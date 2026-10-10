// Финансовое ядро дневника (порт financial_core_v01.py, V05).
// Все суммы — целые копейки (Number.isSafeInteger). Даты — строки YYYY-MM-DD.
// Правила: без возвратов; тариф действует до следующего; аванс фиксирует цену;
// события только добавляются, ошибка исправляется REVERSAL.
(function (global) {
  "use strict";

  const TYPES = new Set([
    "TARIFF_SET", "LESSON_CONDUCTED", "LESSON_CANCELLED",
    "PAYMENT_RECEIVED", "ADVANCE_ALLOCATED", "REVERSAL",
  ]);

  function isDate(s) {
    if (typeof s !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(s)) return false;
    const d = new Date(s + "T00:00:00Z");
    return !isNaN(d.getTime()) && d.toISOString().slice(0, 10) === s;
  }

  function requireDate(v, name) {
    if (!isDate(v)) throw new Error(`${name} must be a date YYYY-MM-DD`);
    return v;
  }

  function requireKop(v, name) {
    if (!Number.isSafeInteger(v) || v < 0) {
      throw new Error(`${name} must be a whole number of kopecks, not negative`);
    }
    return v;
  }

  // Строковое представление с отсортированными ключами: для сравнения дубликатов.
  function stable(value) {
    if (Array.isArray(value)) return "[" + value.map(stable).join(",") + "]";
    if (value && typeof value === "object") {
      return "{" + Object.keys(value).sort()
        .map(k => JSON.stringify(k) + ":" + stable(value[k])).join(",") + "}";
    }
    return JSON.stringify(value);
  }

  function tariffAt(tariffs, day) {
    let current = null;
    for (const t of tariffs) {
      if (t.day <= day) current = t.amount;
      else break;
    }
    return current;
  }

  function need(event, ...fields) {
    for (const f of fields) {
      if (!event[f]) throw new Error(`${event.type} requires ${f}`);
    }
  }

  class FinancialLedger {
    constructor() {
      this.events = new Map();
      this.order = [];
    }

    // Возвращает true — добавлено, false — точный повтор, исключение — правило нарушено.
    // При исключении журнал не меняется.
    add(event) {
      for (const f of ["event_id", "type", "student_id"]) {
        if (!event || event[f] === undefined || event[f] === null) {
          throw new Error(`Missing required event field: ${f}`);
        }
      }
      const eventId = String(event.event_id).trim();
      const type = String(event.type).trim();
      const studentId = String(event.student_id).trim();
      if (!eventId || !studentId) throw new Error("event_id and student_id cannot be empty");
      if (type === "REFUND_PAID") {
        throw new Error("Refunds are not part of the business rules: paid lessons are worked off");
      }
      if (!TYPES.has(type)) throw new Error(`Unsupported event type: ${type}`);

      const n = Object.assign({}, event, {event_id: eventId, type, student_id: studentId});

      switch (type) {
        case "TARIFF_SET":
          need(n, "amount", "effective_from");
          requireKop(n.amount, "amount");
          if (n.amount === 0) throw new Error("Tariff must be positive");
          requireDate(n.effective_from, "effective_from");
          break;

        case "LESSON_CONDUCTED": {
          need(n, "date");
          requireDate(n.date, "date");
          const tariff = tariffAt(this._tariffs(studentId), n.date);
          if (tariff === null) throw new Error("No tariff in effect on the lesson date");
          if ("amount" in event && event.amount !== tariff) {
            throw new Error("Lesson amount does not match the tariff in effect on its date");
          }
          n.amount = tariff;
          break;
        }

        case "PAYMENT_RECEIVED":
          if (n.purpose === "lesson") {
            need(n, "amount", "lesson_id");
            requireKop(n.amount, "amount");
          } else if (n.purpose === "advance") {
            need(n, "amount", "date");
            requireDate(n.date, "date");
            const price = tariffAt(this._tariffs(studentId), n.date);
            if (price === null) throw new Error("No tariff in effect on the payment date");
            requireKop(n.amount, "amount");
            if (n.amount === 0 || n.amount % price !== 0) {
              throw new Error("Advance must equal a whole number of lessons at the tariff");
            }
            n.price = price;                 // цена, зафиксированная авансом
            n.lessons = n.amount / price;
          } else {
            throw new Error("Payment purpose must be lesson or advance");
          }
          break;

        case "ADVANCE_ALLOCATED":
          need(n, "lesson_id");
          if ("amount" in event) {
            throw new Error("ADVANCE_ALLOCATED takes its price from the advance; no amount");
          }
          break;

        case "LESSON_CANCELLED":
          need(n, "lesson_id");
          break;

        case "REVERSAL": {
          const target = String(n.reverses || "").trim();
          if (!target) throw new Error("REVERSAL requires reverses");
          if ("amount" in event) throw new Error("REVERSAL must not carry an amount");
          n.reverses = target;
          break;
        }
      }

      const existing = this.events.get(eventId);
      if (existing) {
        if (stable(existing) !== stable(n)) throw new Error("Conflicting duplicate event_id");
        return false;
      }

      if (type === "REVERSAL") this._checkReversal(n, studentId);

      this.events.set(eventId, n);
      this.order.push(eventId);
      try {
        this.summary(studentId);
      } catch (err) {
        this.order.pop();
        this.events.delete(eventId);
        throw err;
      }
      return true;
    }

    _checkReversal(reversal, studentId) {
      const target = this.events.get(reversal.reverses);
      if (!target) throw new Error("REVERSAL refers to an unknown event");
      if (target.student_id !== studentId) throw new Error("REVERSAL must belong to the same student");
      if (target.type === "REVERSAL") throw new Error("A REVERSAL cannot itself be reversed");
      for (const e of this.events.values()) {
        if (e.type === "REVERSAL" && e.reverses === target.event_id) {
          throw new Error("Event is already reversed");
        }
      }
    }

    // Копии всех событий в порядке добавления.
    list() {
      return this.order.map(id => Object.assign({}, this.events.get(id)));
    }

    _activeEvents(studentId) {
      const reversed = new Set();
      for (const e of this.events.values()) {
        if (e.type === "REVERSAL") reversed.add(e.reverses);
      }
      const active = [];
      for (const id of this.order) {
        const e = this.events.get(id);
        if (e.student_id !== studentId) continue;
        if (e.type === "REVERSAL" || reversed.has(id)) continue;
        active.push(e);
      }
      return active;
    }

    _tariffs(studentId) {
      const items = [];
      for (const e of this._activeEvents(studentId)) {
        if (e.type === "TARIFF_SET") items.push({day: e.effective_from, amount: e.amount});
      }
      items.sort((a, b) => (a.day < b.day ? -1 : a.day > b.day ? 1 : 0));
      for (let i = 1; i < items.length; i++) {
        if (items[i].day === items[i - 1].day) {
          throw new Error("Two tariffs have the same effective date");
        }
      }
      return items;
    }

    // Финансовое положение ученика. Суммы в копейках.
    summary(studentId) {
      studentId = String(studentId);
      const tariffs = this._tariffs(studentId);

      let receipts = 0, advanceReceipts = 0, lessonPayments = 0, advanceValue = 0;
      const buckets = [];                 // FIFO: {left, price}
      const conducted = new Map();        // lesson_id -> {day, amount}
      const cancelled = new Set();
      const paidDirect = new Map();       // lesson_id -> сумма прямой оплаты
      const funded = new Map();           // lesson_id -> цена из аванса
      const sources = new Map();          // lesson_id -> Set("payment" | "advance")
      const addSource = (lid, s) => {
        if (!sources.has(lid)) sources.set(lid, new Set());
        sources.get(lid).add(s);
      };

      for (const e of this._activeEvents(studentId)) {
        const lid = e.lesson_id;
        if (e.type === "LESSON_CONDUCTED") {
          if (conducted.has(lid) || cancelled.has(lid)) {
            throw new Error(`Lesson ${lid} already has a conducted or cancelled record`);
          }
          conducted.set(lid, {day: e.date, amount: e.amount});
        } else if (e.type === "LESSON_CANCELLED") {
          if (conducted.has(lid) || cancelled.has(lid)) {
            throw new Error(`Lesson ${lid} already has a conducted or cancelled record`);
          }
          cancelled.add(lid);
        } else if (e.type === "PAYMENT_RECEIVED") {
          receipts += e.amount;
          if (e.purpose === "lesson") {
            lessonPayments += e.amount;
            paidDirect.set(lid, (paidDirect.get(lid) || 0) + e.amount);
            addSource(lid, "payment");
          } else {
            advanceReceipts += e.amount;
            buckets.push({left: e.lessons, price: e.price});
          }
        } else if (e.type === "ADVANCE_ALLOCATED") {
          const bucket = buckets.find(b => b.left > 0);
          if (!bucket) throw new Error("No prepaid lesson left to allocate");
          bucket.left -= 1;
          if (funded.has(lid)) throw new Error(`Lesson ${lid} is already paid from the advance`);
          funded.set(lid, bucket.price);
          advanceValue += bucket.price;
          addSource(lid, "advance");
        }
      }

      let lessonValue = 0, debt = 0, lessonsPaid = 0;
      for (const [lid, c] of conducted) {
        let value;
        if (funded.has(lid)) {
          value = funded.get(lid);
        } else {
          value = tariffAt(tariffs, c.day);
          if (value === null) throw new Error(`No tariff in effect for lesson ${lid}`);
          if (c.amount !== value) {
            throw new Error(`Lesson ${lid} does not match the tariff in effect on its date`);
          }
        }
        const paid = (paidDirect.get(lid) || 0) + (funded.get(lid) || 0);
        if (paid > value) throw new Error(`Payments for lesson ${lid} exceed its value`);
        if ((sources.get(lid) || new Set()).size > 1) {
          throw new Error(`Lesson ${lid} is paid both by payment and by advance`);
        }
        lessonValue += value;
        debt += value - paid;
        if (paid === value) lessonsPaid += 1;
      }

      for (const lid of new Set([...funded.keys(), ...paidDirect.keys()])) {
        if (!conducted.has(lid)) throw new Error(`Payment for lesson ${lid} without a conducted lesson`);
      }
      for (const lid of cancelled) {
        if (funded.has(lid) || paidDirect.has(lid)) {
          throw new Error(`Lesson ${lid} was cancelled but has payments`);
        }
      }

      const advanceBalance = advanceReceipts - advanceValue;
      if (advanceBalance < 0) throw new Error("Advance allocations exceed the advance received");

      return {
        lesson_value: lessonValue,
        receipts,
        lesson_payments: lessonPayments,
        advance_receipts: advanceReceipts,
        advance_allocated: advanceValue,
        advance_balance: advanceBalance,
        paid_lessons_left: buckets.reduce((s, b) => s + b.left, 0),
        debt,
        lessons_conducted: conducted.size,
        lessons_cancelled: cancelled.size,
        lessons_paid: lessonsPaid,
        tariff_current: tariffs.length ? tariffs[tariffs.length - 1].amount : null,
      };
    }
  }

  global.FinancialLedger = FinancialLedger;
  if (typeof module !== "undefined" && module.exports) module.exports = FinancialLedger;
})(typeof globalThis !== "undefined" ? globalThis : this);

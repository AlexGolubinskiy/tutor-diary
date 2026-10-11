"""Standalone financial reference model V05.

Business rules:
- There are no refunds. A paid lesson is worked off by the teacher.
- Each student has a tariff: the price of one lesson, set with an effective date.
  A tariff applies until the next one. Tariffs change rarely.
- Money received in advance always equals a whole number of lessons at the
  tariff in effect on the payment date. The advance locks that price.
- A lesson paid from an advance costs the locked price, even if the tariff has
  changed since. When the advance runs out, lessons cost the tariff on their date.
- A lesson paid directly (purpose "lesson") costs the tariff on its date.
- A conducted lesson's price cannot be changed retroactively.
- Money received is recorded once, as a PAYMENT_RECEIVED event. Conducting a lesson
  or using an advance is not a receipt.
- Events are append-only. A mistake is corrected by a REVERSAL event that points
  at the original; the original is never edited or deleted.

This is not production persistence or a backup/recovery implementation.
"""
from datetime import date
from decimal import Decimal, InvalidOperation

ZERO = Decimal("0")


def money(value):
    """Return an exact Decimal amount in roubles with at most 2 decimal places.

    float is rejected on purpose: binary floating point cannot represent
    most decimal amounts exactly.
    """
    if isinstance(value, (bool, float)):
        raise TypeError("Amount must be str, int or Decimal, not float")
    if isinstance(value, Decimal):
        result = value
    elif isinstance(value, str):
        try:
            result = Decimal(value.strip())
        except InvalidOperation:
            raise ValueError("Invalid amount")
    elif isinstance(value, int):
        result = Decimal(value)
    else:
        raise TypeError("Unsupported amount type")
    if not result.is_finite() or result < 0:
        raise ValueError("Amount must be a finite non-negative number")
    if result.as_tuple().exponent < -2:
        raise ValueError("Amount must have at most 2 decimal places")
    return result


def _iso_date(value):
    try:
        return date.fromisoformat(str(value).strip())
    except ValueError:
        raise ValueError("Date must be in YYYY-MM-DD format")


class FinancialLedger:
    ALLOWED = {
        "TARIFF_SET",
        "LESSON_CONDUCTED",
        "LESSON_CANCELLED",
        "PAYMENT_RECEIVED",
        "ADVANCE_ALLOCATED",
        "REVERSAL",
    }
    NEEDS_LESSON = {"LESSON_CONDUCTED", "LESSON_CANCELLED", "ADVANCE_ALLOCATED"}

    def __init__(self):
        self._events = {}
        self._order = []

    # ------------------------------------------------------------------ input

    def add_event(self, event):
        """Add an event. Returns False for an identical duplicate, raises on invalid data.

        The event is rejected, and the ledger left unchanged, if the student's
        resulting state would violate a financial rule.
        """
        for field in ("event_id", "type", "student_id"):
            if field not in event:
                raise ValueError(f"Missing required event field: {field}")

        event_id = str(event["event_id"]).strip()
        event_type = str(event["type"]).strip()
        student_id = str(event["student_id"]).strip()

        if not event_id or not student_id:
            raise ValueError("event_id and student_id cannot be empty")
        if event_type == "REFUND_PAID":
            raise ValueError("Refunds are not part of the business rules: paid lessons are worked off")
        if event_type not in self.ALLOWED:
            raise ValueError(f"Unsupported event type: {event_type}")

        normalized = dict(event)
        normalized["event_id"] = event_id
        normalized["type"] = event_type
        normalized["student_id"] = student_id

        if event_type == "TARIFF_SET":
            self._require(normalized, "amount", "effective_from")
            normalized["amount"] = str(money(normalized["amount"]))
            if Decimal(normalized["amount"]) == ZERO:
                raise ValueError("Tariff must be positive")
            normalized["effective_from"] = _iso_date(normalized["effective_from"]).isoformat()

        elif event_type == "LESSON_CONDUCTED":
            self._require(normalized, "date")
            lesson_day = _iso_date(normalized["date"])
            normalized["date"] = lesson_day.isoformat()
            tariff = self._tariff_at(self._tariffs(student_id), lesson_day)
            if tariff is None:
                raise ValueError("No tariff in effect on the lesson date")
            if "amount" in normalized and money(normalized["amount"]) != tariff:
                raise ValueError("Lesson amount does not match the tariff in effect on its date")
            normalized["amount"] = str(tariff)

        elif event_type == "PAYMENT_RECEIVED":
            purpose = normalized.get("purpose")
            if purpose == "lesson":
                self._require(normalized, "amount", "lesson_id")
                normalized["amount"] = str(money(normalized["amount"]))
            elif purpose == "advance":
                self._require(normalized, "amount", "date")
                day = _iso_date(normalized["date"])
                price = self._tariff_at(self._tariffs(student_id), day)
                if price is None:
                    raise ValueError("No tariff in effect on the payment date")
                amount = money(normalized["amount"])
                if amount == ZERO:
                    raise ValueError("Advance must be positive")
                normalized["amount"] = str(amount)
                normalized["date"] = day.isoformat()
                normalized["price"] = str(price)          # locked price for these lessons
                normalized["lessons"] = int(amount // price)
            else:
                raise ValueError("Payment purpose must be lesson or advance")

        elif event_type == "ADVANCE_ALLOCATED":
            self._require(normalized, "lesson_id")
            if "amount" in normalized:
                raise ValueError("ADVANCE_ALLOCATED takes its price from the advance; no amount")

        elif event_type == "LESSON_CANCELLED":
            self._require(normalized, "lesson_id")

        elif event_type == "REVERSAL":
            target_id = str(normalized.get("reverses", "")).strip()
            if not target_id:
                raise ValueError("REVERSAL requires reverses")
            if "amount" in normalized:
                raise ValueError("REVERSAL must not carry an amount")
            normalized["reverses"] = target_id

        if event_id in self._events:
            if self._events[event_id] != normalized:
                raise ValueError("Conflicting duplicate event_id")
            return False

        if event_type == "REVERSAL":
            self._check_reversal(normalized, student_id)

        self._events[event_id] = normalized
        self._order.append(event_id)
        try:
            self.summary(student_id)  # validates the student's full state
        except ValueError:
            self._order.pop()
            del self._events[event_id]
            raise
        return True

    @staticmethod
    def _require(event, *fields):
        for f in fields:
            if not event.get(f):
                raise ValueError(f"{event['type']} requires {f}")

    def _check_reversal(self, reversal, student_id):
        target = self._events.get(reversal["reverses"])
        if target is None:
            raise ValueError("REVERSAL refers to an unknown event")
        if target["student_id"] != student_id:
            raise ValueError("REVERSAL must belong to the same student")
        if target["type"] == "REVERSAL":
            raise ValueError("A REVERSAL cannot itself be reversed")
        if any(e["type"] == "REVERSAL" and e["reverses"] == target["event_id"]
               for e in self._events.values()):
            raise ValueError("Event is already reversed")

    # ------------------------------------------------------------- journal

    def events(self):
        return [dict(self._events[eid]) for eid in self._order]

    def _active_events(self, student_id):
        """Events of one student that are not reversed and not reversal records."""
        reversed_ids = {e["reverses"] for e in self._events.values() if e["type"] == "REVERSAL"}
        active = []
        for eid in self._order:
            e = self._events[eid]
            if e["student_id"] != student_id:
                continue
            if e["type"] == "REVERSAL" or eid in reversed_ids:
                continue
            active.append(e)
        return active

    def _tariffs(self, student_id):
        """Sorted list of (effective_from, amount) for one student."""
        items = []
        for e in self._active_events(student_id):
            if e["type"] == "TARIFF_SET":
                items.append((_iso_date(e["effective_from"]), money(e["amount"])))
        items.sort(key=lambda t: t[0])
        days = [d for d, _ in items]
        if len(set(days)) != len(days):
            raise ValueError("Two tariffs have the same effective date")
        return items

    @staticmethod
    def _tariff_at(tariffs, day):
        current = None
        for effective_from, amount in tariffs:
            if effective_from <= day:
                current = amount
            else:
                break
        return current

    # ------------------------------------------------------------- position

    def summary(self, student_id):
        """Financial position of one student.

        Keys:
          receipts              money received, each payment once
          advance_receipts      money received as advance
          lesson_payments       money received as payment for specific lessons
          advance_allocated     value of lessons paid from advance (at locked prices)
          advance_balance       paid but not yet worked off (money), never negative
          paid_lessons_left     whole lessons left in the advance
          lesson_value          total price of conducted lessons
          debt                  conducted lessons not yet paid, never negative
          lessons_conducted     number of conducted lessons
          lessons_cancelled     number of lessons cancelled for this student (no charge)
          lessons_paid          number of conducted lessons paid in full
          tariff_current        latest tariff, or None
        """
        student_id = str(student_id)
        tariffs = self._tariffs(student_id)

        receipts = ZERO
        advance_receipts = ZERO
        lesson_payments = ZERO
        advance_value = ZERO
        buckets = []             # FIFO: [lessons_left, locked_price]

        conducted = {}           # lesson_id -> date
        cancelled = set()
        paid_direct = {}         # lesson_id -> paid directly
        funded = {}              # lesson_id -> locked price used from advance
        sources = {}             # lesson_id -> set of "payment" / "advance"

        for e in self._active_events(student_id):
            kind = e["type"]
            lid = e.get("lesson_id")

            if kind == "LESSON_CONDUCTED":
                if lid in conducted or lid in cancelled:
                    raise ValueError(f"Lesson {lid} already has a conducted or cancelled record")
                conducted[lid] = (_iso_date(e["date"]), money(e["amount"]))

            elif kind == "LESSON_CANCELLED":
                if lid in conducted or lid in cancelled:
                    raise ValueError(f"Lesson {lid} already has a conducted or cancelled record")
                cancelled.add(lid)

            elif kind == "PAYMENT_RECEIVED":
                amount = money(e["amount"])
                receipts += amount
                if e["purpose"] == "lesson":
                    lesson_payments += amount
                    paid_direct[lid] = paid_direct.get(lid, ZERO) + amount
                    sources.setdefault(lid, set()).add("payment")
                else:
                    advance_receipts += amount
                    buckets.append([amount, money(e["price"])])   # [balance, locked price]

            elif kind == "ADVANCE_ALLOCATED":
                bucket = next((b for b in buckets if b[0] > ZERO), None)
                if bucket is None:
                    raise ValueError("No prepaid balance left to allocate")
                take = min(bucket[0], bucket[1])
                bucket[0] -= take
                if lid in funded:
                    raise ValueError(f"Lesson {lid} is already paid from the advance")
                funded[lid] = (bucket[1], take)        # (locked price, amount taken)
                advance_value += take
                sources.setdefault(lid, set()).add("advance")

        lesson_value = ZERO
        debt = ZERO
        lessons_paid = 0
        tariffs_now = tariffs

        for lid, (day, stored) in conducted.items():
            if lid in funded:
                value = funded[lid][0]       # locked price of the advance
            else:
                value = self._tariff_at(tariffs_now, day)
                if value is None:
                    raise ValueError(f"No tariff in effect for lesson {lid}")
                if stored != value:
                    raise ValueError(f"Lesson {lid} does not match the tariff in effect on its date")
            paid = paid_direct.get(lid, ZERO) + (funded[lid][1] if lid in funded else ZERO)
            if paid > value:
                raise ValueError(f"Payments for lesson {lid} exceed its value")
            lesson_value += value
            debt += value - paid
            if paid == value:
                lessons_paid += 1

        for lid in set(funded) | set(paid_direct):
            if lid not in conducted:
                raise ValueError(f"Payment for lesson {lid} without a conducted lesson")
        for lid in cancelled:
            if lid in funded or lid in paid_direct:
                raise ValueError(f"Lesson {lid} was cancelled but has payments")

        advance_balance = advance_receipts - advance_value

        return {
            "lesson_value": lesson_value,
            "receipts": receipts,
            "lesson_payments": lesson_payments,
            "advance_receipts": advance_receipts,
            "advance_allocated": advance_value,
            "advance_balance": advance_balance,
            "paid_lessons_left": sum(int(b[0] // b[1]) for b in buckets),
            "debt": debt,
            "lessons_conducted": len(conducted),
            "lessons_cancelled": len(cancelled),
            "lessons_paid": lessons_paid,
            "tariff_current": tariffs[-1][1] if tariffs else None,
        }

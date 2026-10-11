"""Tests for the financial reference model V05.

Covers the acceptance scenarios from the project review, tariffs with effective
dates, advances with locked prices, and invariant checks.
"""
import unittest
from decimal import Decimal

from financial_core_v01 import FinancialLedger, money


D = Decimal
START = "2026-01-01"


def set_tariff(ledger, eid, student, amount, effective_from=START):
    return ledger.add_event({
        "event_id": eid, "type": "TARIFF_SET", "student_id": student,
        "amount": amount, "effective_from": effective_from,
    })


def conduct(ledger, eid, student, lesson, day="2026-10-05", amount=None):
    event = {"event_id": eid, "type": "LESSON_CONDUCTED",
             "student_id": student, "lesson_id": lesson, "date": day}
    if amount is not None:
        event["amount"] = amount
    return ledger.add_event(event)


def pay_lesson(ledger, eid, student, lesson, amount="1000"):
    return ledger.add_event({
        "event_id": eid, "type": "PAYMENT_RECEIVED", "purpose": "lesson",
        "student_id": student, "lesson_id": lesson, "amount": amount,
    })


def pay_advance(ledger, eid, student, amount, day="2026-10-01"):
    return ledger.add_event({
        "event_id": eid, "type": "PAYMENT_RECEIVED", "purpose": "advance",
        "student_id": student, "amount": amount, "date": day,
    })


def allocate(ledger, eid, student, lesson):
    return ledger.add_event({
        "event_id": eid, "type": "ADVANCE_ALLOCATED",
        "student_id": student, "lesson_id": lesson,
    })


def cancel(ledger, eid, student, lesson):
    return ledger.add_event({
        "event_id": eid, "type": "LESSON_CANCELLED",
        "student_id": student, "lesson_id": lesson,
    })


def reverse(ledger, eid, student, target):
    return ledger.add_event({
        "event_id": eid, "type": "REVERSAL",
        "student_id": student, "reverses": target,
    })


class TariffTest(unittest.TestCase):
    def test_lesson_takes_price_from_tariff_in_effect_on_its_date(self):
        ledger = FinancialLedger()
        set_tariff(ledger, "t-1", "a", "1000", "2026-01-01")
        set_tariff(ledger, "t-2", "a", "1200", "2027-01-01")
        conduct(ledger, "c-1", "a", "l-1", day="2026-10-05")
        conduct(ledger, "c-2", "a", "l-2", day="2027-02-01")
        s = ledger.summary("a")
        self.assertEqual(s["lesson_value"], D("2200"))
        self.assertEqual(s["tariff_current"], D("1200"))

    def test_lesson_before_any_tariff_is_rejected(self):
        ledger = FinancialLedger()
        set_tariff(ledger, "t-1", "a", "1000", "2026-06-01")
        with self.assertRaises(ValueError):
            conduct(ledger, "c-1", "a", "l-1", day="2026-05-01")

    def test_explicit_lesson_amount_must_match_tariff(self):
        ledger = FinancialLedger()
        set_tariff(ledger, "t-1", "a", "1000")
        with self.assertRaises(ValueError):
            conduct(ledger, "c-1", "a", "l-1", amount="900")

    def test_retroactive_tariff_change_is_rejected(self):
        ledger = FinancialLedger()
        set_tariff(ledger, "t-1", "a", "1000")
        conduct(ledger, "c-1", "a", "l-1", day="2026-10-05")
        with self.assertRaises(ValueError):
            set_tariff(ledger, "t-2", "a", "1200", effective_from="2026-09-01")

    def test_tariff_in_use_cannot_be_reversed(self):
        ledger = FinancialLedger()
        set_tariff(ledger, "t-1", "a", "1000")
        conduct(ledger, "c-1", "a", "l-1", day="2026-10-05")
        with self.assertRaises(ValueError):
            reverse(ledger, "rev-1", "a", "t-1")

    def test_two_tariffs_with_same_date_are_rejected(self):
        ledger = FinancialLedger()
        set_tariff(ledger, "t-1", "a", "1000", "2026-01-01")
        with self.assertRaises(ValueError):
            set_tariff(ledger, "t-2", "a", "1200", "2026-01-01")

    def test_zero_tariff_and_bad_date_are_rejected(self):
        ledger = FinancialLedger()
        with self.assertRaises(ValueError):
            set_tariff(ledger, "t-1", "a", "0")
        with self.assertRaises(ValueError):
            set_tariff(ledger, "t-2", "a", "1000", "01.01.2026")


class AdvanceTest(unittest.TestCase):
    def test_prepaying_several_lessons_is_one_receipt(self):
        ledger = FinancialLedger()
        set_tariff(ledger, "t-1", "a", "1000")
        pay_advance(ledger, "adv-1", "a", "3000")
        s = ledger.summary("a")
        self.assertEqual(s["receipts"], D("3000"))
        self.assertEqual(s["advance_balance"], D("3000"))
        self.assertEqual(s["paid_lessons_left"], 3)
        self.assertEqual(s["debt"], D("0"))

    def test_advance_may_leave_a_tail(self):
        # 2500 при стоимости 1000: 2 занятия полностью, остаток 500 на третье
        ledger = FinancialLedger()
        set_tariff(ledger, "t-1", "a", "1000")
        pay_advance(ledger, "adv-1", "a", "2500")
        for i in (1, 2, 3):
            conduct(ledger, f"c-{i}", "a", f"L{i}", "2026-10-0" + str(i))
            allocate(ledger, f"f-{i}", "a", f"L{i}")
        s = ledger.summary("a")
        self.assertEqual(s["advance_balance"], D("0"))       # 1000 + 1000 + 500
        self.assertEqual(s["debt"], D("500"))                # третье занятие доплачивается на 500
        self.assertEqual(s["paid_lessons_left"], 0)

    def test_advance_tail_is_used_before_cash(self):
        ledger = FinancialLedger()
        set_tariff(ledger, "t-1", "a", "1000")
        pay_advance(ledger, "adv-1", "a", "1500")
        conduct(ledger, "c-1", "a", "L1", "2026-10-01")
        allocate(ledger, "f-1", "a", "L1")                        # полностью из аванса
        conduct(ledger, "c-2", "a", "L2", "2026-10-02")
        allocate(ledger, "f-2", "a", "L2")                        # остаток 500
        s = ledger.summary("a")
        self.assertEqual(s["advance_balance"], D("0"))
        self.assertEqual(s["debt"], D("500"))
        self.assertEqual(s["lessons_paid"], 1)

    def test_advance_requires_tariff_and_date(self):
        ledger = FinancialLedger()
        with self.assertRaises(ValueError):
            pay_advance(ledger, "adv-1", "a", "1000")  # no tariff yet
        set_tariff(ledger, "t-1", "a", "1000")
        with self.assertRaises(ValueError):
            ledger.add_event({"event_id": "adv-2", "type": "PAYMENT_RECEIVED",
                              "purpose": "advance", "student_id": "a", "amount": "1000"})

    def test_conducting_one_prepaid_lesson_reduces_balance_without_receipt(self):
        ledger = FinancialLedger()
        set_tariff(ledger, "t-1", "a", "1000")
        pay_advance(ledger, "adv-1", "a", "3000")
        conduct(ledger, "c-1", "a", "l-1")
        allocate(ledger, "alloc-1", "a", "l-1")
        s = ledger.summary("a")
        self.assertEqual(s["receipts"], D("3000"), "allocation must not be a new receipt")
        self.assertEqual(s["advance_balance"], D("2000"))
        self.assertEqual(s["paid_lessons_left"], 2)
        self.assertEqual(s["lessons_paid"], 1)
        self.assertEqual(s["debt"], D("0"))

    def test_conducting_all_prepaid_lessons_empties_balance(self):
        ledger = FinancialLedger()
        set_tariff(ledger, "t-1", "a", "1000")
        pay_advance(ledger, "adv-1", "a", "3000")
        for i in range(1, 4):
            conduct(ledger, f"c-{i}", "a", f"l-{i}")
            allocate(ledger, f"alloc-{i}", "a", f"l-{i}")
        s = ledger.summary("a")
        self.assertEqual(s["advance_balance"], D("0"))
        self.assertEqual(s["paid_lessons_left"], 0)
        self.assertEqual(s["lessons_paid"], 3)
        self.assertEqual(s["debt"], D("0"))

    def test_lesson_without_prepaid_lessons_stays_debt(self):
        ledger = FinancialLedger()
        set_tariff(ledger, "t-1", "a", "1000")
        conduct(ledger, "c-1", "a", "l-1")
        with self.assertRaises(ValueError):
            allocate(ledger, "alloc-1", "a", "l-1")
        self.assertEqual(ledger.summary("a")["debt"], D("1000"))

    def test_prepaid_lesson_keeps_locked_price_after_tariff_rise(self):
        # Advance of 3000 paid at 1000 covers three lessons at 1000.
        ledger = FinancialLedger()
        set_tariff(ledger, "t-1", "a", "1000", "2026-01-01")
        pay_advance(ledger, "adv-1", "a", "3000", day="2026-10-01")
        set_tariff(ledger, "t-2", "a", "1200", "2027-01-01")
        for i, day in enumerate(["2026-10-05", "2026-10-12", "2026-10-19"], 1):
            conduct(ledger, f"c-{i}", "a", f"l-{i}", day=day)
            allocate(ledger, f"alloc-{i}", "a", f"l-{i}")

        s = ledger.summary("a")
        self.assertEqual(s["lesson_value"], D("3000"), "three lessons at the locked price")
        self.assertEqual(s["debt"], D("0"))
        self.assertEqual(s["advance_balance"], D("0"))

    def test_fourth_lesson_after_advance_runs_out_costs_new_tariff(self):
        ledger = FinancialLedger()
        set_tariff(ledger, "t-1", "a", "1000", "2026-01-01")
        pay_advance(ledger, "adv-1", "a", "3000", day="2026-10-01")
        set_tariff(ledger, "t-2", "a", "1200", "2027-01-01")
        for i, day in enumerate(["2026-10-05", "2026-10-12", "2026-10-19"], 1):
            conduct(ledger, f"c-{i}", "a", f"l-{i}", day=day)
            allocate(ledger, f"alloc-{i}", "a", f"l-{i}")
        conduct(ledger, "c-4", "a", "l-4", day="2027-02-01")

        s = ledger.summary("a")
        self.assertEqual(s["lesson_value"], D("4200"))
        self.assertEqual(s["debt"], D("1200"))
        self.assertEqual(s["lessons_conducted"], 4)

    def test_partly_used_advance_keeps_price_for_remaining_lessons(self):
        ledger = FinancialLedger()
        set_tariff(ledger, "t-1", "a", "1000", "2026-01-01")
        pay_advance(ledger, "adv-1", "a", "3000", day="2026-10-01")
        conduct(ledger, "c-1", "a", "l-1", day="2026-10-05")
        allocate(ledger, "alloc-1", "a", "l-1")
        conduct(ledger, "c-2", "a", "l-2", day="2026-10-12")
        allocate(ledger, "alloc-2", "a", "l-2")
        set_tariff(ledger, "t-2", "a", "1200", "2027-01-01")
        conduct(ledger, "c-3", "a", "l-3", day="2027-01-10")
        allocate(ledger, "alloc-3", "a", "l-3")

        s = ledger.summary("a")
        self.assertEqual(s["lesson_value"], D("3000"))
        self.assertEqual(s["debt"], D("0"))
        self.assertEqual(s["paid_lessons_left"], 0)

    def test_advance_paid_after_tariff_rise_locks_new_price(self):
        ledger = FinancialLedger()
        set_tariff(ledger, "t-1", "a", "1000", "2026-01-01")
        set_tariff(ledger, "t-2", "a", "1200", "2027-01-01")
        pay_advance(ledger, "adv-1", "a", "2400", day="2027-02-01")  # two lessons at 1200
        conduct(ledger, "c-1", "a", "l-1", day="2027-02-05")
        allocate(ledger, "alloc-1", "a", "l-1")
        s = ledger.summary("a")
        self.assertEqual(s["lesson_value"], D("1200"))
        self.assertEqual(s["advance_balance"], D("1200"))
        self.assertEqual(s["paid_lessons_left"], 1)

    def test_reversing_an_allocation_returns_lesson_to_tariff_price(self):
        ledger = FinancialLedger()
        set_tariff(ledger, "t-1", "a", "1000")
        pay_advance(ledger, "adv-1", "a", "1000")
        conduct(ledger, "c-1", "a", "l-1")
        allocate(ledger, "alloc-1", "a", "l-1")
        reverse(ledger, "rev-1", "a", "alloc-1")
        s = ledger.summary("a")
        self.assertEqual(s["debt"], D("1000"))
        self.assertEqual(s["advance_balance"], D("1000"))


class GroupAccountingTest(unittest.TestCase):
    def test_group_of_two_one_pays_one_does_not(self):
        ledger = FinancialLedger()
        set_tariff(ledger, "t-a", "a", "1000")
        set_tariff(ledger, "t-b", "b", "1000")
        conduct(ledger, "c-a", "a", "lesson-1")
        conduct(ledger, "c-b", "b", "lesson-1")
        pay_lesson(ledger, "pay-a", "a", "lesson-1")
        self.assertEqual(ledger.summary("a")["debt"], D("0"))
        self.assertEqual(ledger.summary("a")["receipts"], D("1000"))
        self.assertEqual(ledger.summary("b")["debt"], D("1000"))
        self.assertEqual(ledger.summary("b")["receipts"], D("0"))

    def test_absent_participant_is_not_charged(self):
        # Rule C: the absent participant gets LESSON_CANCELLED, not LESSON_CONDUCTED.
        ledger = FinancialLedger()
        set_tariff(ledger, "t-a", "a", "1000")
        conduct(ledger, "c-a", "a", "lesson-2")
        cancel(ledger, "cancel-c", "c", "lesson-2")
        c = ledger.summary("c")
        self.assertEqual(c["lesson_value"], D("0"))
        self.assertEqual(c["debt"], D("0"))
        self.assertEqual(c["lessons_cancelled"], 1)
        self.assertEqual(ledger.summary("a")["debt"], D("1000"))

    def test_absent_participant_keeps_advance_payment(self):
        ledger = FinancialLedger()
        set_tariff(ledger, "t-c", "c", "1000")
        set_tariff(ledger, "t-a", "a", "1000")
        pay_advance(ledger, "adv-c", "c", "2000")
        conduct(ledger, "c-a", "a", "lesson-2")
        cancel(ledger, "cancel-c", "c", "lesson-2")
        c = ledger.summary("c")
        self.assertEqual(c["advance_balance"], D("2000"), "payment of an absent participant is kept")
        self.assertEqual(c["paid_lessons_left"], 2)
        self.assertEqual(c["debt"], D("0"))
        self.assertEqual(c["receipts"], D("2000"))


class IdempotencyTest(unittest.TestCase):
    def test_repeated_advance_is_not_counted_twice(self):
        ledger = FinancialLedger()
        set_tariff(ledger, "t-1", "a", "1000")
        event = {"event_id": "adv-1", "type": "PAYMENT_RECEIVED", "purpose": "advance",
                 "student_id": "a", "amount": "3000", "date": "2026-10-01"}
        self.assertTrue(ledger.add_event(event))
        self.assertFalse(ledger.add_event(dict(event)))
        s = ledger.summary("a")
        self.assertEqual(s["receipts"], D("3000"))
        self.assertEqual(s["paid_lessons_left"], 3)
        self.assertEqual(len(ledger.events()), 2)  # tariff + one advance

    def test_repeated_lesson_is_not_charged_twice(self):
        ledger = FinancialLedger()
        set_tariff(ledger, "t-1", "a", "1000")
        event = {"event_id": "c-1", "type": "LESSON_CONDUCTED", "student_id": "a",
                 "lesson_id": "l-1", "date": "2026-10-05"}
        self.assertTrue(ledger.add_event(event))
        self.assertFalse(ledger.add_event(dict(event)))
        self.assertEqual(ledger.summary("a")["debt"], D("1000"))

    def test_conflicting_reuse_of_event_id_is_rejected(self):
        ledger = FinancialLedger()
        set_tariff(ledger, "t-1", "a", "1000")
        pay_advance(ledger, "adv-1", "a", "3000")
        with self.assertRaises(ValueError):
            pay_advance(ledger, "adv-1", "a", "5000")


class CorrectionTest(unittest.TestCase):
    """Scenario: a wrong record is corrected without deleting history."""

    def test_wrong_advance_is_corrected_by_reversal(self):
        ledger = FinancialLedger()
        set_tariff(ledger, "t-1", "a", "1000")
        pay_advance(ledger, "adv-wrong", "a", "5000")   # typo: should be 3000
        reverse(ledger, "rev-1", "a", "adv-wrong")
        pay_advance(ledger, "adv-right", "a", "3000")
        s = ledger.summary("a")
        self.assertEqual(s["receipts"], D("3000"))
        self.assertEqual(s["paid_lessons_left"], 3)
        ids = [e["event_id"] for e in ledger.events()]
        self.assertIn("adv-wrong", ids, "the wrong record must stay in the journal")

    def test_reversal_cannot_be_reversed_or_repeated(self):
        ledger = FinancialLedger()
        set_tariff(ledger, "t-1", "a", "1000")
        pay_advance(ledger, "adv-1", "a", "3000")
        reverse(ledger, "rev-1", "a", "adv-1")
        with self.assertRaises(ValueError):
            reverse(ledger, "rev-2", "a", "adv-1")
        with self.assertRaises(ValueError):
            reverse(ledger, "rev-3", "a", "rev-1")

    def test_cannot_reverse_advance_that_was_already_used(self):
        ledger = FinancialLedger()
        set_tariff(ledger, "t-1", "a", "1000")
        pay_advance(ledger, "adv-1", "a", "1000")
        conduct(ledger, "c-1", "a", "l-1")
        allocate(ledger, "alloc-1", "a", "l-1")
        with self.assertRaises(ValueError):
            reverse(ledger, "rev-1", "a", "adv-1")

    def test_cannot_reverse_another_students_event(self):
        ledger = FinancialLedger()
        set_tariff(ledger, "t-1", "a", "1000")
        pay_advance(ledger, "adv-1", "a", "1000")
        with self.assertRaises(ValueError):
            reverse(ledger, "rev-1", "b", "adv-1")

    def test_reversal_cannot_carry_amount(self):
        ledger = FinancialLedger()
        set_tariff(ledger, "t-1", "a", "1000")
        pay_advance(ledger, "adv-1", "a", "1000")
        with self.assertRaises(ValueError):
            ledger.add_event({"event_id": "rev-1", "type": "REVERSAL", "student_id": "a",
                              "reverses": "adv-1", "amount": "1000"})


class NoRefundsTest(unittest.TestCase):
    def test_refund_event_is_rejected(self):
        ledger = FinancialLedger()
        set_tariff(ledger, "t-1", "a", "1000")
        pay_advance(ledger, "adv-1", "a", "1000")
        with self.assertRaises(ValueError):
            ledger.add_event({"event_id": "ref-1", "type": "REFUND_PAID",
                              "student_id": "a", "amount": "500"})
        self.assertEqual(ledger.summary("a")["advance_balance"], D("1000"))


class PaymentRulesTest(unittest.TestCase):
    def test_payment_without_conducted_lesson_is_rejected(self):
        ledger = FinancialLedger()
        with self.assertRaises(ValueError):
            pay_lesson(ledger, "pay-1", "a", "lesson-x")
        self.assertEqual(ledger.events(), [])

    def test_payment_for_cancelled_lesson_is_rejected(self):
        ledger = FinancialLedger()
        cancel(ledger, "cancel-1", "a", "lesson-1")
        with self.assertRaises(ValueError):
            pay_lesson(ledger, "pay-1", "a", "lesson-1")

    def test_overpayment_is_rejected(self):
        ledger = FinancialLedger()
        set_tariff(ledger, "t-1", "a", "1000")
        conduct(ledger, "c-1", "a", "lesson-1")
        with self.assertRaises(ValueError):
            pay_lesson(ledger, "pay-1", "a", "lesson-1", amount="1500")
        self.assertEqual(ledger.summary("a")["debt"], D("1000"))

    def test_lesson_paid_by_payment_and_by_advance_is_rejected(self):
        ledger = FinancialLedger()
        set_tariff(ledger, "t-1", "a", "1000")
        conduct(ledger, "c-1", "a", "lesson-1")
        pay_advance(ledger, "adv-1", "a", "1000")
        allocate(ledger, "alloc-1", "a", "lesson-1")
        with self.assertRaises(ValueError):
            pay_lesson(ledger, "pay-1", "a", "lesson-1", amount="400")

    def test_lesson_cannot_be_recorded_twice(self):
        ledger = FinancialLedger()
        set_tariff(ledger, "t-1", "a", "1000")
        conduct(ledger, "c-1", "a", "lesson-1")
        with self.assertRaises(ValueError):
            conduct(ledger, "c-2", "a", "lesson-1")


class MoneyTest(unittest.TestCase):
    def test_float_is_rejected(self):
        with self.assertRaises(TypeError):
            money(0.1)

    def test_exact_decimal_arithmetic(self):
        self.assertEqual(money("0.1") + money("0.2"), D("0.3"))

    def test_more_than_two_decimals_rejected(self):
        with self.assertRaises(ValueError):
            money("0.001")


if __name__ == "__main__":
    unittest.main()

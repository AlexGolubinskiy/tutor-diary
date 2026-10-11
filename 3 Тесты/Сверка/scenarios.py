import json
S = "s1"
def t(i, amount, frm): return {"type":"TARIFF_SET","event_id":i,"student_id":S,"amount":amount,"effective_from":frm}
def c(i, lid, date, amount=None):
    e = {"type":"LESSON_CONDUCTED","event_id":i,"student_id":S,"lesson_id":lid,"date":date}
    if amount is not None: e["amount"] = amount
    return e
def pl(i, lid, amount): return {"type":"PAYMENT_RECEIVED","event_id":i,"student_id":S,"purpose":"lesson","lesson_id":lid,"amount":amount}
def pa(i, amount, date): return {"type":"PAYMENT_RECEIVED","event_id":i,"student_id":S,"purpose":"advance","amount":amount,"date":date}
def al(i, lid): return {"type":"ADVANCE_ALLOCATED","event_id":i,"student_id":S,"lesson_id":lid}
def cx(i, lid): return {"type":"LESSON_CANCELLED","event_id":i,"student_id":S,"lesson_id":lid}
def rv(i, target): return {"type":"REVERSAL","event_id":i,"student_id":S,"reverses":target}
sc = {
 "direct_payment": [t("t1",80000,"2026-01-01"), c("c1","L1","2026-02-02"), pl("p1","L1",80000)],
 "advance_covers_3": [t("t1",80000,"2026-01-01"), pa("a1",240000,"2026-02-01"),
     c("c2","L2","2026-02-03"), al("f2","L2"), c("c3","L3","2026-02-10"), al("f3","L3"),
     c("c4","L4","2026-02-17"), al("f4","L4"), c("c5","L5","2026-02-24")],
 "locked_price_after_tariff_change": [t("t1",80000,"2026-01-01"), pa("a1",240000,"2026-02-01"),
     t("t2",120000,"2026-03-01"), c("c1","L1","2026-03-05"), al("f1","L1"),
     c("c2","L2","2026-03-12"), al("f2","L2"), c("c3","L3","2026-03-19"), al("f3","L3"),
     c("c4","L4","2026-03-26")],
 "advance_not_multiple": [t("t1",80000,"2026-01-01"), pa("a1",100000,"2026-02-01")],
 "refund_rejected": [t("t1",80000,"2026-01-01"), {"type":"REFUND_PAID","event_id":"r1","student_id":S}],
 "reversal_of_lesson": [t("t1",80000,"2026-01-01"), c("c1","L1","2026-02-02"), rv("R1","c1")],
 "duplicate_identical_and_conflict": [t("t1",80000,"2026-01-01"), t("t1",80000,"2026-01-01"), t("t1",90000,"2026-01-01")],
 "amount_mismatch": [t("t1",80000,"2026-01-01"), c("c1","L1","2026-02-02",70000)],
 "overpayment": [t("t1",80000,"2026-01-01"), c("c1","L1","2026-02-02"), pl("p1","L1",80000), pl("p2","L1",10000)],
 "cancelled_with_payment": [t("t1",80000,"2026-01-01"), cx("x1","L1"), pl("p1","L1",80000)],
 "two_tariffs_same_date": [t("t1",80000,"2026-01-01"), t("t2",90000,"2026-01-01")],
 "advance_exhausted": [t("t1",80000,"2026-01-01"), pa("a1",80000,"2026-02-01"), c("c1","L1","2026-02-02"), al("f1","L1"), c("c2","L2","2026-02-09"), al("f2","L2")],
 "payment_without_lesson": [t("t1",80000,"2026-01-01"), pl("p1","L9",80000)],
 "double_reversal": [t("t1",80000,"2026-01-01"), c("c1","L1","2026-02-02"), rv("R1","c1"), rv("R2","c1")],
 "lesson_before_tariff": [t("t1",80000,"2026-03-01"), c("c1","L1","2026-02-02")],
}
json.dump(sc, open("scenarios.json","w"), ensure_ascii=False, indent=1)

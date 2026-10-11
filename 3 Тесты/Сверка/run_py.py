import sys, json
sys.path.insert(0, "/home/claude")
from financial_core_v01 import FinancialLedger
from decimal import Decimal
def rub(k): return f"{k//100}.{k%100:02d}"
def kop(d): return int(Decimal(d) * 100)
out = {}
for name, events in json.load(open("scenarios.json")).items():
    L = FinancialLedger(); res = []
    for e in events:
        ev = dict(e)
        if "amount" in ev: ev["amount"] = rub(ev["amount"])
        try:
            res.append("ok" if L.add_event(ev) else "dup")
        except (ValueError, TypeError):
            res.append("error")
    try:
        s = L.summary("s1")
        summ = {k: (kop(v) if k in ("lesson_value","receipts","lesson_payments","advance_receipts","advance_allocated","advance_balance","debt") else (None if v is None else (kop(v) if k=="tariff_current" else v))) for k, v in s.items()}
    except ValueError:
        summ = "error"
    out[name] = {"results": res, "summary": summ}
json.dump(out, open("py_out.json","w"), ensure_ascii=False, indent=1, sort_keys=True)

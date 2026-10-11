from playwright.sync_api import sync_playwright
alerts = []
def on_dialog(d):
    if d.type == "prompt": d.dismiss()
    else: alerts.append(d.message); d.accept()
with sync_playwright() as p:
    b = p.chromium.launch(); pg = b.new_page(); errs = []
    pg.on("pageerror", lambda e: errs.append(str(e))); pg.on("dialog", on_dialog)
    pg.goto("http://localhost:8766/index.html")
    pg.evaluate("() => localStorage.clear()"); pg.reload(); pg.wait_for_selector("#page1 tr")
    row = lambda i: pg.locator("#page1 section.day").first.locator("tbody tr").nth(i)
    def name(i, t): row(i).locator("span.name").evaluate("(e,t)=>{e.textContent=t; e.dispatchEvent(new Event('blur'));}", t)
    def tariff(i, t):
        inp = row(i).locator("input.tariff-in"); inp.fill(t); inp.press("Enter")
    def att(i): row(i).locator("td.att").click()
    def pay(i, amount, method):
        row(i).locator("td.pay").click()
        if amount: row(i).locator(".pay-edit input").fill(amount)
        V={"наличные":"cash","безнал":"bank","аванс":"prepay","из аванса":"fromadvance","не оплачено":"none"}; sel = row(i).locator(".pay-edit select"); sel.select_option(value=V[method]); sel.press("Enter")
    def cell(i): return row(i).locator("td.pay").inner_text(), row(i).locator("td.att").inner_text()
    def summ(n): return pg.evaluate("(n)=>buildLedger(JSON.parse(localStorage.getItem('tutorDiaryLedgerV1')||'[]')).summary(n)", n)

    name(0, "Аня"); tariff(0, "800"); att(0); pay(0, "800", "наличные")
    print("1", cell(0), alerts); assert cell(0) == ("800 ₽ · нал.", "+") and not alerts
    s = summ("аня"); assert s["debt"] == 0 and s["lessons_paid"] == 1

    att(0)  # + -> −
    print("2 alert:", alerts[-1:]); assert "«−»" in alerts[-1] and cell(0)[1] == "+"

    name(1, "Петя"); tariff(1, "800"); pay(1, "2400", "аванс")
    print("3", cell(1), alerts[-1:])
    name(2, "Петя"); att(2); pay(2, "", "из аванса")
    print("3b", cell(2))
    s = summ("петя"); print("3 Петя:", {k: s[k] for k in ["advance_balance","paid_lessons_left"]})
    assert s["advance_balance"] == 160000 and s["paid_lessons_left"] == 2

    name(3, "Аня"); att(3); n = len(alerts)
    pay(3, "", "из аванса")
    print("4 alert:", alerts[n:]); assert len(alerts) == n + 1 and "на аванс" in alerts[-1]

    name(4, "Вася"); tariff(4, "800"); n = len(alerts)
    pay(4, "1000", "аванс")
    print("5 (tail, no error expected):", alerts[n:], cell(4)); assert len(alerts) == n

    # Escape отменяет редактирование без сохранения
    row(0).locator("td.pay").click(); row(0).locator(".pay-edit input").fill("999")
    row(0).locator(".pay-edit input").press("Escape")
    print("6 after escape:", cell(0)); assert cell(0)[0] == "800 ₽ · нал."

    pg.reload(); pg.wait_for_selector("#page1 tr")
    print("7 after reload:", cell(0), cell(1), cell(2))
    print("errors:", errs); assert not errs
    print("ALL OK"); b.close()

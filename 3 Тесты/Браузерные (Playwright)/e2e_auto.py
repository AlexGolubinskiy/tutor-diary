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
    day = lambda d: pg.locator("#page1 section.day, #page2 section.day").nth(d)
    row = lambda d, i: day(d).locator("tbody tr").nth(i)
    cellpay = lambda d, i: row(d, i).locator("td.pay").inner_text()
    # Пн 5.10: Олег, тариф 800, аванс 4000
    row(0,0).locator("span.name").evaluate("e=>{e.textContent='Олег'; e.dispatchEvent(new Event('blur'));}")
    t = row(0,0).locator("input.tariff-in"); t.fill("800"); t.press("Enter")
    row(0,0).locator("td.pay").click(); row(0,0).locator(".pay-edit input").fill("4000")
    s = row(0,0).locator(".pay-edit select"); s.select_option(value="prepay"); s.press("Enter")
    # Вт 6.10: Олег отмечен «+» (без оплаты) — должно списаться из аванса автоматически
    row(0,1).locator("span.name").evaluate("e=>{e.textContent='Олег'; e.dispatchEvent(new Event('blur'));}")
    row(0,1).locator("td.att").click()
    print("Mon:", cellpay(0,0), "| Tue:", cellpay(0,1), "| alerts:", alerts)
    assert cellpay(0,1) == "из аванса" and not alerts
    # Ср 7.10: Олег — занятие «—» → подсказка «из аванса (план)»
    row(0,2).locator("span.name").evaluate("e=>{e.textContent='Олег'; e.dispatchEvent(new Event('blur'));}")
    print("Wed:", cellpay(0,2))
    assert cellpay(0,2) == "из аванса"
    # Остаток: 4000 - 800 (вт) = 3200 → среда покрыта, четверг — 2400 …
    s = pg.evaluate("() => buildLedger(JSON.parse(localStorage.getItem('tutorDiaryLedgerV1'))).summary('олег')")
    print("advance_balance:", s["advance_balance"], "debt:", s["debt"])
    assert s["advance_balance"] == 320000 and s["debt"] == 0
    print("errors:", errs); assert not errs
    print("ALL OK"); b.close()

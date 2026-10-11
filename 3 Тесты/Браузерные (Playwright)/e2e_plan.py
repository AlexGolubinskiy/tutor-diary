from playwright.sync_api import sync_playwright
def mk(id, student="", **kw):
    r = {"id": id, "time": "", "student": student, "attendance": "—",
         "payment": {"amountKop": 0, "method": "none"}, "isGroup": False, "groupId": None,
         "tariffKop": None, "collapsed": False}
    r.update(kw); return r
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
    row(0).locator("span.name").evaluate("e=>{e.textContent='Аня'; e.dispatchEvent(new Event('blur'));}")
    inp = row(0).locator("input.tariff-in"); inp.fill("800"); inp.press("Enter")
    row(0).locator("td.pay").click(); row(0).locator(".pay-edit input").fill("2000")
    s = row(0).locator(".pay-edit select"); s.select_option(value="prepay"); s.press("Enter")
    print("prepay cell:", row(0).locator("td.pay").inner_text(), "alerts:", alerts)
    assert not alerts
    # следующая неделя: у Ани занятия «—» по дням
    pg.evaluate("""() => {
      const all = JSON.parse(localStorage.getItem('tutorDiaryV2'));
      all['2026-10-12'] = {days: [0,1,2,3,4,5].map(i => ({rows: i < 4 ? [{id:'n'+i, time:'10.00-11.00', student:'Аня',
          attendance:'—', payment:{amountKop:0,method:'none'}, isGroup:false, groupId:null, tariffKop:null, collapsed:false}] : []}))};
      localStorage.setItem('tutorDiaryV2', JSON.stringify(all));
      document.getElementById('datePick').value = '2026-10-12'; render();
    }""")
    texts = pg.locator("#page1 section.day tbody tr:first-child td.pay, #page2 section.day tbody tr:first-child td.pay").all_inner_texts()
    print("next week pay cells:", texts)
    assert texts[0] == "из аванса" and texts[1] == "из аванса"
    assert texts[2].startswith("аванс: осталось 400") and texts[3] == ""
    # подсказка не сохраняется как оплата
    print("stored payment day0:", pg.evaluate("() => JSON.parse(localStorage.getItem('tutorDiaryV2'))['2026-10-12'].days[0].rows[0].payment"))
    assert pg.evaluate("() => JSON.parse(localStorage.getItem('tutorDiaryV2'))['2026-10-12'].days[0].rows[0].payment.method") == "none"
    print("errors:", errs); assert not errs
    print("ALL OK"); b.close()

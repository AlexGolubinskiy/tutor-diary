from playwright.sync_api import sync_playwright
def mk(id, time="", student="", **kw):
    r = {"id": id, "time": time, "student": student, "attendance": "—",
         "payment": {"amountKop": 0, "method": "none"}, "isGroup": False, "groupId": None,
         "tariffKop": None, "collapsed": False}
    r.update(kw); return r
day0 = [mk("a", "17.00-18.00", "Аня"),
        mk("g", "10.00-11.00", "группа", isGroup=True),
        mk("m1", "", "Петя", groupId="g"), mk("m2", "", "Оля", groupId="g"),
        mk("c", "12.00-13.00", "Вася"), mk("e", "", "")]
data = {"days": [{"rows": day0}] + [{"rows": []} for _ in range(5)]}
with sync_playwright() as p:
    b = p.chromium.launch(); pg = b.new_page(); errs = []
    pg.on("pageerror", lambda e: errs.append(str(e))); pg.on("dialog", lambda d: d.accept())
    pg.goto("http://localhost:8766/index.html")
    pg.evaluate("d => { localStorage.clear(); localStorage.setItem('tutorDiaryV2', JSON.stringify({'2026-10-05': d})); }", data)
    pg.reload(); pg.wait_for_selector("#page1 tr")
    names = lambda: pg.locator("#page1 section.day").first.locator("tbody tr span.name").all_inner_texts()
    print("start:", names())
    # изменяем время Ани на 09.00 — она должна встать первой, группа с участниками — после неё
    row = pg.locator("#page1 section.day").first.locator("tbody tr").nth(0)
    row.locator("td").first.evaluate("e=>{e.textContent='09.00-10.00'; e.dispatchEvent(new Event('blur'));}")
    print("after 09.00 Аня:", names())
    # новый ученик с временем 11.30 — между группой (10.00) и Васей (12.00)
    pg.locator("#page1 section.day").first.locator("button", has_text="+ занятие").click()
    nr = pg.locator("#page1 section.day").first.locator("tbody tr").last
    nr.locator("span.name").evaluate("e=>{e.textContent='Женя'; e.dispatchEvent(new Event('blur'));}")
    nr = pg.locator("#page1 section.day").first.locator("tbody tr").filter(has_text="Женя").first
    nr.locator("td").first.evaluate("e=>{e.textContent='11.30-12.30'; e.dispatchEvent(new Event('blur'));}")
    print("after Женя 11.30:", names())
    got = names()
    assert got.index("Аня") == 0, got
    assert got.index("группа") < got.index("Женя") < got.index("Вася"), got
    assert got.index("Петя") == got.index("группа") + 1 and got.index("Оля") == got.index("группа") + 2, got
    assert got[-1] == "" , got
    print("errors:", errs); assert not errs
    print("ALL OK"); b.close()

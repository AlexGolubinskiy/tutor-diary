const fs = require("fs");
const FinancialLedger = require("/home/claude/tutor-diary/ledger.js");
const sc = JSON.parse(fs.readFileSync("scenarios.json", "utf8"));
const out = {};
for (const name of Object.keys(sc)) {
  const L = new FinancialLedger(); const res = [];
  for (const e of sc[name]) {
    try { res.push(L.add(e) ? "ok" : "dup"); } catch (err) { res.push("error"); }
  }
  let summ;
  try { summ = L.summary("s1"); } catch (err) { summ = "error"; }
  out[name] = {results: res, summary: summ};
}
fs.writeFileSync("js_out.json", JSON.stringify(out, null, 1));

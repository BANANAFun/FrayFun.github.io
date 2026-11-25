// Тайминги по паузам готовой озвучки: границы фраз (секунды) → ../audio/{phrases,words,shots}.json
//   node tools/align_pauses.mjs "0,4.58;4.96,10.08;..." <total_sec>
import fs from "node:fs";
const spans = process.argv[2].split(";").map((p) => p.split(",").map(Number));
const totalSec = Number(process.argv[3]);
const lines = fs.readFileSync("../script/voice.txt", "utf8").split(/\r?\n/).map((s) => s.trim()).filter(Boolean);
if (lines.length !== spans.length) throw new Error(`фраз ${lines.length}, отрезков ${spans.length}`);
const words = [], phrases = [];
lines.forEach((line, k) => {
  const [s0, e0] = spans[k], dur = e0 - s0;
  phrases.push({ text: line, s: s0, e: e0 });
  const ws = line.split(/\s+/).filter((w) => w && w !== "—");
  const wt = ws.map((w) => w.replace(/[^\p{L}\p{N}]/gu, "").length + 1.5 + (/[,:;.—]$/.test(w) ? 2.5 : 0));
  const sum = wt.reduce((x, y) => x + y, 0);
  let acc = 0;
  ws.forEach((w, i) => { const s = s0 + (acc / sum) * dur; acc += wt[i]; words.push({ t: w, s, e: s0 + (acc / sum) * dur }); });
});
const F = 30, total = Math.ceil((totalSec + 0.5) * F);
const shots = phrases.map((x, k) => ({ i: k + 1, text: x.text, start: k ? Math.round(x.s * F) - 2 : 1, end: k < phrases.length - 1 ? Math.round(phrases[k + 1].s * F) - 3 : total }));
fs.writeFileSync("../audio/phrases.json", JSON.stringify(phrases, null, 1));
fs.writeFileSync("../audio/words.json", JSON.stringify(words, null, 1));
fs.writeFileSync("../audio/shots.json", JSON.stringify({ fps: F, total, shots }, null, 1));
console.log(total, shots.map((s) => `${s.i}:${s.start}-${s.end}`).join(" "));

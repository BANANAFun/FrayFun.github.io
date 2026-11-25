// Piper (sherpa-onnx): каждая строка сценария синтезируется отдельно → точные границы фраз.
//   node tools/tts_lines.mjs ../script/voice.txt public/voice.wav [voice] [speed]
// Пишет ../audio/words.json (слова: тайминги внутри фразы пропорционально длине) и ../audio/phrases.json.
import fs from "node:fs";
import path from "node:path";
import os from "node:os";
import { execFileSync } from "node:child_process";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const [, , txtFile, out = "public/voice.wav", voice = "ru_RU-dmitri-medium", speed = "1.0"] = process.argv;
const DIR = path.join(os.homedir(), ".real3d-shorts", "tts");
const vdir = path.join(DIR, `vits-piper-${voice}`);
if (!fs.existsSync(path.join(vdir, "tokens.txt"))) {
  fs.mkdirSync(DIR, { recursive: true });
  const name = `vits-piper-${voice}.tar.bz2`;
  execFileSync("curl", ["-sL", "-f", "-o", name, `https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/${name}`], { cwd: DIR, stdio: "inherit" });
  execFileSync("tar", ["xjf", name], { cwd: DIR, stdio: "inherit" });
  fs.rmSync(path.join(DIR, name), { force: true });
}
const sherpa = require("sherpa-onnx-node");
const onnx = fs.readdirSync(vdir).find((f) => f.endsWith(".onnx"));
const tts = new sherpa.OfflineTts({
  model: { vits: { model: path.join(vdir, onnx), tokens: path.join(vdir, "tokens.txt"), dataDir: path.join(vdir, "espeak-ng-data"),
    noiseScale: 0.55, noiseScaleW: 0.6, lengthScale: 1.0 }, numThreads: 4, provider: "cpu" }, maxNumSentences: 1 });
const lines = fs.readFileSync(txtFile, "utf8").split(/\r?\n/).map((s) => s.trim()).filter(Boolean);
const GAP = 0.32, LEAD = 0.15;
let sr = 22050;
const chunks = [], words = [], phrases = [];
let t = LEAD;
const trim = (a) => { // срезаем тишину по краям фразы
  let s = 0, e = a.length - 1; while (s < e && Math.abs(a[s]) < 0.01) s++; while (e > s && Math.abs(a[e]) < 0.01) e--;
  return a.subarray(Math.max(0, s - 200), Math.min(a.length, e + 400));
};
for (const line of lines) {
  const a = tts.generate({ text: line, sid: 0, speed: Number(speed) });
  sr = a.sampleRate;
  const smp = trim(Float32Array.from(a.samples));
  if (!chunks.length) chunks.push(new Float32Array(Math.floor(sr * LEAD)));
  const dur = smp.length / sr;
  phrases.push({ text: line, s: t, e: t + dur });
  // слова: веса по числу букв (+1 за паузу у знака препинания)
  const ws = line.split(/\s+/).filter((w) => w && w !== "—");
  const wt = ws.map((w) => w.replace(/[^\p{L}\p{N}]/gu, "").length + 1.5 + (/[,:;.—]$/.test(w) ? 2.5 : 0));
  const sum = wt.reduce((x, y) => x + y, 0);
  let acc = 0;
  ws.forEach((w, i) => { const s = t + (acc / sum) * dur; acc += wt[i]; words.push({ t: w, s, e: t + (acc / sum) * dur }); });
  chunks.push(smp, new Float32Array(Math.floor(sr * GAP)));
  t += dur + GAP;
}
const total = chunks.reduce((s, c) => s + c.length, 0);
const all = new Float32Array(total);
let o = 0; for (const c of chunks) { all.set(c, o); o += c.length; }
const tmp = out.replace(/\.wav$/, "_raw.wav");
const buf = Buffer.alloc(44 + total * 2);
buf.write("RIFF", 0); buf.writeUInt32LE(36 + total * 2, 4); buf.write("WAVE", 8); buf.write("fmt ", 12); buf.writeUInt32LE(16, 16);
buf.writeUInt16LE(1, 20); buf.writeUInt16LE(1, 22); buf.writeUInt32LE(sr, 24); buf.writeUInt32LE(sr * 2, 28); buf.writeUInt16LE(2, 32);
buf.writeUInt16LE(16, 34); buf.write("data", 36); buf.writeUInt32LE(total * 2, 40);
for (let i = 0; i < total; i++) buf.writeInt16LE(Math.round(Math.max(-1, Math.min(1, all[i])) * 32767), 44 + i * 2);
fs.mkdirSync(path.dirname(path.resolve(out)), { recursive: true });
fs.writeFileSync(tmp, buf);
// лёгкая обработка голоса: срез низа, компрессия, «присутствие»
execFileSync("ffmpeg", ["-y", "-loglevel", "error", "-i", tmp, "-af",
  "highpass=f=80,equalizer=f=3000:t=q:w=1.2:g=3,equalizer=f=180:t=q:w=1:g=2,acompressor=threshold=0.1:ratio=3:attack=5:release=80,aresample=44100", out]);
fs.rmSync(tmp);
fs.writeFileSync("../audio/words.json", JSON.stringify(words, null, 1));
fs.writeFileSync("../audio/phrases.json", JSON.stringify(phrases, null, 1));
console.log("голос →", out, (total / sr).toFixed(1), "с");
phrases.forEach((p, i) => console.log(i + 1, p.s.toFixed(2), p.e.toFixed(2), p.text.slice(0, 40)));

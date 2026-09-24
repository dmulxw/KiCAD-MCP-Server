import { readFileSync } from "node:fs";
import { widenThinSegments } from "../projects/touch-panel/scripts/widen-thin-tracks.mjs";

const orig = readFileSync("projects/touch-panel/touch-panel.kicad_pcb", "utf8").replace(/\r\n/g, "\n");
const { text, raised } = widenThinSegments(orig, 0.2);

const hist = (s) => {
  const h = {};
  for (const x of s.match(/\(width [0-9.]+\)/g) ?? []) h[x] = (h[x] ?? 0) + 1;
  return h;
};
const count = (s, lit) => s.split(lit).length - 1;

console.log("raised:", raised);
for (const lit of ["(width 0.05)", "(width 0.1)", "(width 0.12)", "(width 0.15)", "(width 0.2)"]) {
  console.log(` ${lit}  before=${count(orig, lit)}  after=${count(text, lit)}`);
}
console.log("length delta:", text.length - orig.length, "(expect 58 * +1 for '15'->'2')");

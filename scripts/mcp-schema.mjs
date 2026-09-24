#!/usr/bin/env node
/**
 * Print the input schema of one or more MCP tools from the cache written by
 * `node scripts/mcp-probe.mjs` against a `tools/list` call.
 *
 * Usage:
 *   node scripts/mcp-schema.mjs create_project add_board_outline
 *   node scripts/mcp-schema.mjs --search foam
 */
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join, resolve } from "node:path";

const REPO_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const CACHE = join(REPO_ROOT, "node_modules", ".cache", "mcp-tools.json");

const tools = JSON.parse(readFileSync(CACHE, "utf8"));
const byName = new Map(tools.map((t) => [t.name, t]));
const args = process.argv.slice(2);

if (args[0] === "--search") {
  const needle = (args[1] ?? "").toLowerCase();
  for (const t of tools) {
    if (t.name.includes(needle) || t.description?.toLowerCase().includes(needle)) {
      console.log(`${t.name}  --  ${t.description?.split("\n")[0]}`);
    }
  }
  process.exit(0);
}

if (args.length === 0) {
  console.error("usage: mcp-schema.mjs <tool>... | --search <needle>");
  process.exit(1);
}

for (const name of args) {
  const t = byName.get(name);
  if (!t) {
    console.error(`unknown tool: ${name}`);
    continue;
  }
  console.log(`\n===== ${name} =====`);
  if (t.description) console.log(t.description);
  const schema = t.inputSchema ?? {};
  const required = new Set(schema.required ?? []);
  const props = schema.properties ?? {};
  if (Object.keys(props).length === 0) {
    console.log("  (no parameters)");
    continue;
  }
  for (const [key, def] of Object.entries(props)) {
    const mark = required.has(key) ? "*" : " ";
    const type = def.type ?? (def.enum ? "enum" : "?");
    const enumVals = def.enum ? ` [${def.enum.join("|")}]` : "";
    console.log(`${mark} ${key}: ${type}${enumVals}`);
    if (def.description) console.log(`      ${def.description.split("\n").join("\n      ")}`);
    if (def.properties) {
      for (const [sub, subDef] of Object.entries(def.properties)) {
        const subReq = new Set(def.required ?? []);
        const enumSub = subDef.enum ? ` [${subDef.enum.join("|")}]` : "";
        console.log(
          `      ${subReq.has(sub) ? "*" : " "} ${sub}: ${subDef.type ?? "?"}${enumSub}` +
            (subDef.description ? `  -- ${subDef.description}` : ""),
        );
      }
    }
    if (def.items?.properties) {
      for (const [sub, subDef] of Object.entries(def.items.properties)) {
        const subReq = new Set(def.items.required ?? []);
        console.log(
          `      ${subReq.has(sub) ? "*" : " "} [].${sub}: ${subDef.type ?? "?"}` +
            (subDef.description ? `  -- ${subDef.description}` : ""),
        );
      }
    }
  }
}

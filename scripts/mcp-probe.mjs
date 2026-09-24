#!/usr/bin/env node
/**
 * Minimal MCP stdio client for driving the containerized KiCAD server from a
 * shell. Reads one JSON-RPC request per line on stdin, prints one response
 * object per line on stdout.
 *
 * Requests are queued and issued one at a time. The first request must be
 * `initialize`; everything else is held back until that handshake completes
 * and the Python child process has finished its pcbnew warm-up, which takes a
 * couple of seconds. Tool calls fired into that window are answered with
 * "Python process for KiCAD scripting is not running".
 *
 * Usage:
 *   node scripts/mcp-probe.mjs < request.jsonl
 *
 * Deliberately not a general-purpose client: no reconnect, no capability
 * negotiation beyond the bare minimum, no sampling or elicitation handling.
 */
import { spawn } from "node:child_process";
import { createInterface } from "node:readline";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join, resolve } from "node:path";

const REPO_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const WARMUP_MS = Number(process.env.KICAD_MCP_WARMUP_MS ?? 8000);

/**
 * Launch the same container .mcp.json does, so the two cannot drift. The
 * workspace host path in .mcp.json is absolute and machine-specific; re-point
 * it at this checkout unless the caller overrides it.
 */
function containerCommand() {
  const workspace = process.env.KICAD_MCP_WORKSPACE ?? REPO_ROOT;
  const config = JSON.parse(readFileSync(join(REPO_ROOT, ".mcp.json"), "utf8"));
  const [server] = Object.values(config.mcpServers);
  const args = server.args.map((a) => {
    if (a === `${workspace}:/workspace`) return a;
    if (/^[A-Za-z]:[\\/].*:\/workspace$/.test(a)) return `${workspace}:/workspace`;
    return a;
  });
  return { command: server.command, args };
}

const { command, args } = containerCommand();
const child = spawn(command, args, { stdio: ["pipe", "pipe", "inherit"] });

const queue = [];
let pending = null; // id of the request we are waiting on, or null
let ready = false; // warm-up done, safe to issue tool calls
let inputClosed = false;

function maybeFinish() {
  if (!inputClosed || pending !== null || queue.length > 0) return;
  child.stdin.end();
  setTimeout(() => child.kill("SIGTERM"), 2000);
}

function pump() {
  if (pending !== null) return maybeFinish();
  const req = queue[0];
  if (!req) return maybeFinish();
  // `initialize` is the one request that must go out before warm-up finishes --
  // it is what tells us warm-up can start.
  if (!ready && req.method !== "initialize") return maybeFinish();
  queue.shift();
  child.stdin.write(JSON.stringify(req) + "\n");
  if (req.id === undefined) {
    // Notification: no response is coming, so keep draining immediately.
    pump();
  } else {
    pending = req.id;
  }
}

const stdout = createInterface({ input: child.stdout, terminal: false });
stdout.on("line", (line) => {
  let msg;
  try {
    msg = JSON.parse(line);
  } catch {
    process.stderr.write(`[non-json stdout] ${line}\n`);
    return;
  }
  process.stdout.write(line + "\n");
  if (msg.id !== undefined && msg.id === pending) pending = null;
  if (!ready && msg.result?.serverInfo) {
    // The initialize response lands before the Python child process is usable.
    setTimeout(() => {
      ready = true;
      pump();
    }, WARMUP_MS);
  } else {
    pump();
  }
});

let nextId = 1;
let sawNotificationSent = false;
const stdin = createInterface({ input: process.stdin, terminal: false });
stdin.on("line", (line) => {
  const trimmed = line.trim();
  if (!trimmed || trimmed.startsWith("#")) return;
  let req;
  try {
    req = JSON.parse(trimmed);
  } catch (err) {
    process.stderr.write(`[bad input] ${err.message}\n`);
    return;
  }
  if (typeof req === "string") req = { method: req };
  req.jsonrpc = "2.0";
  if (req.id === undefined && req.method !== "notifications/initialized") {
    req.id = nextId++;
  }
  if (req.method === "notifications/initialized") sawNotificationSent = true;
  queue.push(req);
  pump();
});

stdin.on("close", () => {
  inputClosed = true;
  if (!queue.some((r) => r.method === "initialize") && !sawNotificationSent) {
    // No handshake was queued; the caller is driving raw requests, so do not
    // wait on an initialize response that will never arrive.
    ready = true;
    setTimeout(pump, WARMUP_MS);
  }
  maybeFinish();
});

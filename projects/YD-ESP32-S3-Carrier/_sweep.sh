#!/bin/bash
# Best-of-N over the router's strategy knobs.
#
# Every knob swept so far (ORDER, VIA_COST, BLOCK_LIMIT) has been a *strategy*
# choice, not a correctness one: each setting routes a different 20-23 of the 39
# new nets, and nothing so far dominates.  Which means the right move is not to
# hunt for the one true setting but to run several and keep the board that
# actually came out best -- the failures are demonstrably reroutable (every
# straggler routes alone), so a run that gets 24 is a real board, not luck.
#
# CROWD_COST stays at its 0.0 default: the field is correct but prices A* into a
# flood, ~2 min -> >15 for a 39-net pass, which is not worth it for the spread
# it buys on a strip that measures 98 mm of empty B_Cu.
#
# Usage:  bash _sweep.sh
set -u

PY="/c/Program Files/KiCad/10.0/bin/python.exe"
BAK="YD-ESP32-S3-Carrier.kicad_pcb.pre-route595.bak"
BOARD="YD-ESP32-S3-Carrier.kicad_pcb"
BEST_BAK="YD-ESP32-S3-Carrier.kicad_pcb.best.bak"

best=0
best_cfg=""

run() {
  local tag="$1"; shift
  cp "$BAK" "$BOARD"
  local t0=$SECONDS
  local out
  out=$(env PYTHONIOENCODING=utf-8 "$@" ROUNDS=8 timeout 900 "$PY" scripts/route.py 2>&1)
  local dt=$((SECONDS - t0))
  local ok fail
  ok=$(printf '%s\n' "$out" | grep -c "\[OK ")
  fail=$(printf '%s\n' "$out" | grep -c "\[FAIL\]")
  local tr
  tr=$(printf '%s\n' "$out" | grep '^tracks=' || true)
  printf '%-34s OK=%2d FAIL=%2d  %s  (%ds)\n' "$tag" "$ok" "$fail" "$tr" "$dt"
  if [ "$ok" -gt "$best" ]; then
    best=$ok
    best_cfg="$tag"
    cp "$BOARD" "$BEST_BAK"
    printf '   -> new best (%d), board kept\n' "$best"
  fi
}

# The known-good shape first, to confirm the CROWD_COST default change restored
# the fast path's exact result -- if this does not reproduce OK=23 the sweep is
# measuring the wrong thing and the rest of it is noise.
run "VIA=1.0 LIMIT=10 (baseline)"   VIA_COST=1.0 BLOCK_LIMIT=10
run "VIA=1.0 LIMIT=25"              VIA_COST=1.0 BLOCK_LIMIT=25
run "VIA=1.0 LIMIT=50"              VIA_COST=1.0 BLOCK_LIMIT=50
run "VIA=1.0 LIMIT=50 lane-rev"     VIA_COST=1.0 BLOCK_LIMIT=50 ORDER=lane-rev
run "VIA=0.5 LIMIT=50"              VIA_COST=0.5 BLOCK_LIMIT=50
run "VIA=2.0 LIMIT=50"              VIA_COST=2.0 BLOCK_LIMIT=50
run "VIA=1.0 LIMIT=50 long"         VIA_COST=1.0 BLOCK_LIMIT=50 ORDER=long

echo
echo "================ BEST: OK=$best  ($best_cfg) ================"
cp "$BEST_BAK" "$BOARD"

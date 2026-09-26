"""Give the two headers their nets -- the assignment the measurements imply.

The connector carries exactly 40 signals and always did:
      21 ROW + 10 CSEL + 5 GND + 4 +3V3 = 40
COL0..COL9 and PAD1..PAD210 are internal to the array and never left the board,
which is why the FPC had 40 pins for 40 nets and yet the board has 253.

The split below is not the plan's a-priori one: it is read off reach2/reach3.
Every net was measured from both headers, and each went to the side that
actually reaches it -- ROW0-9 and CSEL3/4 hug J1A at 5-31mm, ROW10-15/18-20 and
CSEL0/1/2/5-9 hug J1B at 7-52mm.  The plan's table put ROW10 on the far side
(165mm); the measurement says 5.6mm.  Two pins keep the user's requirement that
ROW3 and ROW5 sit at the two ends of the same connector.

Worst net either side: 53.6mm (J1A/ROW17), 52.2mm (J1B/CSEL2).
"""
import sys, os, json, collections
sys.path.insert(0, os.getcwd())
import pcbnew
import edgeflood as E

OUT = '_pins.kicad_pcb'

J1A = {1: "ROW3", 2: "ROW0", 3: "ROW1", 4: "ROW2", 5: "ROW4", 6: "ROW6",
       7: "ROW7", 8: "ROW8", 9: "ROW9", 10: "ROW13", 11: "ROW14",
       12: "ROW16", 13: "ROW17", 14: "CSEL4", 15: "CSEL3",
       16: "GND", 17: "GND", 18: "GND", 19: "GND", 20: "ROW5"}
J1B = {1: "ROW10", 2: "ROW11", 3: "ROW12", 4: "ROW15", 5: "ROW18",
       6: "ROW19", 7: "ROW20", 8: "CSEL0", 9: "CSEL1", 10: "CSEL2",
       11: "CSEL5", 12: "CSEL6", 13: "CSEL7", 14: "CSEL8", 15: "CSEL9",
       16: "GND", 17: "+3V3", 18: "+3V3", 19: "+3V3", 20: "+3V3"}

want = collections.Counter(list(J1A.values()) + list(J1B.values()))
print("assignment check: %d pin(s)" % sum(want.values()))
for pref, n in (("ROW", 21), ("CSEL", 10), ("GND", 5), ("+3V3", 4)):
    got = sum(c for k, c in want.items() if k.startswith(pref))
    print("   %-6s %2d  (need %d)  %s"
          % (pref, got, n, "ok" if got == n else "*** MISMATCH ***"))

board = pcbnew.LoadBoard('_rip3.kicad_pcb')
GRAVE = []

missing = set()
for ref, table in (("J1A", J1A), ("J1B", J1B)):
    fp = [f for f in board.GetFootprints() if f.GetReference() == ref][0]
    done = 0
    for p in fp.Pads():
        num = int(p.GetNumber())
        name = table.get(num)
        if not name:
            continue
        net = board.FindNet(name)
        if net is None:
            missing.add(name)
            continue
        p.SetNet(net)
        done += 1
    print("%s: %d pad(s) netted" % (ref, done))

if missing:
    print("*** nets not found on the board: %s" % sorted(missing))

pcbnew.SaveBoard(OUT, board)
print("\nsaved to %s" % OUT)

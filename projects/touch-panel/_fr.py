"""Specctra DSN/SES bridge around pcbnew.

KiCad 10 dropped `kicad-cli pcb export dsn`, so the autorouter handoff has to
go through pcbnew's own ExportSpecctraDSN / ImportSpecctraSES.

  python _fr.py dsn BOARD OUT.dsn
  python _fr.py ses BOARD IN.ses OUT.kicad_pcb
"""
import sys

import pcbnew

args = sys.argv[1:]
mode, board, other = args[0], args[1], args[2]
dest = args[3] if len(args) > 3 else None

b = pcbnew.LoadBoard(board)

if mode == "dsn":
    ok = pcbnew.ExportSpecctraDSN(b, other)
    print("ExportSpecctraDSN -> %s : %s" % (other, ok))
elif mode == "ses":
    pcbnew.ImportSpecctraSES(b, other)
    b.Save(dest)
    print("ImportSpecctraSES <- %s ; saved %s" % (other, dest))
    print("tracks now %d" % len(list(b.GetTracks())))
else:
    raise SystemExit("mode must be dsn or ses")

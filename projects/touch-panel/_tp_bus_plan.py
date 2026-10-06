
# --------------------------------------------------------------------------
# THE GROUP A BUS  (this file = route-open-nets.py's engine + this driver)
#
# The 595s' control and power bus is 25 of the 59 unconnected entries.  It has
# almost no copper, and it must run vertically past U1..U4 to reach pads 10-16
# of each register.  _tp_ripcorr.py proved the corridors for it exist but are
# occupied by the *other* broken group; _ripped.kicad_pcb is that board with
# Group B's corridor copper removed, and _tp_verify.py confirmed both corridors
# then hold one F vertical and one B vertical.
#
# Each net is routed as a CHAIN in the order listed: link k goes from endpoint
# k to the copper already laid for endpoints < k.  Goals are restricted to that
# copper, so the chain cannot jump ahead -- without that, a run from U2.11 can
# reach U3.11 just as cheaply as U1.11 and the chain skips a register.
#
# The register pads are listed in y order and the J1 pad LAST: the short
# register-to-register hops claim the corridor first and the single long run
# from the bottom edge lands in a board that already carries the bus, which is
# the easier search.  The five nets are routed in order of how constrained
# their escape is, not alphabetically.
#
#   python _tp_bus.py _ripped.kicad_pcb --dry-run
#   python _tp_bus.py _ripped.kicad_pcb --lock
# --------------------------------------------------------------------------

END = [
    ("IO10", [("U1", "11"), ("U2", "11"), ("U3", "11"), ("U4", "11"),
              ("J1", "2")]),
    ("IO11", [("U1", "12"), ("U2", "12"), ("U3", "12"), ("U4", "12"),
              ("J1", "3")]),
    ("IO12", [("U1", "13"), ("U2", "13"), ("U3", "13"), ("U4", "13"),
              ("J1", "4")]),
    ("IO9",  [("U1", "14"), ("J1", "1")]),
    ("+3V3", [("U1", "10"), ("U1", "16"), ("C1", "1"),
              ("U2", "10"), ("U2", "16"), ("C2", "1"),
              ("U3", "10"), ("U3", "16"), ("C3", "1"),
              ("U4", "10"), ("U4", "16"), ("C4", "1"),
              ("J1", "37")]),
]


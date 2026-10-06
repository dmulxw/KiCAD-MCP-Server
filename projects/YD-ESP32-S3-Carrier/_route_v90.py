"""Run route.py's incremental pass against a scratch board, for the net set the
moved sockets and panel headers left behind.

main() reads BOARD and ONLY from module globals at call time, so rebinding them
here is enough -- no fork of the router, and nothing that can drift out of sync.

  python _route_v90.py [board.kicad_pcb]
"""
import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SCRATCH = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "_v90.kicad_pcb")

spec = importlib.util.spec_from_file_location("rt", os.path.join(HERE, "scripts",
                                                                "route.py"))
rt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rt)

# Every net that owns a pad on J1, J2, J8 or J10 (printed by move_sockets.py).
# GND is absent on purpose -- the pour carries it, exactly as on the rest of the
# board.
rt.ONLY = [
    "+3V3", "+5V",
    "BTN_ACT", "BTN_RST", "BTN_VOL_DN", "BTN_VOL_UP",
    "I2C_SCL", "I2C_SDA",
    "I2S_BCK", "I2S_DI", "I2S_DO", "I2S_MCK", "I2S_WS",
    "IO9", "IO10", "IO11", "IO12", "IO13", "IO14", "IO17", "IO18",
    "IO38", "IO39", "IO42", "IO43", "IO44", "IO48",
    "LCD_CS", "LCD_DC", "LCD_RST", "LCD_SCK", "LCD_SDA",
]
rt.BOARD = SCRATCH

# ONLY_SET=+5V,BTN_RST,IO44 routes just those.  A net whose leftmost pad is one
# that moved loses its old copper to `conn &= reach` and is laid from scratch, so
# a net like that has to go down on an empty part of the board -- before the other
# 29 nets have taken the room it is trying to cross.
_only = os.environ.get("ONLY_SET")
if _only:
    rt.ONLY = _only.split(",")

print("router aimed at", rt.BOARD)
print("%d net(s) in ONLY" % len(rt.ONLY))
rt.main()

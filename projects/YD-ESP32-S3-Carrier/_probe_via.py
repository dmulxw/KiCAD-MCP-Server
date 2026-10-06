import pcbnew
b = pcbnew.LoadBoard("YD-ESP32-S3-Carrier.kicad_pcb")
via = None
for t in b.GetTracks():
    if isinstance(t, pcbnew.PCB_VIA):
        via = t; break
if via is None:
    print("no vias on board"); raise SystemExit
print("found via net=%r pos=%s" % (via.GetNetname(), via.GetPosition()))
names = [n for n in dir(via) if "Width" in n or "Drill" in n]
print("width/drill methods:", names)
for n in ("GetFrontWidth","GetBackWidth","GetDrillValue","GetViaType"):
    if hasattr(via, n):
        try: print("  %s = %r" % (n, getattr(via, n)()))
        except Exception as e: print("  %s -> %s" % (n, e))
print("  GetWidth(F_Cu) = %r" % (via.GetWidth(pcbnew.F_Cu),))
print("  GetWidth(B_Cu) = %r" % (via.GetWidth(pcbnew.B_Cu),))

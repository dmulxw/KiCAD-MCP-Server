"""Is the empty bay poured and then discarded as an isolated island?
Refill with island removal off and re-measure the same probe points."""
import pcbnew
BOARD = (r"D:\source\repos\KiCAD-MCP-Server\projects\YD-ESP32-S3-Carrier"
         r"\YD-ESP32-S3-Carrier.kicad_pcb")
b = pcbnew.LoadBoard(BOARD)
mm = pcbnew.ToMM
print([n for n in dir(pcbnew) if "ISLAND" in n.upper()], flush=True)
z = [zz for zz in b.Zones() if not zz.GetIsRuleArea() and zz.GetLayer() == pcbnew.F_Cu][0]
print("island removal mode:", z.GetIslandRemovalMode(), flush=True)
print("min island area:", mm(mm(z.GetMinIslandArea())) if hasattr(z, "GetMinIslandArea") else "n/a", flush=True)

PROBE = [(20, 20), (20, 26), (28, 28), (14, 22), (32, 24)]
def report(tag):
    print(f"  {tag}", flush=True)
    for lay, nm in ((pcbnew.F_Cu, "F.Cu"), (pcbnew.B_Cu, "B.Cu")):
        zz = [q for q in b.Zones() if not q.GetIsRuleArea() and q.GetLayer() == lay][0]
        hits = [p for p in PROBE
                if zz.HitTestFilledArea(lay, pcbnew.VECTOR2I(pcbnew.FromMM(p[0]), pcbnew.FromMM(p[1])))]
        print(f"    {nm}: {len(hits)}/{len(PROBE)} probes filled  area={zz.GetFilledPolysList(lay).Area()/1e12:.1f}",
              flush=True)

report("as found on disk")
for zz in b.Zones():
    if not zz.GetIsRuleArea():
        zz.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_NEVER)
pcbnew.ZONE_FILLER(b).Fill(b.Zones())
report("after refill with island removal = NEVER")

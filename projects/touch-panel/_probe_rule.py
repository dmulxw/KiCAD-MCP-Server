import pcbnew, json
b=pcbnew.LoadBoard("touch-panel.kicad_pcb")
ds=b.GetDesignSettings()
try:
    nc=ds.GetNetClasses()
    for name in nc.GetNetClassNames() if hasattr(nc,'GetNetClassNames') else []:
        c=nc.GetNetClass(name)
        print("netclass %-12s clearance=%.3f track=%.3f via=%.3f"%(name,
            c.GetClearance()/1e6, c.GetTrackWidth()/1e6, c.GetViaDiameter()/1e6))
except Exception as e:
    print("netclass walk failed:",e)
print("default clearance = %.3f mm"%(ds.GetDefault().GetClearance()/1e6))

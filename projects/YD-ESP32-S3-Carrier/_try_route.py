import importlib.util, os, sys, shutil, io, contextlib
order, crowd, vcost, spread, out = sys.argv[1:6]
os.environ["ORDER"] = order
os.environ["CROWD_COST"] = crowd
os.environ["VIA_COST"] = vcost
os.environ["CROWD_SPREAD"] = spread
spec = importlib.util.spec_from_file_location("rt", "scripts/route.py")
rt = importlib.util.module_from_spec(spec); spec.loader.exec_module(rt)
shutil.copyfile("YD-ESP32-S3-Carrier.kicad_pcb.pre-route595.bak", out)
rt.BOARD = os.path.abspath(out)
buf = io.StringIO()
try:
    with contextlib.redirect_stdout(buf):
        rt.main()
except SystemExit:
    pass
lines = buf.getvalue().splitlines()
fails = [l.split()[1] for l in lines if "[FAIL]" in l]
oks   = [l.split()[1] for l in lines if "[OK " in l]
print("ORDER=%-8s CROWD=%-4s VIA=%-4s SPREAD=%-4s -> ok %2d  fail %2d  %s"
      % (order, crowd, vcost, spread, len(oks), len(fails), " ".join(sorted(fails))))

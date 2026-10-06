import importlib.util, os, sys, io, contextlib
os.environ["ONLY_SET"] = sys.argv[2]
os.environ.setdefault("ORDER", os.environ.get("ORDER", "span"))
spec = importlib.util.spec_from_file_location("rt", "scripts/route.py")
rt = importlib.util.module_from_spec(spec); spec.loader.exec_module(rt)
rt.BOARD = os.path.abspath(sys.argv[1])
buf = io.StringIO()
try:
    with contextlib.redirect_stdout(buf):
        rt.main()
except SystemExit:
    pass
lines = buf.getvalue().splitlines()
fails = sorted(l.split()[1] for l in lines if "[FAIL]" in l)
oks = len([l for l in lines if "[OK " in l])
print("incremental: ok %d  fail %d" % (oks, len(fails)))
print("FAILED:", " ".join(fails))

import importlib.util, os, sys, shutil, io, contextlib
spec = importlib.util.spec_from_file_location("pr", "scripts/pour.py")
pr = importlib.util.module_from_spec(spec); spec.loader.exec_module(pr)
out = os.path.abspath(sys.argv[1])
shutil.copyfile(sys.argv[2], out)
pr.BOARD = out
buf = io.StringIO()
try:
    with contextlib.redirect_stdout(buf):
        pr.main()
except SystemExit:
    pass
print(buf.getvalue()[-1500:])

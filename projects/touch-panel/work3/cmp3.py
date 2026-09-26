import json, sys, collections

def load(p):
    with open(p, encoding='utf-8') as f:
        return json.load(f)

def key(it):
    p = it.get('pos')
    if isinstance(p, dict):
        xy = "%.3f,%.3f" % (p.get('x', 0), p.get('y', 0))
    else:
        xy = str(p)
    return (it.get('type'), it.get('description', '')[:60], xy)

base = load(sys.argv[1])
new = load(sys.argv[2])

def tally(d):
    c = collections.Counter()
    for it in d.get('violations', []):
        c[it.get('type')] += 1
    return c

print("基线", sys.argv[1], ":", dict(tally(base)), "unconnected", len(base.get('unconnected_items', [])))
print("新板", sys.argv[2], ":", dict(tally(new)), "unconnected", len(new.get('unconnected_items', [])))

bs = {key(it) for it in base.get('violations', [])}
added = [it for it in new.get('violations', []) if key(it) not in bs]
print("\n新增 %d 条:" % len(added))
for it in added:
    print("  [%s] %s" % (it.get('type'), it.get('description')))
    for x in it.get('items', []):
        print("      - %s" % x.get('description'))

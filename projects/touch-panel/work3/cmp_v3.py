import json, io, collections, sys
base = json.load(io.open('_drc_base_now.json', encoding='utf-8'))
bc = collections.Counter(v['type'] for v in base['violations'])
def fmt(it):
    d = it.get('description','')
    p = it.get('pos')
    return "%s @(%.4f,%.4f)" % (d, p['x'], p['y']) if isinstance(p, dict) else "%s @%s" % (d, p)
for tag in sys.argv[1:]:
    new = json.load(io.open(tag + '_drc.json', encoding='utf-8'))
    nc = collections.Counter(v['type'] for v in new['violations'])
    nt = {t: nc[t]-bc.get(t,0) for t in nc if nc[t]-bc.get(t,0) > 0}
    print("=== %-5s violations %d  unconnected %d   new types %s"
          % (tag, len(new['violations']), len(new.get('unconnected_items',[])), nt))

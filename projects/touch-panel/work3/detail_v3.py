import json, io, collections
base = json.load(io.open('_drc_base_now.json', encoding='utf-8'))
bc = collections.Counter(v['type'] for v in base['violations'])
new = json.load(io.open('_v3_drc.json', encoding='utf-8'))
nc = collections.Counter(v['type'] for v in new['violations'])
nt = {t: nc[t]-bc.get(t,0) for t in nc if nc[t]-bc.get(t,0) > 0}
def fmt(it):
    d = it.get('description','')
    p = it.get('pos')
    return "%s @(%.4f,%.4f)" % (d, p['x'], p['y']) if isinstance(p, dict) else "%s @%s" % (d, p)
for v in new['violations']:
    if v['type'] in nt:
        print("\n%-16s %s" % (v['type'], v.get('description','')))
        for it in v.get('items', []):
            print("     - %s" % fmt(it))

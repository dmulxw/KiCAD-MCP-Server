import json, io, collections
base = json.load(io.open('_drc_base_now.json', encoding='utf-8'))
new  = json.load(io.open('_v2_drc.json', encoding='utf-8'))
bc = collections.Counter(v['type'] for v in base['violations'])
nc = collections.Counter(v['type'] for v in new['violations'])
newtypes = {t: nc[t]-bc.get(t,0) for t in nc if nc[t]-bc.get(t,0) > 0}
print("new violation types:", newtypes)

def fmt(it):
    d = it.get('description','')
    p = it.get('pos')
    if isinstance(p, dict):
        return "%s @(%.4f,%.4f)" % (d, p.get('x',0), p.get('y',0))
    return "%s @%s" % (d, p)

for v in new['violations']:
    if v['type'] in newtypes:
        print("\n%-18s %s" % (v['type'], v.get('description','')))
        for it in v.get('items', []):
            print("     - %s" % fmt(it))

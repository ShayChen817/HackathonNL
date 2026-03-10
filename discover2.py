import requests, json

session = requests.Session()
session.auth = ('group_6', 'Q-M7L77o3G@j')
session.headers.update({'Accept': 'application/json'})
API = 'https://next.collibra.com/rest/2.0'

# Active Tester Flag measure relations
print("=== ACTIVE TESTER FLAG RELATIONS ===")
flag_id = '019c9f78-2633-7377-9050-c1b3d84eb68d'
for direction in ['sourceId', 'targetId']:
    resp = session.get(API + '/relations', params={direction: flag_id, 'limit': 50})
    for r in resp.json().get('results', []):
        src = r.get('source', {})
        tgt = r.get('target', {})
        sd = src.get('domain', {}).get('name', '')
        td = tgt.get('domain', {}).get('name', '')
        print("  %s [%s] --> %s [%s]" % (src.get('name',''), sd, tgt.get('name',''), td))

print()
print("=== PHYSICAL COLUMNS FOR KEY TABLES ===")
ctx = json.load(open('governed_context.json', encoding='utf-8'))
for key in sorted(ctx['column_map'].keys()):
    info = ctx['column_map'][key]
    if any(t in key for t in ['prt_mtrc', 'tkt_itm', 'prj_hdr', 'qa_sat', 'act_stat']):
        bt = info.get('business_term', '')
        desc = info.get('physical_description', '')
        print("  %-35s BT=%-30s Desc=%s" % (key, bt, desc[:100]))

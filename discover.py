"""Fetch governed definitions from Collibra API - one-time data discovery."""
import requests
import json
from bs4 import BeautifulSoup

session = requests.Session()
session.auth = ('group_6', 'Q-M7L77o3G@j')
session.headers.update({'Accept': 'application/json'})
API = 'https://next.collibra.com/rest/2.0'

def strip(val):
    if val is None:
        return ""
    if not isinstance(val, str):
        return str(val)
    try:
        return BeautifulSoup(val, "lxml").get_text(separator=" ").strip()
    except:
        return str(val)

# 1. Active Tester business term
print("=" * 80)
print("ACTIVE TESTER — Business Term (Asset ID: 0198c234-11fe-73ff-be9b-c91312850031)")
print("=" * 80)
resp = session.get(f'{API}/attributes', params={'assetId': '0198c234-11fe-73ff-be9b-c91312850031', 'limit': 50})
for a in resp.json().get('results', []):
    tname = a.get('type', {}).get('name', '?')
    val = strip(a.get('value', ''))
    print(f"  [{tname}]: {val}")

# 2. All Measures from Metrics Catalog
print("\n" + "=" * 80)
print("ALL MEASURES — Metrics Catalog (Domain: 019c9f76-2a44-7242-8f7d-cf40e16f270b)")
print("=" * 80)
resp = session.get(f'{API}/assets', params={'domainId': '019c9f76-2a44-7242-8f7d-cf40e16f270b', 'limit': 50})
measures = resp.json().get('results', [])
for m in measures:
    print(f"\n--- MEASURE: {m['displayName']} (id={m['id']}) ---")
    attrs = session.get(f'{API}/attributes', params={'assetId': m['id'], 'limit': 50}).json().get('results', [])
    for a in attrs:
        tname = a.get('type', {}).get('name', '?')
        val = strip(a.get('value', ''))
        print(f"  [{tname}]: {val}")

# 3. Get Z_PRJ_STAT unique values to know what "ongoing" looks like
print("\n" + "=" * 80)
print("PROJECT STATUS VALUES (Z_PRJ_STAT in zcc_prj_hdr)")
print("=" * 80)
import delta_sharing, pandas as pd
df = delta_sharing.load_as_pandas("config.json#centercode_share.centercode.zcc_prj_hdr", limit=1000)
print(f"  Unique Z_PRJ_STAT values: {df['Z_PRJ_STAT'].value_counts().to_dict()}")

# 4. Get Z_ENG_ST unique values 
print("\n" + "=" * 80)
print("ENGAGEMENT STATUS VALUES (Z_ENG_ST in zcc_act_stat)")
print("=" * 80)
df2 = delta_sharing.load_as_pandas("config.json#centercode_share.centercode.zcc_act_stat", limit=10000)
print(f"  Unique Z_ENG_ST values: {df2['Z_ENG_ST'].value_counts().to_dict()}")

# 5. Active Tester Flag measure - get relations to see column mapping
print("\n" + "=" * 80)
print("RELATIONS FOR ACTIVE TESTER (tracing to physical columns)")
print("=" * 80)
# Get relations from Active Tester business term
resp = session.get(f'{API}/relations', params={'sourceId': '0198c234-11fe-73ff-be9b-c91312850031', 'limit': 50})
for r in resp.json().get('results', []):
    src = r.get('source', {})
    tgt = r.get('target', {})
    print(f"  {src.get('name','')} [{src.get('domain',{}).get('name','')}] --> {tgt.get('name','')} [{tgt.get('domain',{}).get('name','')}]")

resp = session.get(f'{API}/relations', params={'targetId': '0198c234-11fe-73ff-be9b-c91312850031', 'limit': 50})
for r in resp.json().get('results', []):
    src = r.get('source', {})
    tgt = r.get('target', {})
    print(f"  {src.get('name','')} [{src.get('domain',{}).get('name','')}] --> {tgt.get('name','')} [{tgt.get('domain',{}).get('name','')}]")

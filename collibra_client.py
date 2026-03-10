"""
collibra_client.py — Fetch all governed context from Collibra REST API.

Retrieves:
  - Business Terms (definitions, synonyms)
  - Measures / Metrics (calculation rules)
  - Logical Layer (Data Entities, Data Attributes)
  - Physical Layer (Schemas, Tables, Columns + descriptions)
  - Relations between all layers (the semantic graph)
"""

import os
import time
import json
import re
import requests
from dotenv import load_dotenv
from bs4 import BeautifulSoup

load_dotenv()

BASE_URL = os.getenv("COLLIBRA_BASE_URL", "https://next.collibra.com")
API_ROOT = f"{BASE_URL}/rest/2.0"

# Domain IDs from the hackathon
DOMAINS = {
    "glossary":       "019c907a-40d8-74d9-84c5-83abd6ae4d4e",
    "metrics":        "019c9f76-2a44-7242-8f7d-cf40e16f270b",
    "logical":        "019c9e6d-9079-72e3-b0f9-e64c49a57ac9",
    "physical":       "019c9e17-b6f2-725e-9181-dbda44044df9",
}


def _session() -> requests.Session:
    """Create an authenticated session."""
    s = requests.Session()
    s.auth = (os.getenv("COLLIBRA_USERNAME"), os.getenv("COLLIBRA_PASSWORD"))
    s.headers.update({"Accept": "application/json"})
    return s


def strip_html(text) -> str:
    """Remove HTML tags from Collibra attribute values."""
    if text is None:
        return ""
    if not isinstance(text, str):
        return str(text)
    if not text:
        return ""
    return BeautifulSoup(text, "lxml").get_text(separator=" ").strip()


def _paginated_get(session: requests.Session, endpoint: str, params: dict = None) -> list:
    """Fetch all pages from a paginated Collibra endpoint."""
    if params is None:
        params = {}
    params.setdefault("limit", 1000)
    all_results = []
    while True:
        resp = session.get(f"{API_ROOT}/{endpoint}", params=params)
        resp.raise_for_status()
        data = resp.json()
        results = data.get("results", [])
        all_results.extend(results)
        next_cursor = data.get("nextCursor", "")
        if not next_cursor or len(results) == 0:
            break
        params["cursor"] = next_cursor
        time.sleep(0.15)  # be kind to rate limits
    return all_results


# ── Domain-level helpers ──────────────────────────────────────────────

def get_asset_types(session: requests.Session, domain_id: str) -> list:
    """Discover asset types in a domain."""
    resp = session.get(f"{API_ROOT}/assignments/domain/{domain_id}/assetTypes")
    resp.raise_for_status()
    return resp.json()


def get_assets(session: requests.Session, domain_id: str, type_id: str = None) -> list:
    """List all assets in a domain, optionally filtered by type."""
    params = {"domainId": domain_id, "excludeMeta": "true", "typeInheritance": "true"}
    if type_id:
        params["typeId"] = type_id
    return _paginated_get(session, "assets", params)


def get_attributes(session: requests.Session, asset_id: str) -> list:
    """Get all attributes (Definition, Description, Synonym, etc.) for an asset."""
    return _paginated_get(session, "attributes", {"assetId": asset_id})


def get_relations(session: requests.Session, asset_id: str, direction: str = "both") -> list:
    """Get relations for an asset. direction: 'source', 'target', or 'both'."""
    results = []
    if direction in ("source", "both"):
        results.extend(_paginated_get(session, "relations", {"sourceId": asset_id}))
    if direction in ("target", "both"):
        results.extend(_paginated_get(session, "relations", {"targetId": asset_id}))
    return results


# ── Full context extraction ───────────────────────────────────────────

def extract_full_context() -> dict:
    """
    Pull all governed context from Collibra and return a structured dict.
    
    Returns:
        {
            "business_terms": [...],
            "measures": [...],
            "logical_assets": [...],
            "physical_assets": [...],
            "relations": [...],
            "column_map": { "table.column": { description, business_term, ... } }
        }
    """
    session = _session()
    context = {
        "business_terms": [],
        "measures": [],
        "logical_assets": [],
        "physical_assets": [],
        "relations": [],
        "column_map": {},
    }

    print("📖 Fetching Business Terms from Glossary...")
    bt_assets = get_assets(session, DOMAINS["glossary"])
    for asset in bt_assets:
        attrs = get_attributes(session, asset["id"])
        term = {
            "id": asset["id"],
            "name": asset.get("displayName", asset.get("name", "")),
            "type": asset.get("type", {}).get("name", ""),
            "status": asset.get("status", {}).get("name", ""),
            "definition": "",
            "description": "",
            "synonyms": [],
            "attributes": {},
        }
        for attr in attrs:
            attr_type = attr.get("type", {}).get("name", "")
            val = strip_html(attr.get("value", ""))
            if attr_type == "Definition":
                term["definition"] = val
            elif attr_type == "Description":
                term["description"] = val
            elif attr_type == "Synonym":
                term["synonyms"].append(val)
            else:
                term["attributes"][attr_type] = val
        context["business_terms"].append(term)
        time.sleep(0.1)
    print(f"  ✅ {len(context['business_terms'])} business terms loaded")

    print("📊 Fetching Measures from Metrics Catalog...")
    m_assets = get_assets(session, DOMAINS["metrics"])
    for asset in m_assets:
        attrs = get_attributes(session, asset["id"])
        measure = {
            "id": asset["id"],
            "name": asset.get("displayName", asset.get("name", "")),
            "type": asset.get("type", {}).get("name", ""),
            "status": asset.get("status", {}).get("name", ""),
            "definition": "",
            "description": "",
            "attributes": {},
        }
        for attr in attrs:
            attr_type = attr.get("type", {}).get("name", "")
            val = strip_html(attr.get("value", ""))
            if attr_type == "Definition":
                measure["definition"] = val
            elif attr_type == "Description":
                measure["description"] = val
            else:
                measure["attributes"][attr_type] = val
        context["measures"].append(measure)
        time.sleep(0.1)
    print(f"  ✅ {len(context['measures'])} measures loaded")

    print("🔗 Fetching Logical Layer...")
    l_assets = get_assets(session, DOMAINS["logical"])
    for asset in l_assets:
        attrs = get_attributes(session, asset["id"])
        logical = {
            "id": asset["id"],
            "name": asset.get("displayName", asset.get("name", "")),
            "type": asset.get("type", {}).get("name", ""),
            "definition": "",
            "description": "",
        }
        for attr in attrs:
            attr_type = attr.get("type", {}).get("name", "")
            val = strip_html(attr.get("value", ""))
            if attr_type == "Definition":
                logical["definition"] = val
            elif attr_type == "Description":
                logical["description"] = val
        context["logical_assets"].append(logical)
        time.sleep(0.1)
    print(f"  ✅ {len(context['logical_assets'])} logical assets loaded")

    print("🗄️ Fetching Physical Layer (schemas, tables, columns)...")
    p_assets = get_assets(session, DOMAINS["physical"])
    for asset in p_assets:
        attrs = get_attributes(session, asset["id"])
        physical = {
            "id": asset["id"],
            "name": asset.get("displayName", asset.get("name", "")),
            "type": asset.get("type", {}).get("name", ""),
            "definition": "",
            "description": "",
        }
        for attr in attrs:
            attr_type = attr.get("type", {}).get("name", "")
            val = strip_html(attr.get("value", ""))
            if attr_type == "Definition":
                physical["definition"] = val
            elif attr_type == "Description":
                physical["description"] = val
        context["physical_assets"].append(physical)
        time.sleep(0.1)
    print(f"  ✅ {len(context['physical_assets'])} physical assets loaded")

    # ── Relations: build the semantic graph ──
    print("🌐 Fetching relations across all layers...")
    all_asset_ids = set()
    for layer in [context["business_terms"], context["measures"],
                  context["logical_assets"], context["physical_assets"]]:
        for a in layer:
            all_asset_ids.add(a["id"])

    seen_relation_ids = set()
    for asset_id in all_asset_ids:
        rels = get_relations(session, asset_id)
        for r in rels:
            rid = r.get("id", "")
            if rid not in seen_relation_ids:
                seen_relation_ids.add(rid)
                context["relations"].append({
                    "id": rid,
                    "type": r.get("type", {}).get("name", ""),
                    "source_id": r.get("source", {}).get("id", ""),
                    "source_name": r.get("source", {}).get("name", ""),
                    "source_domain": r.get("source", {}).get("domain", {}).get("name", ""),
                    "target_id": r.get("target", {}).get("id", ""),
                    "target_name": r.get("target", {}).get("name", ""),
                    "target_domain": r.get("target", {}).get("domain", {}).get("name", ""),
                })
        time.sleep(0.1)
    print(f"  ✅ {len(context['relations'])} unique relations loaded")

    # ── Build column map: Business Term → Logical → Physical Column ──
    print("🗺️ Building column map (business term → physical column)...")
    _build_column_map(context)

    return context


def _build_column_map(context: dict):
    """
    Build a mapping from physical columns to their governed meaning.
    Uses the two-hop pattern: Business Term → Logical → Physical
    """
    # Index assets by ID for quick lookup
    all_assets = {}
    for layer in ["business_terms", "measures", "logical_assets", "physical_assets"]:
        for a in context[layer]:
            all_assets[a["id"]] = a

    # Index relations
    source_to_targets = {}  # source_id -> list of (target_id, target_domain)
    target_to_sources = {}  # target_id -> list of (source_id, source_domain)
    for r in context["relations"]:
        sid, tid = r["source_id"], r["target_id"]
        source_to_targets.setdefault(sid, []).append({
            "id": tid, "name": r["target_name"], "domain": r["target_domain"]
        })
        target_to_sources.setdefault(tid, []).append({
            "id": sid, "name": r["source_name"], "domain": r["source_domain"]
        })

    # For each physical column, trace back through logical to business
    for p in context["physical_assets"]:
        if p["type"] != "Column":
            continue

        col_info = {
            "physical_name": p["name"],
            "physical_description": p.get("description", ""),
            "logical_name": "",
            "business_term": "",
            "business_definition": "",
            "measure_name": "",
            "measure_definition": "",
            "table_name": "",
        }

        # Find which table this column belongs to (via relations)
        # Column could be target of a table's outbound relation, or source pointing to table
        for link in target_to_sources.get(p["id"], []):
            linked = all_assets.get(link["id"], {})
            if linked.get("type") == "Table":
                col_info["table_name"] = linked["name"]
                break
        for link in source_to_targets.get(p["id"], []):
            linked = all_assets.get(link["id"], {})
            if linked.get("type") == "Table":
                col_info["table_name"] = linked["name"]
                break

        # Find logical asset linked to this column
        logical_id = None
        for link in target_to_sources.get(p["id"], []):
            linked = all_assets.get(link["id"], {})
            if linked.get("type") in ("Data Attribute", "Data Entity"):
                col_info["logical_name"] = linked["name"]
                logical_id = link["id"]
                break
        if not logical_id:
            for link in source_to_targets.get(p["id"], []):
                linked = all_assets.get(link["id"], {})
                if linked.get("type") in ("Data Attribute", "Data Entity"):
                    col_info["logical_name"] = linked["name"]
                    logical_id = link["id"]
                    break

        # Find business term linked to the logical asset
        if logical_id:
            for link in target_to_sources.get(logical_id, []):
                linked = all_assets.get(link["id"], {})
                if linked.get("type") == "Business Term":
                    col_info["business_term"] = linked["name"]
                    col_info["business_definition"] = linked.get("definition", "")
                    break
            if not col_info["business_term"]:
                for link in source_to_targets.get(logical_id, []):
                    linked = all_assets.get(link["id"], {})
                    if linked.get("type") == "Business Term":
                        col_info["business_term"] = linked["name"]
                        col_info["business_definition"] = linked.get("definition", "")
                        break
            # Also check for measures
            for link in target_to_sources.get(logical_id, []):
                linked = all_assets.get(link["id"], {})
                if linked.get("type") == "Measure":
                    col_info["measure_name"] = linked["name"]
                    col_info["measure_definition"] = linked.get("definition", "")
                    break

        key = f"{col_info['table_name']}.{p['name']}" if col_info["table_name"] else p["name"]
        context["column_map"][key] = col_info

    print(f"  ✅ Column map built: {len(context['column_map'])} columns mapped")


def save_context(context: dict, path: str = "governed_context.json"):
    """Save the full context to a JSON file for reuse."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(context, f, indent=2, ensure_ascii=False)
    print(f"💾 Context saved to {path}")


def load_context(path: str = "governed_context.json") -> dict:
    """Load previously saved context."""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


if __name__ == "__main__":
    ctx = extract_full_context()
    save_context(ctx)
    print(f"\nSummary:")
    print(f"  Business Terms: {len(ctx['business_terms'])}")
    print(f"  Measures:       {len(ctx['measures'])}")
    print(f"  Logical Assets: {len(ctx['logical_assets'])}")
    print(f"  Physical Assets:{len(ctx['physical_assets'])}")
    print(f"  Relations:      {len(ctx['relations'])}")
    print(f"  Column Map:     {len(ctx['column_map'])} columns")

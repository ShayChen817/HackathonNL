"""
app.py — Flask web server for Ask Your Data frontend.
Exposes the RAG pipeline and deterministic engine as REST APIs.
"""

import os
import json
import threading
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__, static_folder="frontend", static_url_path="")
CORS(app)

# ── Lazy-loaded globals ───────────────────────────────────────────────
_context = None
_table_schemas = None
_dataframes = None
_init_lock = threading.Lock()
_init_done = False
_init_error = None

def _initialize():
    global _context, _table_schemas, _dataframes, _init_done, _init_error
    try:
        from collibra_client import load_context, extract_full_context, save_context
        from data_loader import load_all_tables, get_table_schemas

        ctx_path = "governed_context.json"
        if os.path.exists(ctx_path):
            with open(ctx_path, "r", encoding="utf-8") as f:
                _context = json.load(f)
        else:
            raw = extract_full_context()
            save_context(raw, ctx_path)
            _context = raw

        _dataframes = load_all_tables()
        _table_schemas = get_table_schemas()
        _init_done = True
    except Exception as e:
        _init_error = str(e)
        _init_done = True


def get_initialized():
    global _init_done
    with _init_lock:
        if not _init_done and not _init_error:
            _initialize()
    return _init_done, _init_error


# ── Routes ────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return send_from_directory("frontend", "index.html")


@app.route("/api/status")
def status():
    """Health check — also returns init state."""
    done, err = get_initialized()
    tables = list(_dataframes.keys()) if _dataframes else []
    terms_count = len(_context.get("business_terms", [])) if _context else 0
    return jsonify({
        "ready": done and not err,
        "error": err,
        "tables_loaded": tables,
        "terms_count": terms_count,
    })


@app.route("/api/ask", methods=["POST"])
def ask():
    """RAG pipeline — governed AI answer."""
    done, err = get_initialized()
    if not done or err:
        return jsonify({"error": f"System initializing: {err}"}), 503

    body = request.get_json(force=True)
    question = (body.get("question") or "").strip()
    if not question:
        return jsonify({"error": "question is required"}), 400

    try:
        from ask_your_data import ask_with_context
        result = ask_with_context(question, _context, _table_schemas)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/active-testers")
def active_testers():
    """Deterministic engine — 100% governed active tester count."""
    done, err = get_initialized()
    if not done or err:
        return jsonify({"error": f"System initializing: {err}"}), 503
    try:
        from deterministic_engine import DeterministicEngine
        engine = DeterministicEngine()
        result = engine.count_active_testers(ongoing_only=True)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/projects/stats")
def project_stats():
    """Quick project status breakdown."""
    done, err = get_initialized()
    if not done or err:
        return jsonify({"error": f"System initializing: {err}"}), 503
    try:
        df = _dataframes["zcc_prj_hdr"]
        counts = df["Z_PRJ_STAT"].value_counts().to_dict()
        total = int(df.shape[0])
        return jsonify({"total": total, "by_status": counts})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/tables")
def list_tables():
    """List available tables and row counts."""
    done, err = get_initialized()
    if not done or err:
        return jsonify({"error": f"System initializing: {err}"}), 503
    try:
        info = {name: {"rows": schema["row_count"], "columns": schema["columns"]}
                for name, schema in _table_schemas.items()}
        return jsonify(info)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/terms")
def list_terms():
    """List governed business terms from Collibra."""
    done, err = get_initialized()
    if not done or err:
        return jsonify({"error": f"System initializing: {err}"}), 503
    try:
        terms = [{"name": t["name"], "definition": t.get("definition", "")}
                 for t in _context.get("business_terms", [])]
        return jsonify(terms)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    print("🚀 Starting Ask Your Data — initializing data connections...")
    _initialize()
    app.run(debug=False, port=5000, threaded=True)

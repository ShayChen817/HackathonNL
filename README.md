# Ask Your Data  Collibra Next Level Challenge

**Governed AI for Enterprise Data Questions**

> Team 18 | Next Level Challenge Hackathon

## Overview

This prototype answers plain-language business questions about Collibra's preview program data, using **governed context from the Collibra Data Intelligence Platform** to ensure accuracy, consistency, and trustworthiness.

### The Problem

LLMs can generate SQL from natural language  but without business context, they guess wrong:

| | Without Context | With Context |
|---|---|---|
| "Active Tester" | Guessed ``Z_ENG_ST = 'ACTIVE'`` | Governed: 3-criteria OR logic |
| "Ongoing" | Guessed ``Z_PRJ_STAT = 'ACTIVE'`` | Governed: ``Z_PRJ_STAT = 'Ongoing'`` |
| **Result** | **0 testers (wrong)** | **303 testers (correct)** |

Same LLM. Same data. Only the **context** changed.

### Key Result

**303 active testers** in ongoing programs  verified across **20 consecutive runs** with zero variance.

---

## Architecture

The solution follows Collibra's **four-layer data governance model**:

```
Business Question
    |
Layer 1: Business Vocabulary (Glossary + Metrics)
    |  "Active Tester" = 3-criteria OR definition
Layer 2: Logical Layer (Data Entities & Attributes)
    |  Maps business concepts to logical structures
Layer 3: Physical Layer (Schemas, Tables, Columns)
    |  Z_ACT_CMP = "Completed Activities"
Layer 4: Data Layer (Databricks via Delta Sharing)
    |  8 tables, ~20K rows
Answer with full traceability
```

### Two Engines

| Engine | Use Case | Determinism |
|--------|----------|-------------|
| **RAG Pipeline** (``ask_your_data.py``) | Open-ended, exploratory questions | High (temperature=0) |
| **Deterministic Rulebook** (``deterministic_engine.py``) | Mission-critical governed metrics | 100% (no LLM) |

---

## Quick Start

### 1. Clone & Setup

```bash
git clone https://gitlab.com/next-level-challenge/team-18.git
cd team-18
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure Credentials

Create a ``.env`` file:

```env
COLLIBRA_USERNAME=<your-username>
COLLIBRA_PASSWORD=<your-password>
ANTHROPIC_API_KEY=<your-api-key>
DELTA_SHARING_PROFILE=config.json
DELTA_SHARING_LIMIT=0
```

Place your Delta Sharing ``config.json`` in the project root.

### 3. Verify Connections

```bash
# Test Delta Sharing
python data_loader.py

# Test Collibra API
python collibra_client.py

# Test the full pipeline
python ask_your_data.py
```

### 4. Run the Deterministic Engine

```bash
python test_deterministic.py
```

Expected output: 303 active testers, 20/20 runs identical.

---

## Active Tester Definition

From Collibra Business Term (asset ``0198c234-11fe-73ff-be9b-c91312850031``):

> A tester is considered **active** if they meet **at least one** of:
> 1. Submitted **>= 3 feedback tickets** (``COUNT(DISTINCT Z_TKT_NR)`` from ``zcc_tkt_itm``)
> 2. Completed **>= 2 surveys** (``Z_SRV_CMP`` from ``zcc_prt_mtrc``)
> 3. **Completed activities > incomplete + blocked + opted-out** (``Z_ACT_CMP > Z_ACT_INC + Z_ACT_BLK + Z_ACT_OPT``)

**Scope:** Only "Ongoing" projects (``Z_PRJ_STAT = 'Ongoing'``)
**Grain:** Unique participants identified by ``Z_SMTP_ADR`` (hashed email)
**Combination:** OR logic with Python set union  no double-counting

### Breakdown

| Criterion | Participants |
|-----------|-------------|
| Tickets >= 3 | 73 |
| Surveys >= 2 | 284 |
| Completed > rest | 64 |
| **Overlap removed** | **118** |
| **Final (set union)** | **303** |

Inclusion-exclusion proof: ``73 + 284 + 64 - 57 - 28 - 61 + 28 = 303``

---

## File Reference

| File | Description |
|------|-------------|
| ``collibra_client.py`` | Extracts all governed context from Collibra REST API (52 terms, 4 measures, 65 column mappings) |
| ``data_loader.py`` | Loads 8 Databricks tables via Delta Sharing into pandas DataFrames |
| ``ask_your_data.py`` | RAG pipeline: governed context + Claude LLM + SQL execution |
| ``rulebook.py`` | Governed definitions encoded as Python constants with Collibra asset IDs |
| ``deterministic_engine.py`` | Pure pandas Active Tester computation  no LLM, 100% deterministic |
| ``test_deterministic.py`` | 20-run verification harness |
| ``governed_context.json`` | Cached Collibra context (52 terms, 230 relations, 65 column mappings) |
| ``generate_report.py`` | Generates the project guide Word document |
| ``generate_presentation.py`` | Generates the project presentation (PPTX) |

---

## Tech Stack

- **Python 3.12**  core runtime
- **Collibra REST API**  governed metadata (business terms, measures, column mappings)
- **Databricks Delta Sharing**  secure data access (8 tables, ~20K rows)
- **Anthropic Claude** (``claude-sonnet-4-20250514``)  LLM for RAG pipeline
- **pandas**  data manipulation and computation
- **pandasql**  SQL execution against DataFrames
- **BeautifulSoup**  HTML stripping from Collibra attributes

---

## Data Sources

| Table | Description | Rows |
|-------|-------------|------|
| ``zcc_prt_mtrc`` | Participant Metrics | 5,865 |
| ``zcc_tkt_itm`` | Feedback Tickets | 3,852 |
| ``zcc_prj_hdr`` | Project Headers | 100 |
| ``zcc_act_stat`` | Activity Status | ~10,000 |
| ``zcc_knt_mstr`` | Content Master | 579 |
| ``zcc_usr_mstr`` | User Master | 1,982 |
| ``zcc_ptm_lnk`` | Project-Team Links | ~500 |
| ``zcc_qa_sat`` | QA Satisfaction | ~700 |

---

## License

This project was created for the Collibra Next Level Challenge hackathon.

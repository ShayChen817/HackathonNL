"""
ask_your_data.py — The main "Ask Your Data Product" prototype.

This is the RAG pipeline that:
1. Takes a plain-language business question
2. Retrieves governed context from Collibra (business terms, column meanings)
3. Uses an LLM to generate SQL grounded in that context
4. Executes the SQL against the Databricks data
5. Returns a trustworthy, transparent answer with sources

Usage:
    python ask_your_data.py
"""

import os
import json
import re
import textwrap
from dotenv import load_dotenv

load_dotenv()

from collibra_client import load_context, extract_full_context, save_context
from data_loader import load_all_tables, execute_sql, get_table_schemas

# ── LLM Configuration (Anthropic Claude) ─────────────────────────────

try:
    import anthropic
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    LLM_AVAILABLE = True
    LLM_MODEL = "claude-sonnet-4-20250514"
except Exception:
    client = None
    LLM_AVAILABLE = False
    LLM_MODEL = None


# ── Context Builder ──────────────────────────────────────────────────

def build_system_prompt(context: dict, table_schemas: dict) -> str:
    """
    Build the system prompt that gives the LLM all the governed context
    it needs to answer questions accurately.
    """

    # 1. Business terms and definitions
    terms_section = "## GOVERNED BUSINESS TERMS\n"
    terms_section += "These are the official, governed definitions. You MUST use these definitions when interpreting questions.\n\n"
    for term in context.get("business_terms", []):
        terms_section += f"### {term['name']}\n"
        if term.get("definition"):
            terms_section += f"**Definition:** {term['definition']}\n"
        if term.get("description"):
            terms_section += f"**Description:** {term['description']}\n"
        if term.get("synonyms"):
            terms_section += f"**Synonyms:** {', '.join(term['synonyms'])}\n"
        terms_section += "\n"

    # 2. Measures / Metrics
    measures_section = "## GOVERNED MEASURES & METRICS\n"
    measures_section += "These define how metrics are calculated. Use these formulas exactly.\n\n"
    for m in context.get("measures", []):
        measures_section += f"### {m['name']}\n"
        if m.get("definition"):
            measures_section += f"**Definition:** {m['definition']}\n"
        if m.get("description"):
            measures_section += f"**Description:** {m['description']}\n"
        for k, v in m.get("attributes", {}).items():
            if v:
                measures_section += f"**{k}:** {v}\n"
        measures_section += "\n"

    # 3. Column map — the crucial bridge from business terms to physical columns
    column_section = "## COLUMN DICTIONARY (Physical Column → Business Meaning)\n"
    column_section += "Column names are cryptic. Use this dictionary to know what each column stores.\n\n"
    column_section += "| Table | Column | Description | Business Term | Business Definition |\n"
    column_section += "|-------|--------|-------------|---------------|--------------------|\n"
    for key, info in sorted(context.get("column_map", {}).items()):
        table = info.get("table_name", "")
        col = info.get("physical_name", "")
        desc = info.get("physical_description", "").replace("\n", " ")[:100]
        bt = info.get("business_term", "")
        bd = info.get("business_definition", "").replace("\n", " ")[:100]
        column_section += f"| {table} | {col} | {desc} | {bt} | {bd} |\n"

    # 4. Table schemas
    schema_section = "## TABLE SCHEMAS\n"
    schema_section += "Available tables and their columns (from Databricks):\n\n"
    for table_name, schema in table_schemas.items():
        schema_section += f"### {table_name} ({schema['row_count']} rows)\n"
        schema_section += "| Column | Type |\n|--------|------|\n"
        for col, dtype in schema["dtypes"].items():
            schema_section += f"| {col} | {dtype} |\n"
        schema_section += "\n"

    system_prompt = textwrap.dedent(f"""\
    You are "Ask Your Data Product" — a trustworthy data assistant for Collibra's preview program data.

    YOUR CORE RULES:
    1. ALWAYS use the governed business definitions below when interpreting questions.
       A "business term" has a precise meaning — never guess.
    2. Generate SQL (SQLite-compatible) that can run against the tables listed below.
    3. ALWAYS show your reasoning: which definitions you used, which columns you mapped, and why.
    4. If a term in the question does NOT have a governed definition, explicitly flag it:
       "⚠️ The term '{{term}}' does not have a governed definition in Collibra. 
       The following answer is based on my best interpretation, not a governed definition."
    5. Return deterministic answers — same question = same answer.
    6. Show the SQL query you generated.
    7. Cite the governed definitions you used.
     8. METRIC SCOPING RULES (MANDATORY):
         - "Number of feedback tickets" MUST be COUNT(DISTINCT zcc_tkt_itm.Z_TKT_NR).
         - Ticket leaderboards by project MUST join zcc_tkt_itm.Z_PRJ_NR = zcc_prj_hdr.Z_PRJ_NR.
         - For project-level ranking, group by canonical name zcc_prj_hdr.Z_PRJ_TXT.
         - NEVER use COUNT(*) when counting tickets.
         - "Number of issues" means issue tickets only: LOWER(zcc_tkt_itm.Z_TKT_ART) = 'issue'.
         - Issue counts MUST exclude not-applicable issues: LOWER(COALESCE(zcc_tkt_itm.Z_TKT_ST, '')) <> 'not applicable'.
         - When scope is ongoing projects, only include projects with at least one participant (EXISTS in zcc_prt_mtrc).
                 - Delta Impact Score uses zcc_prj_hdr.Z_HLT_DTA.
                 - Active tester count must use governed criteria:
                     feedback tickets >= 3 OR surveys >= 2 OR completed > (incomplete + blocked + opted-out).
                 - For "in ongoing programs" active tester questions, default grain is participant-program pairs
                     (Z_SMTP_ADR + Z_PRJ_OID) unless the user explicitly asks for unique people.
         - Only apply project status filters (Ongoing/Finished) if explicitly requested.

    RESPONSE FORMAT:
    📋 **Question Interpretation:**
    [How you interpreted the question using governed definitions]

    📚 **Governed Definitions Used:**
    [List each business term/measure used and its governed definition]

    🔍 **SQL Query:**
    ```sql
    [Your generated SQL]
    ```

    📊 **Answer:**
    [The data-driven answer]

    🔗 **Sources & Traceability:**
    [Which Collibra assets were used, column mappings applied]

    ⚠️ **Ungoverned Terms (if any):**
    [Terms without governed definitions, flagged for attention]

    ---

    {terms_section}

    {measures_section}

    {column_section}

    {schema_section}
    """)

    return system_prompt


def build_no_context_prompt(table_schemas: dict) -> str:
    """
    Build a system prompt WITHOUT governed context — for the 'before' demo.
    The LLM only sees raw table schemas with cryptic column names.
    """
    schema_section = "## TABLE SCHEMAS\n"
    for table_name, schema in table_schemas.items():
        schema_section += f"### {table_name} ({schema['row_count']} rows)\n"
        schema_section += "| Column | Type |\n|--------|------|\n"
        for col, dtype in schema["dtypes"].items():
            schema_section += f"| {col} | {dtype} |\n"
        schema_section += "\n"

    return textwrap.dedent(f"""\
    You are a data assistant. Answer business questions by generating SQL against these tables.
    Generate SQLite-compatible SQL. Show the SQL and give the answer.

    {schema_section}
    """)


# ── Query Pipeline ───────────────────────────────────────────────────

def _extract_top_n(question: str, default: int = 10, max_value: int = 100) -> int:
    """Extract requested Top-N from question text."""
    match = re.search(r"\btop\s+(\d{1,3})\b", question, re.IGNORECASE)
    if not match:
        # Covers phrases like "5 projects" and "5 ongoing projects".
        match = re.search(
            r"\b(\d{1,3})\s+(?:(?:\w+\s+){0,3})?(?:projects?|programs?)\b",
            question,
            re.IGNORECASE,
        )
    if not match:
        return default
    return max(1, min(int(match.group(1)), max_value))


def _build_feedback_ticket_leaderboard_sql(question: str) -> dict | None:
    """
    Build a deterministic SQL template for project leaderboard ticket questions.
    Returns None if the question does not match this intent.
    """
    q = question.lower()
    has_rank = any(k in q for k in ("top", "most", "highest", "leaderboard", "rank"))
    has_project = any(k in q for k in ("project", "projects", "program", "programs"))
    has_ticket = "ticket" in q
    has_feedback = "feedback" in q

    if not (has_rank and has_project and has_ticket and has_feedback):
        return None

    top_n = _extract_top_n(question, default=10)

    status_filter = ""
    scope_label = "All projects"
    if any(k in q for k in ("ongoing", "active projects", "active programs")):
        status_filter = "WHERE p.Z_PRJ_STAT = 'Ongoing'"
        scope_label = "Ongoing projects only"
    elif any(k in q for k in ("finished", "archived", "completed projects", "completed programs")):
        status_filter = "WHERE p.Z_PRJ_STAT = 'Finished'"
        scope_label = "Finished projects only"

    sql_query = textwrap.dedent(f"""\
    SELECT
        p.Z_PRJ_TXT AS project_name,
        COUNT(DISTINCT t.Z_TKT_NR) AS ticket_count
    FROM zcc_tkt_itm t
    JOIN zcc_prj_hdr p ON t.Z_PRJ_NR = p.Z_PRJ_NR
    {status_filter}
    GROUP BY p.Z_PRJ_TXT
    ORDER BY ticket_count DESC
    LIMIT {top_n};
    """).strip()

    return {
        "sql_query": sql_query,
        "scope_label": scope_label,
        "top_n": top_n,
    }


def _build_feedback_ticket_template_response(question: str, sql_query: str, scope_label: str) -> str:
    """Create a transparent response for deterministic scoped SQL execution."""
    return textwrap.dedent(f"""\
    📋 **Question Interpretation:**
    Ranked project leaderboard by number of feedback tickets.

    📚 **Governed Definitions Used:**
    - Feedback tickets are counted with `COUNT(DISTINCT Z_TKT_NR)`.
    - Project names are taken from `zcc_prj_hdr.Z_PRJ_TXT` after joining on project ID.
    - Scope: {scope_label}

    🔍 **SQL Query:**
    ```sql
    {sql_query}
    ```

    📊 **Answer:**
    Returned the requested project leaderboard from governed ticket counting logic.

    🔗 **Sources & Traceability:**
    - `zcc_tkt_itm.Z_TKT_NR` (ticket identifier)
    - `zcc_tkt_itm.Z_PRJ_NR` -> `zcc_prj_hdr.Z_PRJ_NR`
    - `zcc_prj_hdr.Z_PRJ_TXT` (canonical project name)
    """).strip()


def _build_issue_leaderboard_sql(question: str) -> dict | None:
    """
    Build a deterministic SQL template for project leaderboard issue questions.
    Returns None if the question does not match this intent.
    """
    q = question.lower()
    has_rank = any(k in q for k in ("top", "most", "highest", "leaderboard", "rank"))
    has_project = any(k in q for k in ("project", "projects", "program", "programs"))
    has_issue = any(k in q for k in ("issue", "issues"))

    # Keep this path specific to issue-based intent; feedback ticket path is handled separately.
    if not (has_rank and has_project and has_issue):
        return None

    top_n = _extract_top_n(question, default=10)

    where_clauses = [
        "LOWER(t.Z_TKT_ART) = 'issue'",
        "LOWER(COALESCE(t.Z_TKT_ST, '')) <> 'not applicable'",
    ]
    scope_label = "All projects"

    if any(k in q for k in ("ongoing", "active projects", "active programs")):
        where_clauses.append("p.Z_PRJ_STAT = 'Ongoing'")
        where_clauses.append("EXISTS (SELECT 1 FROM zcc_prt_mtrc m WHERE m.Z_PRJ_OID = p.Z_PRJ_NR)")
        scope_label = "Ongoing projects with participants"
    elif any(k in q for k in ("finished", "archived", "completed projects", "completed programs")):
        where_clauses.append("p.Z_PRJ_STAT = 'Finished'")
        scope_label = "Finished projects only"

    where_sql = "\nWHERE " + "\n  AND ".join(where_clauses)

    sql_query = textwrap.dedent(f"""\
    SELECT
        p.Z_PRJ_TXT AS project_name,
        COUNT(DISTINCT t.Z_TKT_NR) AS issue_total_count
    FROM zcc_tkt_itm t
    JOIN zcc_prj_hdr p ON t.Z_PRJ_NR = p.Z_PRJ_NR
    {where_sql}
    GROUP BY p.Z_PRJ_TXT
    ORDER BY issue_total_count DESC
    LIMIT {top_n};
    """).strip()

    return {
        "sql_query": sql_query,
        "scope_label": scope_label,
        "top_n": top_n,
    }


def _build_issue_template_response(question: str, sql_query: str, scope_label: str) -> str:
    """Create a transparent response for deterministic issue leaderboard execution."""
    return textwrap.dedent(f"""\
    📋 **Question Interpretation:**
    Ranked project leaderboard by number of issues.

    📚 **Governed Definitions Used:**
    - Issues are counted from feedback tickets where `LOWER(Z_TKT_ART) = 'issue'`.
    - Not-applicable issues are excluded with `LOWER(COALESCE(Z_TKT_ST, '')) <> 'not applicable'`.
    - Ongoing scope requires projects that have participants in `zcc_prt_mtrc`.
    - Scope: {scope_label}

    🔍 **SQL Query:**
    ```sql
    {sql_query}
    ```

    📊 **Answer:**
    Returned the requested project leaderboard from governed issue-counting logic.

    🔗 **Sources & Traceability:**
    - `zcc_tkt_itm.Z_TKT_ART`, `zcc_tkt_itm.Z_TKT_ST`, `zcc_tkt_itm.Z_TKT_NR`
    - `zcc_tkt_itm.Z_PRJ_NR` -> `zcc_prj_hdr.Z_PRJ_NR`
    - `zcc_prj_hdr.Z_PRJ_TXT`
    - `zcc_prt_mtrc.Z_PRJ_OID` (participant existence for ongoing scope)
    """).strip()


def _extract_impact_score_min(question: str, default: int = 100) -> int:
        """Extract minimum impact score threshold from question text."""
        patterns = [
                r"(?:delta\s+impact\s+score|impact\s+score)[^\d]{0,24}(?:over|above|greater than|at least|>=)\s*(\d{1,3})",
                r"(?:over|above|greater than|at least|>=)\s*(\d{1,3})\s*%?\s*(?:delta\s+impact\s+score|impact\s+score)",
        ]
        for pattern in patterns:
                match = re.search(pattern, question, re.IGNORECASE)
                if match:
                        return max(0, min(int(match.group(1)), 10000))
        return default


def _extract_active_tester_max(question: str, default: int = 20) -> int:
        """Extract upper bound for active tester count from question text."""
        patterns = [
                r"(?:fewer than|less than|under|below)\s*(\d{1,3})\s+active\s+testers?",
                r"active\s+testers?[^\d]{0,24}(?:fewer than|less than|under|below)\s*(\d{1,3})",
                r"active\s+testers?\s*<\s*(\d{1,3})",
        ]
        for pattern in patterns:
                match = re.search(pattern, question, re.IGNORECASE)
                if match:
                        return max(1, min(int(match.group(1)), 100000))
        return default


def _build_high_impact_low_active_sql(question: str) -> dict | None:
        """
        Build deterministic SQL for:
        projects with high Delta Impact Score and low active tester count.
        """
        q = question.lower()
        has_project = any(k in q for k in ("project", "projects", "program", "programs"))
        has_impact = "impact score" in q or "delta impact" in q or "z_hlt_dta" in q
        has_active = "active tester" in q or "active testers" in q

        if not (has_project and has_impact and has_active):
                return None

        impact_min = _extract_impact_score_min(question, default=100)
        active_max = _extract_active_tester_max(question, default=20)

        sql_query = textwrap.dedent(f"""\
        WITH feedback_completion AS (
            SELECT
                ft.Z_SMTP_ADR,
                ft.Z_PRJ_NR,
                COUNT(DISTINCT ft.Z_TKT_NR) AS feedback_ticket_count
            FROM zcc_tkt_itm ft
            GROUP BY ft.Z_SMTP_ADR, ft.Z_PRJ_NR
        ),
        participant_status AS (
            SELECT
                pa.Z_SMTP_ADR,
                pa.Z_PRJ_OID,
                pa.Z_PRJ_TXT,
                CASE
                    WHEN COALESCE(fc.feedback_ticket_count, 0) >= 3
                        OR COALESCE(pa.Z_SRV_CMP, 0) >= 2
                        OR COALESCE(pa.Z_ACT_CMP, 0) > COALESCE(pa.Z_ACT_INC, 0)
                             + COALESCE(pa.Z_ACT_BLK, 0)
                             + COALESCE(pa.Z_ACT_OPT, 0)
                    THEN 1
                    ELSE 0
                END AS is_active_tester
            FROM zcc_prt_mtrc pa
            LEFT JOIN feedback_completion fc
                ON pa.Z_SMTP_ADR = fc.Z_SMTP_ADR
             AND pa.Z_PRJ_OID = fc.Z_PRJ_NR
        )
        SELECT
            ps.Z_PRJ_OID,
            ps.Z_PRJ_TXT,
            pr.Z_HLT_DTA,
            COUNT(DISTINCT CASE WHEN ps.is_active_tester = 1 THEN ps.Z_SMTP_ADR END) AS active_tester_count
        FROM participant_status ps
        JOIN zcc_prj_hdr pr
            ON ps.Z_PRJ_OID = pr.Z_PRJ_NR
        WHERE CAST(COALESCE(pr.Z_HLT_DTA, 0) AS REAL) >= {impact_min}
        GROUP BY ps.Z_PRJ_OID, ps.Z_PRJ_TXT, pr.Z_HLT_DTA
        HAVING COUNT(DISTINCT CASE WHEN ps.is_active_tester = 1 THEN ps.Z_SMTP_ADR END) < {active_max}
        ORDER BY CAST(pr.Z_HLT_DTA AS REAL) DESC, active_tester_count ASC, ps.Z_PRJ_TXT;
        """).strip()

        return {
                "sql_query": sql_query,
                "impact_min": impact_min,
                "active_max": active_max,
        }


def _build_high_impact_low_active_response(question: str, sql_query: str, impact_min: int, active_max: int) -> str:
        """Create a transparent response for high-impact/low-active deterministic SQL."""
        return textwrap.dedent(f"""\
        📋 **Question Interpretation:**
        List projects with Delta Impact Score >= {impact_min} and active tester count < {active_max}.

        📚 **Governed Definitions Used:**
        - Delta Impact Score from `zcc_prj_hdr.Z_HLT_DTA`.
        - Active tester rule:
            ticket_count >= 3 OR surveys >= 2 OR completed > (incomplete + blocked + opted-out).
        - Active testers counted as distinct participants per project (`Z_SMTP_ADR`).

        🔍 **SQL Query:**
        ```sql
        {sql_query}
        ```

        📊 **Answer:**
        Returned projects meeting both impact and active-tester constraints.

        🔗 **Sources & Traceability:**
        - `zcc_prj_hdr.Z_HLT_DTA`
        - `zcc_prt_mtrc.Z_SRV_CMP`, `Z_ACT_CMP`, `Z_ACT_INC`, `Z_ACT_BLK`, `Z_ACT_OPT`
        - `zcc_tkt_itm.Z_TKT_NR`, `zcc_tkt_itm.Z_PRJ_NR`, `zcc_tkt_itm.Z_SMTP_ADR`
        """).strip()


def _build_active_tester_count_sql(question: str) -> dict | None:
        """
        Build deterministic SQL for active tester count questions.
        Returns both participant-program grain and unique-person grain for transparency.
        """
        q = question.lower()
        has_active = "active tester" in q or "active testers" in q
        has_count_intent = any(k in q for k in ("how many", "count", "number of", "total"))

        if not (has_active and has_count_intent):
                return None

        ongoing_only = any(k in q for k in ("ongoing", "ongoing program", "ongoing programs", "ongoing project", "ongoing projects"))
        finished_only = any(k in q for k in ("finished", "archived", "completed projects", "completed programs"))
        unique_only = any(k in q for k in ("unique", "distinct", "different people", "unique people"))

        status_filter = ""
        scope_label = "All projects"
        if ongoing_only:
                status_filter = "WHERE ph.Z_PRJ_STAT = 'Ongoing'"
                scope_label = "Ongoing programs"
        elif finished_only:
                status_filter = "WHERE ph.Z_PRJ_STAT = 'Finished'"
                scope_label = "Finished programs"

        sql_query = textwrap.dedent(f"""\
        WITH feedback_completion AS (
            SELECT
                ft.Z_SMTP_ADR,
                ft.Z_PRJ_NR,
                COUNT(DISTINCT ft.Z_TKT_NR) AS feedback_ticket_count
            FROM zcc_tkt_itm ft
            GROUP BY ft.Z_SMTP_ADR, ft.Z_PRJ_NR
        ),
        participant_status AS (
            SELECT
                pm.Z_SMTP_ADR,
                pm.Z_PRJ_OID,
                CASE
                    WHEN COALESCE(fc.feedback_ticket_count, 0) >= 3
                        OR COALESCE(pm.Z_SRV_CMP, 0) >= 2
                        OR COALESCE(pm.Z_ACT_CMP, 0) > COALESCE(pm.Z_ACT_INC, 0)
                             + COALESCE(pm.Z_ACT_BLK, 0)
                             + COALESCE(pm.Z_ACT_OPT, 0)
                    THEN 1
                    ELSE 0
                END AS is_active_tester
            FROM zcc_prt_mtrc pm
            JOIN zcc_prj_hdr ph ON pm.Z_PRJ_OID = ph.Z_PRJ_NR
            LEFT JOIN feedback_completion fc
                ON pm.Z_SMTP_ADR = fc.Z_SMTP_ADR
             AND pm.Z_PRJ_OID = fc.Z_PRJ_NR
            {status_filter}
        )
        SELECT
            COUNT(DISTINCT CASE WHEN is_active_tester = 1 THEN Z_SMTP_ADR || '|' || Z_PRJ_OID END) AS active_tester_participations,
            COUNT(DISTINCT CASE WHEN is_active_tester = 1 THEN Z_SMTP_ADR END) AS unique_active_testers
        FROM participant_status;
        """).strip()

        return {
                "sql_query": sql_query,
                "scope_label": scope_label,
                "unique_only": unique_only,
        }


def _build_active_tester_count_response(sql_query: str, scope_label: str, unique_only: bool) -> str:
        """Create a transparent response for deterministic active tester count execution."""
        grain_note = (
                "Unique people only requested; use `unique_active_testers`."
                if unique_only
                else "Default grain is participant-program pairs (`active_tester_participations`) for in-program questions."
        )

        return textwrap.dedent(f"""\
        📋 **Question Interpretation:**
        Count active testers using governed rules for scope: {scope_label}.

        📚 **Governed Definitions Used:**
        - Active tester rule: ticket_count >= 3 OR surveys >= 2 OR completed > (incomplete + blocked + opted-out).
        - Returned both grains to avoid ambiguity:
            - `active_tester_participations` (participant-program pairs)
            - `unique_active_testers` (deduplicated people)

        🔍 **SQL Query:**
        ```sql
        {sql_query}
        ```

        📊 **Answer:**
        {grain_note}

        🔗 **Sources & Traceability:**
        - `zcc_prt_mtrc.Z_SMTP_ADR`, `Z_PRJ_OID`, `Z_SRV_CMP`, `Z_ACT_CMP`, `Z_ACT_INC`, `Z_ACT_BLK`, `Z_ACT_OPT`
        - `zcc_tkt_itm.Z_TKT_NR`, `zcc_tkt_itm.Z_PRJ_NR`, `zcc_tkt_itm.Z_SMTP_ADR`
        - `zcc_prj_hdr.Z_PRJ_NR`, `zcc_prj_hdr.Z_PRJ_STAT`
        """).strip()

def ask_with_context(question: str, context: dict, table_schemas: dict) -> dict:
    """
    Answer a question WITH governed context (the 'after' / trustworthy path).
    """
    system_prompt = build_system_prompt(context, table_schemas)

    # NOTE: Active tester count now routes through Claude (governed RAG) so the LLM
    # demonstrates it can derive the correct answer from Collibra definitions.
    # The rulebook helpers are still available for the /api/active-testers endpoint.

    high_impact_template = _build_high_impact_low_active_sql(question)
    if high_impact_template:
        sql_query = high_impact_template["sql_query"]
        query_result = None
        query_error = None
        try:
            result_df = execute_sql(sql_query)
            query_result = result_df.to_dict(orient="records")
        except Exception as e:
            query_error = str(e)

        return {
            "mode": "with_context",
            "execution_mode": "rulebook_sql",
            "question": question,
            "llm_response": _build_high_impact_low_active_response(
                question,
                sql_query,
                high_impact_template["impact_min"],
                high_impact_template["active_max"],
            ),
            "sql_query": sql_query,
            "query_result": query_result,
            "query_error": query_error,
        }

    issue_template = _build_issue_leaderboard_sql(question)
    if issue_template:
        sql_query = issue_template["sql_query"]
        query_result = None
        query_error = None
        try:
            result_df = execute_sql(sql_query)
            query_result = result_df.to_dict(orient="records")
        except Exception as e:
            query_error = str(e)

        return {
            "mode": "with_context",
            "execution_mode": "rulebook_sql",
            "question": question,
            "llm_response": _build_issue_template_response(
                question,
                sql_query,
                issue_template["scope_label"],
            ),
            "sql_query": sql_query,
            "query_result": query_result,
            "query_error": query_error,
        }

    scoped_template = _build_feedback_ticket_leaderboard_sql(question)
    if scoped_template:
        sql_query = scoped_template["sql_query"]
        query_result = None
        query_error = None
        try:
            result_df = execute_sql(sql_query)
            query_result = result_df.to_dict(orient="records")
        except Exception as e:
            query_error = str(e)

        return {
            "mode": "with_context",
            "execution_mode": "rulebook_sql",
            "question": question,
            "llm_response": _build_feedback_ticket_template_response(
                question,
                sql_query,
                scoped_template["scope_label"],
            ),
            "sql_query": sql_query,
            "query_result": query_result,
            "query_error": query_error,
        }

    if not LLM_AVAILABLE:
        return {
            "mode": "with_context",
            "execution_mode": "unavailable",
            "question": question,
            "error": "No LLM API key configured. Set ANTHROPIC_API_KEY in .env",
            "system_prompt_preview": system_prompt[:2000] + "...",
        }

    # Step 1: Ask Claude to generate SQL + reasoning
    response = client.messages.create(
        model=LLM_MODEL,
        max_tokens=4096,
        system=system_prompt,
        messages=[
            {"role": "user", "content": question},
        ],
        temperature=0,  # deterministic
    )
    llm_output = response.content[0].text

    # Step 2: Extract SQL from response
    sql_match = re.search(r"```sql\s*(.*?)\s*```", llm_output, re.DOTALL)
    sql_query = sql_match.group(1).strip() if sql_match else None

    # Step 3: Execute SQL
    query_result = None
    query_error = None
    if sql_query:
        try:
            result_df = execute_sql(sql_query)
            query_result = result_df.to_dict(orient="records")
        except Exception as e:
            query_error = str(e)

    return {
        "mode": "with_context",
        "execution_mode": "llm_sql",
        "question": question,
        "llm_response": llm_output,
        "sql_query": sql_query,
        "query_result": query_result,
        "query_error": query_error,
    }


def ask_without_context(question: str, table_schemas: dict) -> dict:
    """
    Answer a question WITHOUT governed context (the 'before' / naive path).
    """
    system_prompt = build_no_context_prompt(table_schemas)

    if not LLM_AVAILABLE:
        return {
            "mode": "without_context",
            "question": question,
            "error": "No LLM API key configured. Set ANTHROPIC_API_KEY in .env",
        }

    response = client.messages.create(
        model=LLM_MODEL,
        max_tokens=4096,
        system=system_prompt,
        messages=[
            {"role": "user", "content": question},
        ],
        temperature=0,
    )
    llm_output = response.content[0].text

    sql_match = re.search(r"```sql\s*(.*?)\s*```", llm_output, re.DOTALL)
    sql_query = sql_match.group(1).strip() if sql_match else None

    query_result = None
    query_error = None
    if sql_query:
        try:
            result_df = execute_sql(sql_query)
            query_result = result_df.to_dict(orient="records")
        except Exception as e:
            query_error = str(e)

    return {
        "mode": "without_context",
        "question": question,
        "llm_response": llm_output,
        "sql_query": sql_query,
        "query_result": query_result,
        "query_error": query_error,
    }


def compare(question: str, context: dict, table_schemas: dict) -> dict:
    """
    Run the same question through both pipelines for the before/after demo.
    """
    print(f"\n{'='*80}")
    print(f"  QUESTION: {question}")
    print(f"{'='*80}\n")

    print("❌ Running WITHOUT context (naive LLM)...")
    without = ask_without_context(question, table_schemas)

    print("✅ Running WITH governed context...")
    with_ctx = ask_with_context(question, context, table_schemas)

    return {
        "question": question,
        "without_context": without,
        "with_context": with_ctx,
    }


# ── Pretty Printer ───────────────────────────────────────────────────

def print_result(result: dict):
    """Pretty-print a query result."""
    mode = result.get("mode", "unknown")
    icon = "✅" if mode == "with_context" else "❌"
    label = "WITH GOVERNED CONTEXT" if mode == "with_context" else "WITHOUT CONTEXT (naive)"

    print(f"\n{'─'*70}")
    print(f"{icon} {label}")
    print(f"{'─'*70}")
    print(f"\nQuestion: {result['question']}\n")

    if result.get("error"):
        print(f"⚠️  Error: {result['error']}")
        return

    print(result.get("llm_response", "No response"))

    if result.get("query_result") is not None:
        print(f"\n📊 Query Result (raw data):")
        for row in result["query_result"][:10]:
            print(f"  {row}")
    elif result.get("query_error"):
        print(f"\n⚠️  SQL Error: {result['query_error']}")


def print_comparison(comparison: dict):
    """Pretty-print a side-by-side comparison."""
    print(f"\n{'='*80}")
    print(f"  BEFORE / AFTER COMPARISON")
    print(f"  Question: {comparison['question']}")
    print(f"{'='*80}")

    print_result(comparison["without_context"])
    print_result(comparison["with_context"])


# ── Main Interactive Loop ────────────────────────────────────────────

SAMPLE_QUESTIONS = [
    "How many active testers do we have in the ongoing programs?",
    "What is the average satisfaction score across all programs?",
    "Which programs have the most feedback tickets?",
    "How many participants completed at least half of their activities?",
    "What is the total number of issues reported with high impact?",
    "List all finished programs with their creation dates.",
    "How many unique companies participate across all programs?",
    "What is the feedback impact score distribution?",
]


def main():
    print("\n" + "="*70)
    print("  🧠 ASK YOUR DATA PRODUCT — Collibra Hackathon Prototype")
    print("="*70)

    # Load or extract context
    context_path = "governed_context.json"
    if os.path.exists(context_path):
        print("\n📂 Loading cached governed context...")
        context = load_context(context_path)
    else:
        print("\n🔄 Extracting governed context from Collibra API...")
        context = extract_full_context()
        save_context(context, context_path)

    print(f"\n📊 Context loaded:")
    print(f"  Business Terms: {len(context.get('business_terms', []))}")
    print(f"  Measures:       {len(context.get('measures', []))}")
    print(f"  Column Map:     {len(context.get('column_map', {}))} columns")

    # Load data
    print("\n📦 Loading data tables...")
    load_all_tables()
    table_schemas = get_table_schemas()

    # Interactive loop
    print(f"\n{'─'*70}")
    print("Ready! Ask a question, or type:")
    print("  'compare <question>' — side-by-side before/after")
    print("  'samples'            — see sample questions")
    print("  'demo'               — run the full before/after demo")
    print("  'quit'               — exit")
    print(f"{'─'*70}\n")

    while True:
        try:
            user_input = input("🔍 Your question: ").strip()
        except (EOFError, KeyboardInterrupt):
            break

        if not user_input:
            continue
        if user_input.lower() in ("quit", "exit", "q"):
            print("👋 Goodbye!")
            break
        elif user_input.lower() == "samples":
            print("\n📝 Sample questions:")
            for i, q in enumerate(SAMPLE_QUESTIONS, 1):
                print(f"  {i}. {q}")
            print()
        elif user_input.lower() == "demo":
            demo_question = "How many active testers do we have in the ongoing programs?"
            result = compare(demo_question, context, table_schemas)
            print_comparison(result)
        elif user_input.lower().startswith("compare "):
            question = user_input[8:].strip()
            result = compare(question, context, table_schemas)
            print_comparison(result)
        else:
            result = ask_with_context(user_input, context, table_schemas)
            print_result(result)


if __name__ == "__main__":
    main()

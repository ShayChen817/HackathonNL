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

def ask_with_context(question: str, context: dict, table_schemas: dict) -> dict:
    """
    Answer a question WITH governed context (the 'after' / trustworthy path).
    """
    system_prompt = build_system_prompt(context, table_schemas)

    if not LLM_AVAILABLE:
        return {
            "mode": "with_context",
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

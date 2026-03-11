"""
data_loader.py — Load all Databricks tables via Delta Sharing into pandas DataFrames.

Also provides a SQL interface via pandasql so the LLM-generated SQL can be executed.
"""

import os
import json
import delta_sharing
import pandas as pd
from dotenv import load_dotenv

load_dotenv()

PROFILE_PATH = os.getenv("DELTA_SHARING_PROFILE", "config.json")
LIMIT = os.getenv("DELTA_SHARING_LIMIT", "0")
LIMIT = int(LIMIT) if LIMIT and LIMIT != "0" else None

TABLES = {
    "zcc_act_stat": "centercode_share.centercode.zcc_act_stat",
    "zcc_knt_mstr": "centercode_share.centercode.zcc_knt_mstr",
    "zcc_prj_hdr":  "centercode_share.centercode.zcc_prj_hdr",
    "zcc_prt_mtrc": "centercode_share.centercode.zcc_prt_mtrc",
    "zcc_ptm_lnk":  "centercode_share.centercode.zcc_ptm_lnk",
    "zcc_qa_sat":   "centercode_share.centercode.zcc_qa_sat",
    "zcc_tkt_itm":  "centercode_share.centercode.zcc_tkt_itm",
    "zcc_usr_mstr": "centercode_share.centercode.zcc_usr_mstr",
}

# Global dataframe cache
_dataframes: dict[str, pd.DataFrame] = {}


def _validate_profile_file(path: str) -> None:
    """Validate Delta Sharing profile file to provide clear startup errors."""
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"Delta Sharing profile not found: {path}. "
            "Set DELTA_SHARING_PROFILE to a valid file path."
        )

    try:
        with open(path, "r", encoding="utf-8") as f:
            parsed = json.load(f)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Delta Sharing profile is not valid JSON: {path}."
        ) from exc

    if not isinstance(parsed, dict):
        raise ValueError(
            "Delta Sharing profile JSON must be an object. "
            "If you are deploying on Render, set DELTA_SHARING_CONFIG_JSON "
            "to the full config.json content (not DELTA_SHARING_LIMIT like 10000)."
        )


def load_all_tables(limit: int = None) -> dict[str, pd.DataFrame]:
    """Load all hackathon tables into pandas DataFrames."""
    global _dataframes
    if _dataframes:
        return _dataframes

    _validate_profile_file(PROFILE_PATH)

    effective_limit = limit or LIMIT
    print(f"📦 Loading tables from Databricks (limit={effective_limit or 'ALL'})...")

    for name, fqn in TABLES.items():
        table_url = f"{PROFILE_PATH}#{fqn}"
        kwargs = {}
        if effective_limit:
            kwargs["limit"] = effective_limit
        _dataframes[name] = delta_sharing.load_as_pandas(table_url, **kwargs)
        print(f"  ✅ {name}: {_dataframes[name].shape[0]} rows, {_dataframes[name].shape[1]} cols")

    return _dataframes


def get_dataframes() -> dict[str, pd.DataFrame]:
    """Get cached dataframes, loading if needed."""
    if not _dataframes:
        load_all_tables()
    return _dataframes


def execute_sql(sql: str) -> pd.DataFrame:
    """
    Execute a SQL query against the loaded DataFrames using pandasql.
    
    The SQL can reference table names directly (e.g., SELECT * FROM zcc_act_stat).
    """
    from pandasql import sqldf
    dfs = get_dataframes()
    # pandasql uses a lambda to access local variables as table names
    return sqldf(sql, dfs)


def get_table_schemas() -> dict:
    """Return schema info for all tables (column names, dtypes, sample values)."""
    dfs = get_dataframes()
    schemas = {}
    for name, df in dfs.items():
        schemas[name] = {
            "columns": list(df.columns),
            "dtypes": {col: str(dtype) for col, dtype in df.dtypes.items()},
            "row_count": len(df),
            "sample": df.head(3).to_dict(orient="records"),
        }
    return schemas


if __name__ == "__main__":
    dfs = load_all_tables()
    print("\n📋 Table Schemas:")
    for name, df in dfs.items():
        print(f"\n  {name} ({len(df)} rows):")
        for col in df.columns:
            print(f"    {col}: {df[col].dtype}")

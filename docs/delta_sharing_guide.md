# Delta Sharing Guide — Data Layer

This is the **Data Layer** of the hackathon architecture — the raw tables you will query once you know what the columns mean (see the [Collibra API Guide](collibra_api_guide.md) for the semantic context).

The hackathon dataset lives in Databricks and is shared via Delta Sharing. This guide explains how to connect, load the tables, and start exploring the data.

**Official Delta Sharing spec:** [https://github.com/delta-io/delta-sharing](https://github.com/delta-io/delta-sharing)
**Databricks Delta Sharing docs:** [https://docs.databricks.com/en/delta-sharing/index.html](https://docs.databricks.com/en/delta-sharing/index.html)

---

## 1. What is Delta Sharing?

Delta Sharing is an open protocol developed by Databricks for sharing live data from a data lake or lakehouse **without copying it**. The data stays in the provider's storage (Databricks, in this case); the recipient reads it via a REST API using a short-lived bearer token.

From your perspective as a participant:

- You receive a `config.json` file (the **sharing profile**) that contains a bearer token and an endpoint URL.
- You point the `delta-sharing` Python library at that file.
- The library handles authentication and downloads data directly into a pandas DataFrame.

You do not need a Databricks account, a Spark cluster, or any cloud credentials beyond `config.json`.

---

## 2. The sharing profile (`config.json`)

The file `config.json` in the repo root is a **Delta Sharing profile** — a JSON document the library uses to authenticate against the Databricks sharing endpoint.

**Structure:**

```json
{
  "shareCredentialsVersion": 1,
  "bearerToken": "<token>",
  "endpoint": "https://<region>.cloud.databricks.com/api/2.0/delta-sharing/metastores/<metastore-id>",
  "expirationTime": "2027-02-23T17:01:53.505Z",
  "icebergEndpoint": "https://<region>.cloud.databricks.com/api/2.0/delta-sharing/metastores/<metastore-id>/iceberg"
}
```

**Fields:**

| Field | Type | Description |
|---|---|---|
| `shareCredentialsVersion` | integer | Protocol version — always `1` for the current spec |
| `bearerToken` | string | Short-lived access token. Treat this as a password — do not commit it or paste it in public channels |
| `endpoint` | string | The Databricks Delta Sharing REST endpoint for this metastore |
| `expirationTime` | ISO 8601 datetime | When the token expires. After this date the token will stop working |
| `icebergEndpoint` | string | Alternative endpoint for Iceberg-format reads (not used in this hackathon) |

> **Security:** `config.json` is listed in `.gitignore`. Never commit it to a public repository. Treat the `bearerToken` the same way you would treat a password.

The path to this file is configured via the `.env` variable:

```
DELTA_SHARING_PROFILE=config.json
```

---

## 3. Installation

```bash
pip install delta-sharing pandas python-dotenv
```

The `delta-sharing` package is the official open-source Python client. It ships from PyPI and has no Databricks-specific dependencies.

---

## 4. Table naming — fully qualified names (FQN)

Delta Sharing organises shared data in a three-level hierarchy:

```
{share_name}.{schema_name}.{table_name}
```

| Level | Description |
|---|---|
| **Share** | A named collection of schemas/tables the provider has shared. In the hackathon this is `centercode_share`. |
| **Schema** | A namespace within the share, equivalent to a database schema. In the hackathon this is `centercode`. |
| **Table** | The actual data table. |

**The six hackathon tables:**

| Table | Fully qualified name |
|---|---|
| `zcc_act_stat` | `centercode_share.centercode.zcc_act_stat` |
| `zcc_prj_hdr` | `centercode_share.centercode.zcc_prj_hdr` |
| `zcc_prt_mtrc` | `centercode_share.centercode.zcc_prt_mtrc` |
| `zcc_ptm_lnk` | `centercode_share.centercode.zcc_ptm_lnk` |
| `zcc_qa_sat` | `centercode_share.centercode.zcc_qa_sat` |
| `zcc_tkt_itm` | `centercode_share.centercode.zcc_tkt_itm` |

> **Column names are cryptic by design.** Names like `Z_ENG_ST`, `Z_IMP_SC`, `Z_OCC_MNG` do not explain what they store. The governed descriptions for every column live in Collibra's Physical Data Layer — see the [Collibra API Guide](collibra_api_guide.md).

---

## 5. Python API reference

### 5.1 Discover available tables

```python
import delta_sharing

profile = "config.json"
client = delta_sharing.SharingClient(profile)
tables = client.list_all_tables()
```

Each item in the returned list is a `Table` object. Fields:

| Attribute | Description |
|---|---|
| `.name` | Table name (e.g. `zcc_act_stat`) |
| `.share` | Share name (e.g. `centercode_share`) |
| `.schema` | Schema name (e.g. `centercode`) |

Use this to confirm your profile is working and see which tables are available before loading them.

---

### 5.2 Load a table into a pandas DataFrame

```python
import delta_sharing

profile = "config.json"
table_url = f"{profile}#centercode_share.centercode.zcc_act_stat"

df = delta_sharing.load_as_pandas(table_url, limit=1000)
```

**The table URL format:**

```
{path_to_profile_json}#{share_name}.{schema_name}.{table_name}
```

The `#` separator tells the library to split on the profile path and the table FQN.

**Parameters:**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `url` | string | required | Table URL in `{profile}#{share.schema.table}` format |
| `limit` | integer | `None` (all rows) | Maximum number of rows to fetch. Use this to avoid loading the entire table during exploration. |

> **Note on `limit`:** The limit is **best-effort** — the library fetches whole Parquet files from the provider and stops once it has accumulated at least `limit` rows. The actual row count may be slightly above `limit` depending on how the files are partitioned.

**Returns:** a `pandas.DataFrame` with all columns from the table.

> **Version compatibility:** If you get a `TypeError` on `load_as_pandas` with a `limit=` argument, upgrade with `pip install --upgrade delta-sharing`.

---

### 5.3 Load all six tables at once

```python
import os
import delta_sharing
from dotenv import load_dotenv

load_dotenv()

PROFILE_PATH = os.getenv("DELTA_SHARING_PROFILE", "config.json")
LIMIT = int(os.getenv("DELTA_SHARING_LIMIT", "1000") or "1000")

TABLES = {
    "zcc_act_stat": "centercode_share.centercode.zcc_act_stat",
    "zcc_prj_hdr":  "centercode_share.centercode.zcc_prj_hdr",
    "zcc_prt_mtrc": "centercode_share.centercode.zcc_prt_mtrc",
    "zcc_ptm_lnk":  "centercode_share.centercode.zcc_ptm_lnk",
    "zcc_qa_sat":   "centercode_share.centercode.zcc_qa_sat",
    "zcc_tkt_itm":  "centercode_share.centercode.zcc_tkt_itm",
}

dataframes = {}
for name, fqn in TABLES.items():
    table_url = f"{PROFILE_PATH}#{fqn}"
    dataframes[name] = delta_sharing.load_as_pandas(table_url, limit=LIMIT)
    print(f"Loaded {name}: {dataframes[name].shape}")
```

After this, `dataframes["zcc_act_stat"]`, `dataframes["zcc_prj_hdr"]`, etc. are standard pandas DataFrames.

---

## 6. Environment variables

| Variable | Default | Description |
|---|---|---|
| `DELTA_SHARING_PROFILE` | `config.json` | Path to the Delta Sharing profile file |
| `DELTA_SHARING_LIMIT` | `1000` | Maximum rows per table load (`None` or `0` to load all rows) |

Set these in `.env` (copy from `.env.example`):

```bash
DELTA_SHARING_PROFILE=config.json
DELTA_SHARING_LIMIT=1000
```

---

## 7. Error handling

| Error / symptom | Likely cause | Fix |
|---|---|---|
| `RuntimeError: Missing dependency 'delta-sharing'` | Package not installed | `pip install delta-sharing pandas python-dotenv` |
| `HTTP 401 Unauthorized` | Bearer token is wrong or expired | Check `config.json` — ask the organizers for a fresh profile if the token has expired |
| `HTTP 403 Forbidden` | Token is valid but does not have permission to access this share/table | Verify you are using the correct `config.json` for this hackathon |
| `HTTP 404 Not Found` | Wrong share, schema, or table name in the FQN | Check the FQN against the list returned by `list_all_tables` |
| `FileNotFoundError: config.json` | Profile path is wrong | Make sure `config.json` is in the repo root and `DELTA_SHARING_PROFILE` in `.env` points to it |
| DataFrame has fewer rows than expected | `DELTA_SHARING_LIMIT` is set low | Increase `DELTA_SHARING_LIMIT` in `.env` or set it to `0` to load all rows |
| `TypeError` on `load_as_pandas` with `limit=` | Older version of `delta-sharing` | Upgrade: `pip install --upgrade delta-sharing` |

---

## 8. Quick reference

```python
import delta_sharing

# 1. Discover tables
client = delta_sharing.SharingClient("config.json")
tables = client.list_all_tables()

# 2. Load a single table (up to 1000 rows)
df = delta_sharing.load_as_pandas("config.json#centercode_share.centercode.zcc_act_stat", limit=1000)

# 3. Load all rows (no limit)
df_full = delta_sharing.load_as_pandas("config.json#centercode_share.centercode.zcc_act_stat")
```

**Table URL format:**
```
{profile_file_path}#{share_name}.{schema_name}.{table_name}
```

**The six hackathon tables:**
```
config.json#centercode_share.centercode.zcc_act_stat   → activity engagement status
config.json#centercode_share.centercode.zcc_prj_hdr    → project (program) headers
config.json#centercode_share.centercode.zcc_prt_mtrc   → participant metrics
config.json#centercode_share.centercode.zcc_ptm_lnk    → participant/team links
config.json#centercode_share.centercode.zcc_qa_sat     → satisfaction survey scores
config.json#centercode_share.centercode.zcc_tkt_itm    → feedback tickets
```

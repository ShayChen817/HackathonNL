"""
deterministic_engine.py — Compute Active Tester count deterministically.
============================================================================
Uses the governed rulebook to apply exact Collibra business logic to data.
No LLM involved — pure pandas computation from governed definitions.

Active Tester Flag (Collibra Measure 019c9f78-2633-7377-9050-c1b3d84eb68d):
  A tester is 'active' if they meet AT LEAST ONE of:
    1. Submitted >= 3 feedback tickets        (from zcc_tkt_itm)
    2. Completed >= 2 surveys                 (zcc_prt_mtrc.Z_SRV_CMP)
    3. Completed activities > (incomplete + blocked + opted-out)
       (Z_ACT_CMP > Z_ACT_INC + Z_ACT_BLK + Z_ACT_OPT)

Project filter:
  'Ongoing' projects: zcc_prj_hdr.Z_PRJ_STAT == 'Ongoing'

Participant identifier: Z_SMTP_ADR (hashed email, consistent across tables)
"""

import os
import pandas as pd
import delta_sharing
from dotenv import load_dotenv

load_dotenv()


class DeterministicEngine:
    """Compute governed metrics deterministically from Delta Sharing data."""

    def __init__(self):
        self.profile = os.getenv("DELTA_SHARING_PROFILE", "config.json")
        self._cache = {}

    def _load(self, table: str) -> pd.DataFrame:
        if table not in self._cache:
            url = f"{self.profile}#centercode_share.centercode.{table}"
            self._cache[table] = delta_sharing.load_as_pandas(url)
            print(f"  [LOAD] {table}: {self._cache[table].shape[0]} rows")
        return self._cache[table]

    def count_active_testers(self, ongoing_only: bool = True) -> dict:
        """
        Count active testers using the governed Active Tester Flag definition.
        
        Returns a dict with the answer and full provenance.
        """
        # ── Step 1: Load tables ──────────────────────────────────────
        prt = self._load("zcc_prt_mtrc")   # participant metrics
        tkt = self._load("zcc_tkt_itm")    # feedback tickets
        prj = self._load("zcc_prj_hdr")    # project header

        # ── Step 2: Filter to ongoing projects if requested ──────────
        if ongoing_only:
            ongoing_ids = set(prj[prj["Z_PRJ_STAT"] == "Ongoing"]["Z_PRJ_NR"])
            prt_filtered = prt[prt["Z_PRJ_OID"].isin(ongoing_ids)].copy()
            tkt_filtered = tkt[tkt["Z_PRJ_NR"].isin(ongoing_ids)].copy()
            project_filter = f"Z_PRJ_STAT == 'Ongoing' ({len(ongoing_ids)} projects)"
        else:
            prt_filtered = prt.copy()
            tkt_filtered = tkt.copy()
            ongoing_ids = set(prj["Z_PRJ_NR"])
            project_filter = f"All projects ({len(ongoing_ids)} projects)"

        total_participants = prt_filtered["Z_SMTP_ADR"].nunique()

        # ── Step 3: Criterion 1 — feedback tickets >= 3 ─────────────
        # Count distinct tickets per participant per project
        ticket_counts = (
            tkt_filtered
            .groupby("Z_SMTP_ADR")["Z_TKT_NR"]
            .nunique()
            .reset_index()
            .rename(columns={"Z_TKT_NR": "ticket_count"})
        )
        crit1_emails = set(
            ticket_counts[ticket_counts["ticket_count"] >= 3]["Z_SMTP_ADR"]
        )

        # ── Step 4: Criterion 2 — surveys completed >= 2 ────────────
        survey_counts = (
            prt_filtered
            .groupby("Z_SMTP_ADR")["Z_SRV_CMP"]
            .sum()
            .reset_index()
        )
        survey_counts["Z_SRV_CMP"] = pd.to_numeric(survey_counts["Z_SRV_CMP"], errors="coerce").fillna(0)
        crit2_emails = set(
            survey_counts[survey_counts["Z_SRV_CMP"] >= 2]["Z_SMTP_ADR"]
        )

        # ── Step 5: Criterion 3 — completed > (incomplete + blocked + opted_out) ─
        prt_act = prt_filtered.copy()
        for col in ["Z_ACT_CMP", "Z_ACT_INC", "Z_ACT_BLK", "Z_ACT_OPT"]:
            prt_act[col] = pd.to_numeric(prt_act[col], errors="coerce").fillna(0)

        # Aggregate across projects per participant
        act_agg = (
            prt_act
            .groupby("Z_SMTP_ADR")[["Z_ACT_CMP", "Z_ACT_INC", "Z_ACT_BLK", "Z_ACT_OPT"]]
            .sum()
            .reset_index()
        )
        act_agg["non_completed"] = act_agg["Z_ACT_INC"] + act_agg["Z_ACT_BLK"] + act_agg["Z_ACT_OPT"]
        crit3_emails = set(
            act_agg[act_agg["Z_ACT_CMP"] > act_agg["non_completed"]]["Z_SMTP_ADR"]
        )

        # ── Step 6: Combine with OR logic ────────────────────────────
        active_emails = crit1_emails | crit2_emails | crit3_emails

        # ── Step 7: Build provenance ─────────────────────────────────
        return {
            "question": "How many active testers do we have?"
                        + (" (ongoing programs)" if ongoing_only else " (all programs)"),
            "answer": len(active_emails),
            "total_unique_participants": total_participants,
            "project_filter": project_filter,
            "criteria_breakdown": {
                "criterion_1_tickets_gte_3": len(crit1_emails),
                "criterion_2_surveys_gte_2": len(crit2_emails),
                "criterion_3_completed_gt_rest": len(crit3_emails),
            },
            "combination_logic": "OR (any one criterion met = active)",
            "governed_sources": {
                "business_term": "Active Tester",
                "business_term_asset": "0198c234-11fe-73ff-be9b-c91312850031",
                "measure": "Active Tester Flag",
                "measure_asset": "019c9f78-2633-7377-9050-c1b3d84eb68d",
                "definition": (
                    "A tester is active if they meet at least one of: "
                    "(1) Submitted >=3 feedback tickets, "
                    "(2) Completed >=2 surveys, "
                    "(3) Completed activities outnumber incomplete+blocked+opted-out"
                ),
            },
            "tables_used": ["zcc_prt_mtrc", "zcc_tkt_itm", "zcc_prj_hdr"],
            "columns_used": {
                "zcc_prt_mtrc": ["Z_PRJ_OID", "Z_SMTP_ADR", "Z_ACT_CMP", "Z_ACT_INC", "Z_ACT_BLK", "Z_ACT_OPT", "Z_SRV_CMP"],
                "zcc_tkt_itm": ["Z_SMTP_ADR", "Z_PRJ_NR", "Z_TKT_NR"],
                "zcc_prj_hdr": ["Z_PRJ_NR", "Z_PRJ_STAT"],
            },
        }

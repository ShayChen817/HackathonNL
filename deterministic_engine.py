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

        Default answer grain is participant-program pairs so the deterministic
        endpoint matches the governed SQL used in /api/ask.
        
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

        total_participants = int(prt_filtered["Z_SMTP_ADR"].nunique())

        # ── Step 3: Build participant-program universe ──────────────
        pair_universe_df = prt_filtered[["Z_SMTP_ADR", "Z_PRJ_OID"]].drop_duplicates()
        total_pair_count = int(pair_universe_df.shape[0])

        # ── Step 4: Criterion 1 — feedback tickets >= 3 (pair grain) ─
        feedback_completion = (
            tkt_filtered
            .groupby(["Z_SMTP_ADR", "Z_PRJ_NR"])["Z_TKT_NR"]
            .nunique()
            .reset_index(name="feedback_ticket_count")
        )
        crit1_df = pair_universe_df.merge(
            feedback_completion,
            left_on=["Z_SMTP_ADR", "Z_PRJ_OID"],
            right_on=["Z_SMTP_ADR", "Z_PRJ_NR"],
            how="left",
        )
        crit1_df["feedback_ticket_count"] = pd.to_numeric(
            crit1_df["feedback_ticket_count"], errors="coerce"
        ).fillna(0)
        crit1_pairs = set(
            tuple(x)
            for x in crit1_df.loc[
                crit1_df["feedback_ticket_count"] >= 3,
                ["Z_SMTP_ADR", "Z_PRJ_OID"],
            ].drop_duplicates().to_records(index=False)
        )

        # ── Step 5: Criterion 2/3 — row-level governed checks, dedup at pair grain ─
        prt_eval = prt_filtered.copy()
        for col in ["Z_SRV_CMP", "Z_ACT_CMP", "Z_ACT_INC", "Z_ACT_BLK", "Z_ACT_OPT"]:
            prt_eval[col] = pd.to_numeric(prt_eval[col], errors="coerce").fillna(0)

        crit2_pairs = set(
            tuple(x)
            for x in prt_eval.loc[
                prt_eval["Z_SRV_CMP"] >= 2,
                ["Z_SMTP_ADR", "Z_PRJ_OID"],
            ].drop_duplicates().to_records(index=False)
        )
        crit3_pairs = set(
            tuple(x)
            for x in prt_eval.loc[
                prt_eval["Z_ACT_CMP"] > (prt_eval["Z_ACT_INC"] + prt_eval["Z_ACT_BLK"] + prt_eval["Z_ACT_OPT"]),
                ["Z_SMTP_ADR", "Z_PRJ_OID"],
            ].drop_duplicates().to_records(index=False)
        )

        # ── Step 6: OR union + inclusion-exclusion components ────────
        active_pairs = crit1_pairs | crit2_pairs | crit3_pairs
        ab_pairs = crit1_pairs & crit2_pairs
        ac_pairs = crit1_pairs & crit3_pairs
        bc_pairs = crit2_pairs & crit3_pairs
        abc_pairs = crit1_pairs & crit2_pairs & crit3_pairs

        active_unique_people = len({email for email, _ in active_pairs})
        formula_text = (
            f"|A ∪ B ∪ C| = {len(crit1_pairs)} + {len(crit2_pairs)} + {len(crit3_pairs)} "
            f"- {len(ab_pairs)} - {len(ac_pairs)} - {len(bc_pairs)} + {len(abc_pairs)} = {len(active_pairs)}"
        )

        # ── Step 7: Build provenance ─────────────────────────────────
        return {
            "question": "How many active testers do we have?"
                        + (" (ongoing programs)" if ongoing_only else " (all programs)"),
            "answer": len(active_pairs),
            "answer_grain": "participant-program pairs",
            "active_tester_participations": len(active_pairs),
            "unique_active_testers": active_unique_people,
            "total_unique_participants": total_participants,
            "total_participant_program_pairs": total_pair_count,
            "project_filter": project_filter,
            "criteria_breakdown": {
                "criterion_1_tickets_gte_3": len(crit1_pairs),
                "criterion_2_surveys_gte_2": len(crit2_pairs),
                "criterion_3_completed_gt_rest": len(crit3_pairs),
            },
            "criteria_intersections": {
                "criterion_1_and_2": len(ab_pairs),
                "criterion_1_and_3": len(ac_pairs),
                "criterion_2_and_3": len(bc_pairs),
                "criterion_1_and_2_and_3": len(abc_pairs),
            },
            "inclusion_exclusion_formula": formula_text,
            "combination_logic": "OR at participant-program grain (any one criterion met = active)",
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

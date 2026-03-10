"""
rulebook.py — Deterministic Governed Rulebook
==============================================
Encodes exact business definitions from Collibra into executable rules.
All column names, filter values, and logic verified against actual data.

Sources:
  - Active Tester (Business Term): Collibra asset 0198c234-11fe-73ff-be9b-c91312850031
  - Active Tester Flag (Measure):  Collibra asset 019c9f78-2633-7377-9050-c1b3d84eb68d
  - Physical Data Layer:           Collibra domain 019c9e17-b6f2-725e-9181-dbda44044df9

Verified column names and values:
  - zcc_prj_hdr.Z_PRJ_STAT: {'Finished': 80, 'Ongoing': 20}
  - zcc_act_stat.Z_ENG_ST:  {'Unengaged', 'Completed', 'Viewed', 'Blocked', 'Not applicable'}
  - zcc_prt_mtrc columns:   Z_ACT_BLK, Z_ACT_CMP, Z_ACT_INC, Z_ACT_OPT, Z_SRV_CMP
  - zcc_tkt_itm columns:    Z_TKT_NR, Z_SMTP_ADR, Z_PRJ_NR
"""

# ══════════════════════════════════════════════════════════════════════
# GOVERNED DEFINITIONS — copied verbatim from Collibra API responses
# ══════════════════════════════════════════════════════════════════════

ACTIVE_TESTER_DEFINITION = """
An active participant in a preview program. We consider that a tester is active 
or engaged if:
  - They have completed at least half of the activities/test scenarios, OR
  - They have completed at least two program surveys, OR
  - They have logged at least three feedback tickets.

Extra indicators to help determine how active a participant is:
  # logins in Centercode
  # votes on other participants' tickets
  # comments logged in other participants' tickets
"""

ACTIVE_TESTER_FLAG_DEFINITION = """
A tester is considered 'active' if they meet at least one of these criteria:
  1. Submitted 3 or more feedback tickets
  2. Completed 2 or more surveys
  3. Completed more than half of their assigned activities
     (i.e. completed activities outnumber the sum of incomplete, blocked, 
      and opted-out ones)
"""

PROJECT_STATUS_DEFINITION = """
zcc_prj_hdr.Z_PRJ_STAT:
  'Ongoing'  = the project has NOT been archived (still active)
  'Finished' = the project HAS an archive date (completed)
"""

# ══════════════════════════════════════════════════════════════════════
# COLUMN MAPPING — verified from Collibra Physical Layer + actual data
# ══════════════════════════════════════════════════════════════════════

COLUMN_MAP = {
    # zcc_prt_mtrc — Participant metrics (one row per participant per project)
    "zcc_prt_mtrc.Z_PRJ_OID":   "Unique identifier for the project",
    "zcc_prt_mtrc.Z_PRJ_TXT":   "Name of the project",
    "zcc_prt_mtrc.Z_SMTP_ADR":  "Email address (hashed) of the participant",
    "zcc_prt_mtrc.Z_PRT_NM":    "Full name (hashed) of the participant",
    "zcc_prt_mtrc.Z_ACT_CMP":   "Number of activities the participant has completed",
    "zcc_prt_mtrc.Z_ACT_INC":   "Number of activities the participant has started but not finished",
    "zcc_prt_mtrc.Z_ACT_BLK":   "Number of activities the participant has blocked",
    "zcc_prt_mtrc.Z_ACT_OPT":   "Number of activities the participant has opted out of",
    "zcc_prt_mtrc.Z_SRV_CMP":   "Number of surveys the participant has completed",
    "zcc_prt_mtrc.Z_FLW_MENGE": "Number of items the participant is following",
    "zcc_prt_mtrc.Z_USR_IMP":   "Participant-level aggregate impact metric",
    "zcc_prt_mtrc.Z_SMTP_DOM":  "Domain name of the participant's email address",
    "zcc_prt_mtrc.Z_PTM_LST":   "Comma-separated list of project teams",

    # zcc_tkt_itm — Feedback tickets
    "zcc_tkt_itm.Z_TKT_NR":    "Unique identifier for the ticket",
    "zcc_tkt_itm.Z_SMTP_ADR":  "Email address (hashed) of submitter",
    "zcc_tkt_itm.Z_PRJ_NR":    "Unique identifier for the project",
    "zcc_tkt_itm.Z_TKT_ART":   "Type of feedback ticket: issue, idea, praise, or discussion",
    "zcc_tkt_itm.Z_IMP_SC":    "Impact score per ticket",

    # zcc_prj_hdr — Project header
    "zcc_prj_hdr.Z_PRJ_NR":    "Unique identifier of the project",
    "zcc_prj_hdr.Z_PRJ_STAT":  "'Ongoing' if not archived, 'Finished' if archived",
    "zcc_prj_hdr.Z_PRJ_TXT":   "Name of the project",
}

# ══════════════════════════════════════════════════════════════════════
# ACTIVE TESTER FLAG — The 3 criteria (from Collibra Measure definition)
# ══════════════════════════════════════════════════════════════════════
#
# Relations from Active Tester Flag in Collibra:
#   Active Tester Flag --> Participant.Blocked Activities   (Z_ACT_BLK)
#   Active Tester Flag --> Participant.Incomplete Activities (Z_ACT_INC)
#   Active Tester Flag --> Participant.Opted Out Activities  (Z_ACT_OPT)
#   Active Tester Flag --> Participant.Completed Activities  (Z_ACT_CMP)
#   Active Tester Flag --> Number of ticket per participant  (count from zcc_tkt_itm)
#   Active Tester Flag --> Active Tester                     (business term link)
#
# Criterion 1: feedback_tickets >= 3
#   Source: COUNT(DISTINCT Z_TKT_NR) FROM zcc_tkt_itm GROUP BY Z_SMTP_ADR, Z_PRJ_NR
#
# Criterion 2: surveys_completed >= 2
#   Source: zcc_prt_mtrc.Z_SRV_CMP >= 2
#
# Criterion 3: completed > (incomplete + blocked + opted_out)
#   Source: Z_ACT_CMP > (Z_ACT_INC + Z_ACT_BLK + Z_ACT_OPT)
#   Note: "more than half" means completed outnumber the rest
#
# Scope: when "ongoing" is specified, filter to zcc_prj_hdr.Z_PRJ_STAT = 'Ongoing'
# Grain: one participant can appear in multiple projects. Count DISTINCT participants.
# Identifier: Z_SMTP_ADR (hashed email) is the unique participant identifier.

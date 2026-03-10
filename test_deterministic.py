"""
test_deterministic.py — Run Active Tester count 20 times to prove determinism.
"""

import sys
import json
import time
from datetime import datetime
from deterministic_engine import DeterministicEngine


def run_test(num_runs: int = 20):
    print("=" * 80)
    print("  DETERMINISTIC TEST: Active Tester Count")
    print("  Governed by Collibra assets:")
    print("    Business Term: Active Tester (0198c234-11fe-73ff-be9b-c91312850031)")
    print("    Measure:       Active Tester Flag (019c9f78-2633-7377-9050-c1b3d84eb68d)")
    print(f"  Runs: {num_runs}")
    print(f"  Time: {datetime.now().isoformat()}")
    print("=" * 80)

    engine = DeterministicEngine()
    results = []
    counts = []

    for i in range(1, num_runs + 1):
        start = time.time()
        result = engine.count_active_testers(ongoing_only=True)
        elapsed = time.time() - start

        count = result["answer"]
        counts.append(count)
        results.append({"run": i, "count": count, "elapsed": round(elapsed, 4)})

        c1 = result["criteria_breakdown"]["criterion_1_tickets_gte_3"]
        c2 = result["criteria_breakdown"]["criterion_2_surveys_gte_2"]
        c3 = result["criteria_breakdown"]["criterion_3_completed_gt_rest"]

        print(f"  Run {i:2d}/{num_runs}: {count} active testers "
              f"(C1={c1}, C2={c2}, C3={c3}) [{elapsed:.3f}s]")

    # ── Summary ──────────────────────────────────────────────────────
    print()
    print("=" * 80)
    print("  RESULTS")
    print("=" * 80)
    print(f"  All {num_runs} results: {counts}")
    print()

    unique = set(counts)
    is_deterministic = len(unique) == 1

    if is_deterministic:
        print(f"  ✅ DETERMINISTIC: All {num_runs} runs returned: {counts[0]}")
        print(f"     Same question → same answer, every time.")
    else:
        print(f"  ❌ NOT DETERMINISTIC: {len(unique)} different values: {unique}")

    print()
    print("  📚 Governed Definition Used:")
    print("     A tester is active if they meet at least ONE of:")
    print("       1. Submitted >= 3 feedback tickets")
    print("       2. Completed >= 2 surveys")
    print("       3. Completed activities > (incomplete + blocked + opted-out)")
    print()
    print("  🔗 Collibra Sources:")
    print("     Active Tester:      0198c234-11fe-73ff-be9b-c91312850031")
    print("     Active Tester Flag: 019c9f78-2633-7377-9050-c1b3d84eb68d")
    print()
    print(f"  📊 Project Filter: Ongoing only (Z_PRJ_STAT == 'Ongoing')")
    print(f"     Total participants: {result['total_unique_participants']}")
    print(f"     Active testers:     {result['answer']}")
    print("=" * 80)

    # Save
    with open("deterministic_test_results.json", "w") as f:
        json.dump({
            "question": "How many active testers do we have in ongoing programs?",
            "answer": counts[0] if is_deterministic else None,
            "is_deterministic": is_deterministic,
            "num_runs": num_runs,
            "all_results": counts,
            "criteria_breakdown": result["criteria_breakdown"],
            "governed_sources": result["governed_sources"],
            "runs": results,
            "timestamp": datetime.now().isoformat(),
        }, f, indent=2)
    print(f"\n  Saved to deterministic_test_results.json")

    return is_deterministic, counts[0] if is_deterministic else None


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 20
    ok, answer = run_test(n)
    if ok:
        print(f"\n🎯 ANSWER: There are {answer} active testers in ongoing programs.")
    else:
        print("\n⚠️ Non-deterministic results detected.")
        sys.exit(1)

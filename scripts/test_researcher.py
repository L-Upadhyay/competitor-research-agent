# Manual test for the research/gather step (Agent 2): normal run, a failing search, and the search limit.

import os
import sys
from pathlib import Path

# Let this script find the "agent" folder in the project root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.researcher import MAX_SEARCHES, gather  # noqa: E402

COMPETITORS = ["Brex", "Airwallex", "Expensify"]


def starting_state(search_count):
    """A state as it would look right after discovery found the competitors."""
    return {
        "company": "Ramp",
        "company_context": "corporate card and spend management",
        "discovery_status": "found",
        "human_question": "",
        "competitors": COMPETITORS,
        "raw_results": {},
        "findings": {},
        "errors": [],
        "search_count": search_count,
        "brief": "",
    }


def summarize(updates):
    """Print a short summary instead of the full raw results."""
    print("--- summary ---")
    for competitor in COMPETITORS:
        entry = updates["raw_results"].get(competitor)
        if entry is None:
            print(f"{competitor}: not gathered")
            continue
        print(
            f"{competitor}: product={len(entry['product'])} "
            f"news={len(entry['news'])} complete={entry['complete']}"
        )
    print(f"errors: {updates['errors']}")
    print(f"search_count: {updates['search_count']} (limit {MAX_SEARCHES})")


def main():
    print("=== a) normal run (search_count starts at 1) ===")
    summarize(gather(starting_state(1)))

    print("\n=== b) FAIL_SEARCH_FOR=Airwallex (search_count starts at 1) ===")
    os.environ["FAIL_SEARCH_FOR"] = "Airwallex"
    try:
        summarize(gather(starting_state(1)))
    finally:
        # Turn the failure switch off again no matter what happened.
        os.environ.pop("FAIL_SEARCH_FOR", None)

    print("\n=== c) search_count starts at 9 (expect the limit to stop it partway) ===")
    summarize(gather(starting_state(9)))


if __name__ == "__main__":
    main()

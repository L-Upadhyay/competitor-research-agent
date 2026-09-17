# Manual test for the extraction step (Agent 3): gather with Airwallex failing, then extract.

import json
import os
import sys
from pathlib import Path

# Let this script find the "agent" folder in the project root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.extractor import extract  # noqa: E402
from agent.researcher import gather  # noqa: E402


def main():
    state = {
        "company": "Ramp",
        "company_context": "corporate card and spend management",
        "discovery_status": "found",
        "human_question": "",
        "competitors": ["Brex", "Airwallex", "Expensify"],
        "raw_results": {},
        "findings": {},
        "errors": [],
        "search_count": 1,
        "brief": "",
    }

    # Step 1: gather, with every Airwallex search forced to fail.
    os.environ["FAIL_SEARCH_FOR"] = "Airwallex"
    try:
        state.update(gather(state))
    finally:
        os.environ.pop("FAIL_SEARCH_FOR", None)

    # Step 2: extract findings from what was gathered.
    state.update(extract(state))

    print("\n=== findings ===")
    print(json.dumps(state["findings"], indent=2))
    print("\n=== errors ===")
    print(json.dumps(state["errors"], indent=2))


if __name__ == "__main__":
    main()

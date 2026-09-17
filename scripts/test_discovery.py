# Manual test for the discovery step (Agent 1) using three example companies.

import json
import sys
from pathlib import Path

# Let this script find the "agent" folder in the project root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.discovery import discover  # noqa: E402

CASES = [
    ("a) clear company with context", "Ramp", "corporate card and spend management"),
    ("b) ambiguous name (expect ambiguous)", "Mercury", ""),
    ("c) made-up company (expect not_found after a retry)", "Zxqvtrbl Labs", ""),
]


def starting_state(company, context):
    """A fresh, empty state for one run."""
    return {
        "company": company,
        "company_context": context,
        "discovery_status": "",
        "human_question": "",
        "competitors": [],
        "raw_results": {},
        "findings": {},
        "errors": [],
        "search_count": 0,
        "brief": "",
    }


def main():
    for label, company, context in CASES:
        print(f"\n=== {label} ===")
        updates = discover(starting_state(company, context))
        print("state updates:")
        print(json.dumps(updates, indent=2))


if __name__ == "__main__":
    main()

# Tests the Streamlit app (app.py) by clicking through it with fake tools (no API calls).
#
# Checks:
#   1. Happy path: enter a company, Start, accept competitors, approve -> success message.
#   2. You.com failing during discovery -> the handoff explanation is shown as an error.

import sys
from pathlib import Path

# Let this script find the "agent" folder and the edge-case fakes.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from streamlit.testing.v1 import AppTest  # noqa: E402

import agent.brief as brief  # noqa: E402
import agent.discovery as discovery  # noqa: E402
import agent.extractor as extractor  # noqa: E402
import agent.researcher as researcher  # noqa: E402
from test_edge_cases import (  # noqa: E402  (same fakes as the edge-case tests)
    FakeExtractionLLM,
    fake_discovery_llm,
    fake_search_fails,
    fake_search_works,
    fake_summary,
)

APP = str(ROOT / "app.py")
# A made-up company name, so the test brief never overwrites a real brief in outputs/.
TEST_COMPANY = "AppTestCo"


def report(name, passed, detail=""):
    print(f"{'PASS' if passed else 'FAIL'}  {name}" + (f"  ({detail})" if detail and not passed else ""))
    return passed


def start_run(at, company):
    """Type a company in the sidebar and press Start research."""
    at.run()
    at.text_input(key="company_input").input(company)
    at.button(key="start").click()
    at.run()


def test_happy_path():
    discovery.search_you = fake_search_works
    discovery._ask_llm = fake_discovery_llm
    researcher.search_you = fake_search_works
    extractor.get_llm = lambda: FakeExtractionLLM()
    brief._executive_summary = fake_summary

    at = AppTest.from_file(APP, default_timeout=60)
    start_run(at, TEST_COMPANY)
    if at.exception:
        return report("1. happy path -> success message", False, f"exception: {at.exception[0].message}")

    at.button(key="accept_competitors").click()
    at.run()
    at.button(key="approve").click()
    at.run()

    successes = [s.value for s in at.success]
    log = at.code[0].value if at.code else ""
    passed = (
        not at.exception
        and any("Brief saved to" in s for s in successes)
        and "[orchestrator] brief approved -> saving" in log
    )
    report("1. happy path -> success message", passed, f"success={successes}, exceptions={len(at.exception)}")

    # Clean up the test brief.
    for path in (ROOT / "outputs").glob(f"{TEST_COMPANY.lower()}_brief.md"):
        path.unlink()
    return passed


def test_search_failure_shows_handoff():
    discovery.search_you = fake_search_fails

    at = AppTest.from_file(APP, default_timeout=60)
    start_run(at, TEST_COMPANY)
    errors = [e.value for e in at.error]
    passed = not at.exception and any("You.com" in e and "YDC_API_KEY" in e for e in errors)
    return report("2. You.com failing -> handoff shown as error", passed, f"errors={errors}")


def main():
    results = [test_happy_path(), test_search_failure_shows_handoff()]
    print(f"\n{'ALL PASSED' if all(results) else 'SOME FAILED'}")


if __name__ == "__main__":
    main()

# Edge-case tests for the orchestrator using fake tools (no API calls, no cost).
#
# Checks:
#   1. You.com failing during discovery goes straight to handoff (no clarify question).
#   2. Typing "yes" at the confirm step keeps the competitor list.
#   3. Typing "yes" at the approval step saves the brief.
#   4. If every extraction fails, the run goes to handoff (no brief).

import contextlib
import io
import sys
from pathlib import Path

# Let this script find the "agent" folder in the project root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from langgraph.types import Command  # noqa: E402

import agent.brief as brief  # noqa: E402
import agent.discovery as discovery  # noqa: E402
import agent.extractor as extractor  # noqa: E402
import agent.researcher as researcher  # noqa: E402
from agent.graph import build_graph, initial_state, make_config  # noqa: E402

COMPETITORS = ["Brex", "Airwallex"]
TEST_FILENAME = "edge_case_test_brief.md"


# ---------- Fakes that stand in for the real services ----------


def fake_search_fails(query, count=5, recent_only=False):
    return {"ok": False, "error": "simulated You.com outage"}


def fake_search_works(query, count=5, recent_only=False):
    name = query.split()[0]
    return {
        "ok": True,
        "web": [{"title": f"{name} pricing", "url": f"https://example.com/{name}", "snippet": f"{name} costs $0."}],
        "news": [{"title": f"{name} news", "url": f"https://example.com/{name}/news",
                  "snippet": f"{name} announced something.", "date": "2026-09-01T10:00:00"}],
    }


def fake_discovery_llm(company, context, query, result):
    return discovery.DiscoveryDecision(
        same_name_companies=[company], status="found", competitors=COMPETITORS, question="", better_query=""
    )


class FakeExtractionLLM:
    """Pretends to be the OpenAI model used by the extractor."""

    def __init__(self, fail=False):
        self.fail = fail

    def with_structured_output(self, schema):
        return self

    def invoke(self, prompt):
        if self.fail:
            raise RuntimeError("simulated OpenAI outage")
        return extractor.CompetitorFindings(
            pricing="$0", core_features=["cards"], positioning="For startups.", recent_news=[], sources=[]
        )


def fake_summary(company, findings):
    return "Fake summary.", "fake-model", None


# ---------- Helpers ----------


def run_until_pause(graph, config, graph_input):
    """Run the graph, capturing everything it prints. Returns (result, printed_text)."""
    printed = io.StringIO()
    with contextlib.redirect_stdout(printed):
        result = graph.invoke(graph_input, config)
    return result, printed.getvalue()


def report(name, passed, detail=""):
    print(f"{'PASS' if passed else 'FAIL'}  {name}" + (f"  ({detail})" if detail and not passed else ""))
    return passed


# ---------- The tests ----------


def test_search_failure_goes_to_handoff():
    discovery.search_you = fake_search_fails
    graph, config = build_graph(), make_config()
    result, printed = run_until_pause(graph, config, initial_state("Ramp"))
    state = graph.get_state(config).values
    passed = (
        not result.get("__interrupt__")  # no clarify question
        and state["discovery_status"] == "error"
        and "HANDOFF" in printed
        and "You.com" in printed
        and "YDC_API_KEY" in printed
    )
    return report("1. You.com failing in discovery -> straight to handoff", passed,
                  f"status={state.get('discovery_status')}, interrupted={bool(result.get('__interrupt__'))}")


def test_yes_confirms_and_yes_approves():
    discovery.search_you = fake_search_works
    discovery._ask_llm = fake_discovery_llm
    researcher.search_you = fake_search_works
    extractor.get_llm = lambda: FakeExtractionLLM()
    brief._executive_summary = fake_summary

    graph, config = build_graph(), make_config(output_filename=TEST_FILENAME)
    result, _ = run_until_pause(graph, config, initial_state("Ramp", "corporate cards"))
    at_confirm = result.get("__interrupt__") and result["__interrupt__"][0].value["kind"] == "confirm_competitors"

    result, _ = run_until_pause(graph, config, Command(resume="yes"))
    state = graph.get_state(config).values
    ok_confirm = report("2. \"yes\" at confirm keeps the competitor list",
                        bool(at_confirm) and state["competitors"] == COMPETITORS,
                        f"competitors={state.get('competitors')}")

    at_approve = result.get("__interrupt__") and result["__interrupt__"][0].value["kind"] == "approve_brief"
    run_until_pause(graph, config, Command(resume="yes"))
    state = graph.get_state(config).values
    saved = state.get("saved_path") and Path(state["saved_path"]).exists()
    ok_approve = report("3. \"yes\" at approval saves the brief",
                        bool(at_approve) and state["human_decision"] == "approve" and bool(saved),
                        f"decision={state.get('human_decision')}, saved_path={state.get('saved_path')!r}")

    # Clean up the test file.
    if saved:
        Path(state["saved_path"]).unlink()
    return ok_confirm and ok_approve


def test_all_extractions_fail_goes_to_handoff():
    discovery.search_you = fake_search_works
    discovery._ask_llm = fake_discovery_llm
    researcher.search_you = fake_search_works
    extractor.get_llm = lambda: FakeExtractionLLM(fail=True)
    brief._executive_summary = fake_summary

    graph, config = build_graph(), make_config(output_filename=TEST_FILENAME)
    run_until_pause(graph, config, initial_state("Ramp", "corporate cards"))
    result, printed = run_until_pause(graph, config, Command(resume=""))
    state = graph.get_state(config).values
    passed = (
        not result.get("__interrupt__")  # never reached the approval step
        and not state.get("brief")
        and "HANDOFF" in printed
        and "extraction (OpenAI)" in printed
    )
    return report("4. all extractions failing -> handoff (no brief)", passed,
                  f"interrupted={bool(result.get('__interrupt__'))}, brief_written={bool(state.get('brief'))}")


def main():
    results = [
        test_search_failure_goes_to_handoff(),
        test_yes_confirms_and_yes_approves(),
        test_all_extractions_fail_goes_to_handoff(),
    ]
    print(f"\n{'ALL PASSED' if all(results) else 'SOME FAILED'}")


if __name__ == "__main__":
    main()

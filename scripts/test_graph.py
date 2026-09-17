# End-to-end test of the orchestrator graph, answering the human steps with scripted replies.

import os
import sys
from pathlib import Path

# Let this script find the "agent" folder in the project root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from langgraph.types import Command  # noqa: E402

from agent.graph import build_graph, initial_state, make_config  # noqa: E402


def run_case(label, company, context, answers, output_filename, fail_first_competitor=False):
    """Run the whole graph once, answering each pause from `answers` (keyed by pause kind)."""
    print(f"\n{'#' * 70}\n# {label}\n{'#' * 70}")
    os.environ.pop("FAIL_SEARCH_FOR", None)

    graph = build_graph()
    config = make_config(output_filename=output_filename)
    try:
        result = graph.invoke(initial_state(company, context), config)
        while result.get("__interrupt__"):
            payload = result["__interrupt__"][0].value
            kind = payload["kind"]
            queue = answers.get(kind, [])
            answer = queue.pop(0) if queue else ""

            if kind == "confirm_competitors" and fail_first_competitor:
                # Make every search for the first competitor fail from here on.
                os.environ["FAIL_SEARCH_FOR"] = payload["competitors"][0]
                print(f"[test] FAIL_SEARCH_FOR={payload['competitors'][0]}")

            shown = payload.get("competitors") if kind == "confirm_competitors" else payload.get("message", "")[:120]
            if kind == "approve_brief":
                shown = "(brief shown)"
            print(f"[human] {kind}: {shown!r} -> answering {answer!r}")
            result = graph.invoke(Command(resume=answer), config)
    finally:
        os.environ.pop("FAIL_SEARCH_FOR", None)

    final = graph.get_state(config).values
    print(f"[test] brief_model={final.get('brief_model')!r} saved_path={final.get('saved_path')!r}")
    if final.get("saved_path"):
        lines = Path(final["saved_path"]).read_text(encoding="utf-8").splitlines()
        print(f"\n----- first 40 lines of {Path(final['saved_path']).name} -----")
        print("\n".join(lines[:40]))
    return final


def main():
    run_case(
        "a) Ramp with context: accept competitors, approve",
        "Ramp", "corporate card and spend management",
        answers={"confirm_competitors": [""], "approve_brief": ["approve"]},
        output_filename="ramp_brief.md",
    )
    run_case(
        "b) Mercury, no context: clarify, accept, approve",
        "Mercury", "",
        answers={
            "clarify": ["the fintech business bank for startups"],
            "confirm_competitors": [""],
            "approve_brief": ["approve"],
        },
        output_filename="mercury_brief.md",
    )
    run_case(
        "c) Ramp with the first competitor's searches failing: accept, approve",
        "Ramp", "corporate card and spend management",
        answers={"confirm_competitors": [""], "approve_brief": ["approve"]},
        output_filename="ramp_brief_with_failure.md",
        fail_first_competitor=True,
    )


if __name__ == "__main__":
    main()

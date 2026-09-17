# Builds and compiles the LangGraph workflow connecting the agent nodes.
#
# The orchestrator, in plain English:
#
#   discover ──found──────────────> confirm_competitors (human checks the list)
#      │                                   │
#      ├─ambiguous / not_found─> clarify ──┘ back to discover (at most 2 clarifications)
#      └─still stuck after 2 clarifications──> handoff (explain what failed) ─> END
#
#   confirm_competitors -> gather -> extract ──no data at all──> handoff ─> END
#                                       └─some data─> write_brief -> approve_brief (human reads it)
#
#   approve_brief ──"approve"──> save_brief -> END
#                 └─anything else──> END (not saved)
#
# "Human" steps pause the graph with interrupt(). The runner shows the question,
# collects an answer, and resumes the graph with Command(resume=answer).

import re
import uuid
from pathlib import Path

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from agent.brief import write_brief
from agent.discovery import discover
from agent.extractor import extract
from agent.researcher import gather
from agent.state import AgentState

# How many times we'll ask the human to clarify the company before giving up.
MAX_CLARIFY_ATTEMPTS = 2

# Safety cap on the number of steps in one run, so a loop can't run forever.
RECURSION_LIMIT = 25

# Where approved briefs are saved.
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "outputs"


def _log(message):
    """Print one short line about a routing decision."""
    print(f"[orchestrator] {message}")


# ---------- Human-in-the-loop steps ----------


def clarify(state):
    """Pause and ask the human which company they mean. Their answer becomes the context."""
    answer = interrupt({
        "kind": "clarify",
        "message": state.get("human_question") or f"Can you tell me more about {state['company']}?",
    })
    return {
        "company_context": str(answer).strip(),
        "clarify_attempts": state.get("clarify_attempts", 0) + 1,
    }


def confirm_competitors(state):
    """Pause and let the human accept the competitor list or type a replacement."""
    competitors = state.get("competitors", [])
    answer = interrupt({
        "kind": "confirm_competitors",
        "competitors": competitors,
        "message": f"Competitors found: {', '.join(competitors)}\n"
        "Press Enter to accept, or type a comma-separated list to replace them.",
    })
    replacement = [name.strip() for name in str(answer).split(",") if name.strip()]
    if replacement:
        _log(f"human replaced competitors -> {', '.join(replacement)}")
        return {"competitors": replacement}
    _log("human accepted competitors")
    return {"competitors": competitors}


def approve_brief(state):
    """Pause and show the brief; the human replies "approve" or "reject"."""
    answer = interrupt({
        "kind": "approve_brief",
        "brief": state.get("brief", ""),
        "message": 'Type "approve" to save this brief, or "reject" to discard it.',
    })
    return {"human_decision": str(answer).strip().lower()}


# ---------- Final steps ----------


def save_brief(state, config):
    """Write the approved brief to outputs/<company>_brief.md.

    A different file name can be passed in the run config as "output_filename"
    (the test script uses this so runs don't overwrite each other).
    """
    slug = re.sub(r"[^a-z0-9]+", "_", state["company"].lower()).strip("_") or "company"
    filename = config.get("configurable", {}).get("output_filename") or f"{slug}_brief.md"
    OUTPUT_DIR.mkdir(exist_ok=True)
    path = OUTPUT_DIR / filename
    path.write_text(state["brief"], encoding="utf-8")
    _log(f"brief saved -> {path}")
    return {"saved_path": str(path)}


def handoff(state):
    """Explain clearly what went wrong and what the human should do next."""
    print("\n" + "=" * 60)
    print("HANDOFF: the agent couldn't finish on its own.")
    if state.get("discovery_status") != "found":
        print(f"What failed: couldn't identify competitors for \"{state['company']}\" "
              f"after {state.get('clarify_attempts', 0)} clarification(s).")
        if state.get("human_question"):
            print(f"Last open question: {state['human_question']}")
        print("What to do: run again with a more specific description, e.g. the company's "
              "industry, product or website.")
    else:
        print("What failed: no search data could be gathered for any competitor.")
        print("What to do: check YDC_API_KEY in .env and your internet connection "
              "(and that the --fail demo flag isn't set), then run again.")
    errors = state.get("errors", [])
    if errors:
        print("Errors recorded:")
        for error in errors:
            print(f"  - {error}")
    print("=" * 60 + "\n")
    return {"saved_path": ""}


# ---------- Routing decisions ----------


def route_after_discovery(state):
    """Decide where to go after discovery."""
    status = state.get("discovery_status")
    if status == "found":
        _log(f"discovery found -> asking human to confirm {len(state.get('competitors', []))} competitors")
        return "confirm_competitors"
    if state.get("clarify_attempts", 0) >= MAX_CLARIFY_ATTEMPTS:
        _log(f"discovery {status} after {MAX_CLARIFY_ATTEMPTS} clarifications -> handoff")
        return "handoff"
    _log(f"discovery {status} -> asking human")
    return "clarify"


def route_after_extraction(state):
    """Write a brief if at least one competitor has data; otherwise hand off."""
    raw_results = state.get("raw_results", {})
    with_data = [
        name for name in state.get("competitors", [])
        if raw_results.get(name, {}).get("product") or raw_results.get(name, {}).get("news")
    ]
    if not with_data:
        _log("no competitor has any data -> handoff")
        return "handoff"
    _log(f"data for {len(with_data)}/{len(state.get('competitors', []))} competitors -> writing brief")
    return "write_brief"


def route_after_approval(state):
    """Save the brief only if the human approved it."""
    if state.get("human_decision") == "approve":
        _log("brief approved -> saving")
        return "save_brief"
    _log(f"brief not approved ({state.get('human_decision') or 'no answer'}) -> not saved")
    return END


# ---------- Wiring it all together ----------


def build_graph():
    """Create the workflow and return it ready to run (with in-memory checkpoints)."""
    graph = StateGraph(AgentState)

    graph.add_node("discover", discover)
    graph.add_node("clarify", clarify)
    graph.add_node("confirm_competitors", confirm_competitors)
    graph.add_node("gather", gather)
    graph.add_node("extract", extract)
    graph.add_node("write_brief", write_brief)
    graph.add_node("approve_brief", approve_brief)
    graph.add_node("save_brief", save_brief)
    graph.add_node("handoff", handoff)

    graph.add_edge(START, "discover")
    graph.add_conditional_edges("discover", route_after_discovery, ["confirm_competitors", "clarify", "handoff"])
    graph.add_edge("clarify", "discover")
    graph.add_edge("confirm_competitors", "gather")
    graph.add_edge("gather", "extract")
    graph.add_conditional_edges("extract", route_after_extraction, ["write_brief", "handoff"])
    graph.add_edge("write_brief", "approve_brief")
    graph.add_conditional_edges("approve_brief", route_after_approval, ["save_brief", END])
    graph.add_edge("save_brief", END)
    graph.add_edge("handoff", END)

    # The checkpointer remembers where each run paused, so it can resume after a human answers.
    return graph.compile(checkpointer=InMemorySaver())


def make_config(thread_id=None, output_filename=None):
    """Settings for one run: a unique thread id (which run this is) and the step limit."""
    configurable = {"thread_id": thread_id or str(uuid.uuid4())}
    if output_filename:
        configurable["output_filename"] = output_filename
    return {"configurable": configurable, "recursion_limit": RECURSION_LIMIT}


def initial_state(company, company_context=""):
    """A fresh, empty state to start a run."""
    return {
        "company": company.strip(),
        "company_context": company_context.strip(),
        "discovery_status": "",
        "human_question": "",
        "competitors": [],
        "raw_results": {},
        "findings": {},
        "errors": [],
        "search_count": 0,
        "brief": "",
        "clarify_attempts": 0,
        "brief_model": "",
        "saved_path": "",
        "human_decision": "",
    }

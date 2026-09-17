# Streamlit web interface for the competitor research agent.
#
# Launch with:  uv run streamlit run app.py
#
# How it works, in plain English:
#   Streamlit re-runs this whole file every time you click a button. So everything
#   that must survive a click (the running agent, where it paused, the log, the
#   final result) is kept in st.session_state, Streamlit's memory for this browser tab.
#
#   The agent runs until it needs a human answer, then pauses. This page shows the
#   question (clarify / confirm competitors / approve brief), and your click resumes it.
#   The terminal version (main.py) still works as a fallback.

import contextlib
import io
import os
import time
from pathlib import Path

import streamlit as st
from langgraph.types import Command

from agent.graph import build_graph, initial_state, make_config

st.set_page_config(page_title="Competitor Research Agent", page_icon="🔎")


# ---------- Memory that survives button clicks ----------

DEFAULTS = {
    "graph": None,       # the agent workflow for the current run
    "config": None,      # run settings, including the thread_id that identifies this run
    "payload": None,     # what the agent is currently asking the human (None if not paused)
    "pause_number": 0,   # counts pauses, so input boxes reset for each new question
    "log": "",           # everything the agent printed (its decisions)
    "final": None,       # the agent's final state once the run has ended
    "last_output": "",   # what the agent printed during its most recent step
    "run_error": "",     # a friendly error message if something crashed
    "agent_seconds": 0.0,  # total time the agent spent working (not time waiting for the human)
    "steps": 0,          # how many times the agent ran between human answers
}
for key, value in DEFAULTS.items():
    if key not in st.session_state:
        st.session_state[key] = value


def reset():
    """Forget the current run and turn off the failure demo."""
    for key, value in DEFAULTS.items():
        st.session_state[key] = value
    os.environ.pop("FAIL_SEARCH_FOR", None)


def run_agent(graph_input):
    """Run (or resume) the agent until it pauses or finishes, capturing everything it prints."""
    captured = io.StringIO()

    def record_timing(start):
        """Add this step's working time to the log and the running total."""
        seconds = time.perf_counter() - start
        st.session_state.agent_seconds += seconds
        st.session_state.steps += 1
        st.session_state.log += f"[timing] this step took {seconds:.1f} s\n"

    # Only the agent's own work is timed; waiting for the human happens between calls.
    start = time.perf_counter()
    try:
        with st.spinner("The agent is working... this can take a minute."):
            with contextlib.redirect_stdout(captured):
                result = st.session_state.graph.invoke(graph_input, st.session_state.config)
    except Exception as e:
        st.session_state.log += captured.getvalue()
        record_timing(start)
        st.session_state.payload = None
        st.session_state.run_error = (
            f"Sorry, something went wrong and the run stopped ({e.__class__.__name__}: {e}). "
            "Check your API keys in .env and your internet connection, then press Reset and try again."
        )
        return

    st.session_state.log += captured.getvalue()
    record_timing(start)
    st.session_state.last_output = captured.getvalue()

    pauses = result.get("__interrupt__")
    if pauses:
        # The agent is waiting for a human answer.
        st.session_state.payload = pauses[0].value
        st.session_state.pause_number += 1
    else:
        # The agent has finished.
        st.session_state.payload = None
        st.session_state.final = st.session_state.graph.get_state(st.session_state.config).values


def resume(answer):
    """Send the human's answer back to the paused agent, then redraw the page."""
    run_agent(Command(resume=answer))
    st.rerun()


# ---------- Sidebar: start / reset ----------

with st.sidebar:
    st.header("New research")
    company = st.text_input("Company", key="company_input")
    context = st.text_input("Context (optional)", key="context_input", placeholder="e.g. corporate card and spend management")
    fail_for = st.text_input("Demo: make searches fail for", key="fail_input", placeholder="e.g. Brex (optional)")

    if st.button("Start research", key="start", type="primary"):
        if not company.strip():
            st.warning("Please enter a company name.")
        else:
            reset()
            # The failure demo only applies to this run.
            if fail_for.strip():
                os.environ["FAIL_SEARCH_FOR"] = fail_for.strip()
            st.session_state.graph = build_graph()
            st.session_state.config = make_config()
            run_agent(initial_state(company, context))
            st.rerun()

    if st.button("Reset", key="reset"):
        reset()
        st.rerun()


# ---------- Main page ----------

st.title("🔎 Competitor Research Agent")

payload = st.session_state.payload
final = st.session_state.final
n = st.session_state.pause_number

if st.session_state.run_error:
    st.error(st.session_state.run_error)

elif payload and payload.get("kind") == "clarify":
    # The agent isn't sure which company is meant.
    st.info(payload.get("message", "Can you tell me more about the company?"))
    answer = st.text_input("Your answer", key=f"clarify_answer_{n}")
    if st.button("Submit", key="clarify_submit"):
        if answer.strip():
            resume(answer)
        else:
            st.warning("Please type an answer first.")

elif payload and payload.get("kind") == "confirm_competitors":
    # The agent found competitors; the human accepts them or types their own list.
    st.subheader("Competitors found")
    for name in payload.get("competitors", []):
        st.markdown(f"- {name}")
    if st.button("Accept these competitors", key="accept_competitors", type="primary"):
        resume("")
    my_list = st.text_input(
        "Or edit the list (comma-separated)",
        value=", ".join(payload.get("competitors", [])),
        key=f"competitor_list_{n}",
    )
    if st.button("Use my list", key="use_my_list"):
        resume(my_list)

elif payload and payload.get("kind") == "approve_brief":
    # The brief is ready; the human decides whether to save it.
    st.subheader("Review the brief")
    with st.container(border=True):
        st.markdown(payload.get("brief", ""))
    col_approve, col_reject = st.columns(2)
    if col_approve.button("Approve and save", key="approve", type="primary"):
        resume("approve")
    if col_reject.button("Reject", key="reject"):
        resume("reject")

elif final is not None:
    # The run has ended: show how it ended.
    if final.get("saved_path"):
        path = Path(final["saved_path"])
        st.success(f"Brief saved to: {path}")
        if path.exists():
            st.download_button(
                "Download the brief", data=path.read_text(encoding="utf-8"),
                file_name=path.name, mime="text/markdown", key="download",
            )
    elif "HANDOFF" in st.session_state.last_output:
        # Show just the handoff explanation the agent printed.
        handoff_text = st.session_state.last_output[st.session_state.last_output.index("HANDOFF"):]
        st.error(handoff_text.strip().strip("=").strip())
    else:
        st.warning("Brief was not saved.")

    # Total time the agent itself spent working (time spent by the human answering isn't counted).
    minutes, seconds = divmod(round(st.session_state.agent_seconds), 60)
    steps = st.session_state.steps
    st.caption(f"Agent working time: {minutes} min {seconds} s across {steps} step{'s' if steps != 1 else ''}")

else:
    st.write("Enter a company in the sidebar and press **Start research**.")

# Always show what the agent decided, so the routing is visible on screen.
with st.expander("Agent decisions log", expanded=True):
    st.code(st.session_state.log or "(nothing yet)", language="text")

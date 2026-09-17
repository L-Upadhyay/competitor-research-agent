# Defines the shared state object passed between graph nodes.
#
# Think of AgentState as the agent's notebook. Every step of the agent
# (discovery, research, extraction, writing) reads from this notebook and
# writes its own results back into it, so the next step can pick up where
# the previous one left off.

from typing import TypedDict


class AgentState(TypedDict):
    # The company we are researching competitors for, e.g. "Ramp".
    company: str

    # Optional extra detail from the human to pin down which company they mean,
    # e.g. "the fintech bank". Empty if not needed.
    company_context: str

    # How the discovery step went:
    #   "found"      - we have a list of competitors
    #   "ambiguous"  - the company name could mean more than one company
    #   "not_found"  - we couldn't find enough information
    discovery_status: str

    # A question for the human when the agent is stuck and needs their help,
    # e.g. "Did you mean Mercury the bank or Mercury Insurance?"
    human_question: str

    # Names of the competitors the discovery step found, e.g. ["Brex", "Mercury"].
    competitors: list[str]

    # Raw search results for each competitor, before any cleanup.
    # Looks like: {"Brex": {...search results...}, "Mercury": {...}}
    raw_results: dict[str, dict]

    # Useful facts pulled out of the raw results for each competitor
    # (pricing, features, positioning, recent news).
    # Looks like: {"Brex": {...extracted info...}}
    findings: dict[str, dict]

    # Plain-English notes about anything that went wrong along the way,
    # so the run can continue and we can still see what failed.
    errors: list[str]

    # How many searches the agent has made so far (helps keep costs in check).
    search_count: int

    # The final written competitor brief.
    brief: str

    # How many times we've asked the human to clarify which company they mean.
    # After 2 tries we stop asking and hand over to the human.
    clarify_attempts: int

    # Which LLM wrote the brief's executive summary (e.g. a Nebius or OpenAI model).
    brief_model: str

    # Where the approved brief was saved on disk. Empty if it wasn't saved.
    saved_path: str

    # What the human said about the finished brief: "approve" or "reject".
    human_decision: str

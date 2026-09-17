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

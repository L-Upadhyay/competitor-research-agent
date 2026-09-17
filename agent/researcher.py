# Research step: gathers and summarizes details on each competitor.
#
# How it works, in plain English:
#   For each competitor found by the discovery step, run two web searches:
#     a) a product search  ("<competitor> pricing features")
#     b) a news search     ("<competitor> <context> news", recent results only)
#   The raw results are saved in the state for the extraction step to read.
#
# Safety nets:
#   - If a search comes back empty, try once more with different wording.
#   - If a search fails, note the error and carry on with the next search.
#   - Stop entirely once the whole run has used MAX_SEARCHES searches, to cap costs.

from agent.tools import search_you

# The most searches allowed in one whole run, counting the discovery step's searches.
MAX_SEARCHES = 12

# How many results to ask for in each search.
RESULTS_PER_SEARCH = 5


class SearchLimitReached(Exception):
    """Raised inside this file to stop gathering once the search budget is used up."""


def _log(message):
    """Print one short progress line."""
    print(f"[gather] {message}")


def gather(state):
    """Search for product info and news on each competitor. Returns only the changed state fields."""
    context = state.get("company_context", "").strip()
    errors = list(state.get("errors", []))
    raw_results = dict(state.get("raw_results", {}))
    search_count = state.get("search_count", 0)

    def search(competitor, kind, query, reworded_query, recent_only):
        """Run one search (plus one reworded retry if it comes back empty).

        Returns the list of results, or None if the search failed.
        Raises SearchLimitReached if we're out of searches.
        """
        nonlocal search_count

        for attempt_query in (query, reworded_query):
            # Check the budget BEFORE every search.
            if search_count >= MAX_SEARCHES:
                raise SearchLimitReached

            result = search_you(attempt_query, count=RESULTS_PER_SEARCH, recent_only=recent_only)
            search_count += 1

            if not result["ok"]:
                _log(f"{competitor}: {kind} search FAILED -> skipping")
                errors.append(f"{competitor}: {kind} search failed: {result['error']}")
                return None

            # Keep news first for news searches, web pages first for product searches.
            if kind == "news":
                items = result["news"] + result["web"]
            else:
                items = result["web"] + result["news"]

            if items:
                _log(f"{competitor}: {kind} search ({len(items)} results)")
                return items

            if attempt_query == query:
                _log(f"{competitor}: {kind} search (0 results) -> retrying as: {reworded_query}")

        # Still nothing after the reworded retry. That's not a failure, just no results.
        _log(f"{competitor}: {kind} search (0 results after retry)")
        return []

    try:
        for competitor in state["competitors"]:
            # Start this competitor's entry as incomplete; mark complete only if both searches work.
            entry = {"product": [], "news": [], "complete": False}
            raw_results[competitor] = entry

            product = search(
                competitor, "product",
                query=f"{competitor} pricing features",
                reworded_query=f"{competitor} official site",
                recent_only=False,
            )
            # Save right away, so these results survive if the news search hits the limit.
            entry["product"] = product or []

            news_query = f"{competitor} {context} news" if context else f"{competitor} company news"
            news = search(
                competitor, "news",
                query=news_query,
                reworded_query=f"{competitor} announcement",
                recent_only=True,
            )

            entry["news"] = news or []
            entry["complete"] = product is not None and news is not None

    except SearchLimitReached:
        _log("search limit reached")
        errors.append("search limit reached")
        # Competitors we never got to are still listed, marked incomplete.
        for competitor in state["competitors"]:
            raw_results.setdefault(competitor, {"product": [], "news": [], "complete": False})

    return {
        "raw_results": raw_results,
        "errors": errors,
        "search_count": search_count,
    }

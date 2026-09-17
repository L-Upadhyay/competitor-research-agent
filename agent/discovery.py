# Discovery step: identifies competitors for a given company or product.
#
# How it works, in plain English:
#   1. Search the web for "<company> <context> competitors".
#   2. Show the search results to the LLM and ask it to decide:
#        - "found":           here are up to 3 competitors
#        - "ambiguous":       the name could mean several companies, so ask the human
#        - "not_enough_info": the results aren't good enough, so suggest a better search
#   3. If there wasn't enough info, search ONE more time with the better query
#      and ask the LLM again. If it's still unclear, ask the human for more context.

from typing import Literal

from pydantic import BaseModel, Field

from agent.llm import get_llm
from agent.tools import search_you

# The most competitors we keep, to keep research (and costs) small.
MAX_COMPETITORS = 3


class DiscoveryDecision(BaseModel):
    """The shape of the answer we require from the LLM."""

    # Asked first on purpose: listing the possible companies before deciding
    # helps the LLM notice when a name is shared by several businesses.
    same_name_companies: list[str] = Field(
        description="Every distinct real company, in any industry, that goes by exactly this name, "
        "each with a few words on what it does. Empty if none is known."
    )
    status: Literal["found", "ambiguous", "not_enough_info"] = Field(
        description="found = competitors identified; ambiguous = the name could refer to "
        "more than one company; not_enough_info = the results don't clearly name competitors."
    )
    competitors: list[str] = Field(
        description=f"Up to {MAX_COMPETITORS} competitor company names. Only when status is found; otherwise empty."
    )
    question: str = Field(
        description="A short question asking the human which company they mean. "
        "Only when status is ambiguous; otherwise an empty string."
    )
    better_query: str = Field(
        description="An improved web search query to find this company's competitors. "
        "Only when status is not_enough_info; otherwise an empty string."
    )


# The instructions we give the LLM.
INSTRUCTIONS = f"""You identify the main competitors of a company using web search results.

Rules:
- Use ONLY the search results below for competitor names. Do not use outside knowledge.
- Never invent companies. Every competitor you name must appear in the search results.
- Do not list the company itself as a competitor.
- Step 1, same_name_companies: list every real company, in ANY industry, that you know
  uses exactly this name (not only the one in the search results). This is the one
  place you may use general knowledge, because search results often show only one of
  them. Companies with merely similar names don't count.
- Step 2, ambiguity: if the user gave no context and same_name_companies has 2 or more
  entries, choose "ambiguous" and ask a short question naming those options, even if
  the search results only show one of them. If the user DID give context, never choose
  "ambiguous": assume the context identifies the company.
- If the search results don't mention a company with this exact name, or don't clearly
  name its competitors, choose "not_enough_info" (never "ambiguous") and suggest a
  better search query that is DIFFERENT from the query already used. If the user gave
  context, the better query must include that context.
- If the user gave context, every competitor must match that context (same kind of
  product or business). Ignore results about other companies or products that merely
  share the name.
- Otherwise choose "found" and list up to {MAX_COMPETITORS} competitors, most relevant first."""


def _log(message):
    """Print one short progress line."""
    print(f"[discovery] {message}")


def _format_results(result):
    """Turn search results into plain text the LLM can read."""
    lines = []
    for i, item in enumerate(result["web"] + result["news"], start=1):
        lines.append(f"{i}. {item['title']}\n   {item['url']}\n   {item['snippet']}")
    return "\n".join(lines) or "(no results)"


def _ask_llm(company, context, query, result):
    """Show the search results to the LLM and get its structured decision."""
    llm = get_llm().with_structured_output(DiscoveryDecision)
    prompt = (
        f"{INSTRUCTIONS}\n\n"
        f"Company: {company}\n"
        f"Context from the user: {context or '(none)'}\n"
        f"Search query used: {query}\n\n"
        f"Search results:\n{_format_results(result)}"
    )
    return llm.invoke(prompt)


def discover(state):
    """Find competitors for state["company"]. Returns only the state fields that changed."""
    company = state["company"]
    context = state.get("company_context", "")
    errors = list(state.get("errors", []))
    search_count = state.get("search_count", 0)

    def stop(status, question="", competitors=None):
        """Package up the final state updates."""
        return {
            "discovery_status": status,
            "competitors": competitors or [],
            "human_question": question,
            "errors": errors,
            "search_count": search_count,
        }

    # Up to two rounds: the first search, plus one retry with a better query.
    query = " ".join(f"{company} {context} competitors".split())
    for round_number in (1, 2):
        # Search the web.
        _log(f"searching: {query}")
        result = search_you(query, count=5)
        search_count += 1

        if not result["ok"]:
            _log(f"search failed: {result['error']}")
            errors.append(f"discovery search failed: {result['error']}")
            return stop(
                "not_found",
                question=f"I couldn't search for {company}'s competitors because: {result['error']} "
                "Can you fix this and try again?",
            )

        # Ask the LLM what the results tell us.
        try:
            decision = _ask_llm(company, context, query, result)
        except Exception as e:
            _log(f"LLM call failed: {e.__class__.__name__}")
            errors.append(f"discovery LLM call failed: {e.__class__.__name__}: {e}")
            return stop(
                "not_found",
                question=f"I found search results for {company} but couldn't analyse them "
                f"({e.__class__.__name__}). Check OPENAI_API_KEY and try again.",
            )

        # Safety rule 1: if the company's name never appears in the search results,
        # the results aren't about it, so we can't be "found" or "ambiguous" yet.
        if company.lower() not in _format_results(result).lower():
            decision.status = "not_enough_info"

        # Safety rule 2: with no context from the human, a name shared by several
        # companies is always ambiguous, even if the LLM picked "found".
        elif not context.strip() and len(decision.same_name_companies) >= 2 and decision.status != "ambiguous":
            options = " or ".join(decision.same_name_companies)
            decision.status = "ambiguous"
            decision.question = decision.question or f"Which {company} do you mean: {options}?"

        # Safety rule 3: the human already told us which company they mean, so
        # don't ask them again. Treat it as "not enough info" and search once more.
        elif context.strip() and decision.status == "ambiguous":
            decision.status = "not_enough_info"

        # Act on the decision.
        competitors = decision.competitors[:MAX_COMPETITORS]
        if decision.status == "found" and competitors:
            _log(f"decision: found -> {', '.join(competitors)}")
            return stop("found", competitors=competitors)

        if decision.status == "ambiguous":
            _log(f"decision: ambiguous -> {decision.question}")
            return stop("ambiguous", question=decision.question)

        # Not enough info (or "found" with no names): try one better search.
        if round_number == 1:
            better = decision.better_query.strip()
            # If the LLM didn't suggest a genuinely different query, use our own.
            # Keep the human's context in the retry, so we don't drift to a
            # different company or product with the same name.
            if context.strip():
                fallback = f"{company} {context.strip()} alternatives"
            else:
                fallback = f'"{company}" company alternatives similar companies'
            if not better or better.lower() == query.lower():
                better = fallback
            elif context.strip() and context.strip().lower() not in better.lower():
                better = fallback
            query = better
            _log(f"decision: not_enough_info -> retrying with: {query}")

    _log("decision: not_found after retry")
    return stop(
        "not_found",
        question=f"I couldn't find clear competitors for \"{company}\". "
        "Can you add more context, such as what the company does, its industry or its website?",
    )

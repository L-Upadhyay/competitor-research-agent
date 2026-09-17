# Extraction step: turns raw search results into pricing, features, positioning and recent news.
#
# How it works, in plain English:
#   For each competitor, hand the LLM the search results the gatherer collected and
#   ask it to fill in a fixed form: pricing, core features, positioning, recent news
#   and the source links it used. The LLM may only use what's in those results.
#
# Safety nets:
#   - If a competitor has no search results at all, skip the LLM (saves money).
#   - If the LLM call fails, note the error and move on to the next competitor.
#   - Any news item or source whose link isn't in the search results is thrown out,
#     so nothing made-up gets through.

import re
from datetime import date

from pydantic import BaseModel, Field

from agent.llm import get_llm

# Limits on how much we keep per competitor.
MAX_FEATURES = 5
MAX_NEWS = 3

# What we write in every field when there's nothing to extract.
NO_DATA = "not available: search failed or skipped"
LLM_FAILED = "not available: extraction failed"


class NewsItem(BaseModel):
    """One recent news item about a competitor."""

    headline: str = Field(description="The news headline, taken from the search result.")
    date: str = Field(description='The date as stated in the result, or "not found".')
    url: str = Field(description="The URL of the search result this came from.")
    is_old: bool = Field(description="True if the date is more than 12 months before today.")


class CompetitorFindings(BaseModel):
    """The form the LLM fills in for each competitor."""

    pricing: str = Field(description='Pricing as stated in the results, or "not found". Never guess.')
    core_features: list[str] = Field(description=f"Up to {MAX_FEATURES} core product features.")
    positioning: str = Field(description="1-2 sentences on who the product is for and how it pitches itself.")
    recent_news: list[NewsItem] = Field(description=f"Up to {MAX_NEWS} news items clearly about this competitor.")
    sources: list[str] = Field(description="URLs of the search results actually used.")


# The instructions we give the LLM. Filled in per competitor below.
INSTRUCTIONS = """You extract facts about a competitor from web search results.

Competitor: {competitor}
It competes with: {company} ({context})
Today's date: {today}

Rules:
- Use ONLY the search results below. Do not use outside knowledge.
- If something isn't stated in the results, write "not found". Never guess prices.
- pricing: summarise every pricing detail stated in the results: plan names, prices
  (e.g. "$0 per user/month"), free tiers, and how pricing scales. Write "not found"
  only if no result says anything about pricing.
- core_features: up to {max_features} features actually described in the results.
- positioning: 1-2 sentences, based only on the results.
- recent_news: up to {max_news} items that are clearly about {competitor} the company.
  The result's title or snippet must mention {competitor} by name. Drop anything about
  other topics or similarly named things (for example "Brexit" is not about "Brex"),
  and drop sponsored or advertising content.
- For each news item, set date to that result's "published:" date (as YYYY-MM-DD).
  If the result says "published: not found", write "not found". Don't take dates
  from other results.
  Set is_old=true if that date is more than 12 months before today's date; if the date
  is "not found", set is_old=false.
- sources: the URL of EVERY result you used for pricing, features, positioning or news.
- Every news item and every source must be the exact URL of one of the results below.

Search results:
{results}"""


def _log(message):
    """Print one short progress line."""
    print(f"[extract] {message}")


def _format_results(entry):
    """Turn the gathered results into plain text, keeping only title, url, publish date and snippet."""
    lines = []
    for section in ("product", "news"):
        for item in entry.get(section, []):
            # The publish date comes from You.com; some results don't have one.
            date_line = f"published: {item['date']}" if item.get("date") else "published: not found"
            lines.append(f"- [{section}] {item['title']}\n  {item['url']}\n  {date_line}\n  {item['snippet']}")
    return "\n".join(lines)


def _placeholder(message, complete=False):
    """Findings for a competitor we couldn't extract anything for."""
    return {
        "pricing": message,
        "core_features": message,
        "positioning": message,
        "recent_news": message,
        "sources": message,
        "complete": complete,
    }


def extract(state):
    """Fill in findings for each competitor. Returns only the changed state fields."""
    company = state.get("company", "")
    context = state.get("company_context", "").strip() or "no extra context"
    raw_results = state.get("raw_results", {})
    findings = dict(state.get("findings", {}))
    errors = list(state.get("errors", []))
    today = date.today().isoformat()

    for competitor in state["competitors"]:
        entry = raw_results.get(competitor)

        # No results at all: skip the LLM entirely.
        if not entry or (not entry.get("product") and not entry.get("news")):
            _log(f"{competitor}: no data -> skipped")
            findings[competitor] = _placeholder(NO_DATA)
            continue

        prompt = INSTRUCTIONS.format(
            competitor=competitor,
            company=company,
            context=context,
            today=today,
            max_features=MAX_FEATURES,
            max_news=MAX_NEWS,
            results=_format_results(entry),
        )

        try:
            result = get_llm().with_structured_output(CompetitorFindings).invoke(prompt)
        except Exception as e:
            _log(f"{competitor}: extraction FAILED ({e.__class__.__name__}) -> skipping")
            errors.append(f"{competitor}: extraction failed: {e.__class__.__name__}: {e}")
            findings[competitor] = _placeholder(LLM_FAILED)
            continue

        # Look up each search result by its link, so we can check the LLM's answer.
        results_by_url = {item["url"]: item for section in ("product", "news") for item in entry.get(section, [])}

        # Safety check 1: news must come from a real result that names the competitor
        # as a whole word (so a "Brexit" article doesn't count as news about "Brex"),
        # and must not be a paid "Sponsored" advert.
        name_pattern = re.compile(rf"\b{re.escape(competitor)}\b", re.IGNORECASE)
        news, rejected_urls = [], set()
        for item in result.recent_news:
            source = results_by_url.get(item.url)
            if (
                source
                and name_pattern.search(f"{source['title']} {source['snippet']}")
                and "sponsored" not in source["title"].lower()
            ):
                news.append(item)
            else:
                rejected_urls.add(item.url)
        dropped = len(rejected_urls)
        news = news[:MAX_NEWS]
        # Show dates as plain YYYY-MM-DD (You.com sometimes adds a time, e.g. "2026-09-01T13:00:00").
        for item in news:
            if re.match(r"\d{4}-\d{2}-\d{2}T", item.date):
                item.date = item.date[:10]

        # Safety check 2: sources must be real result links, and not a news item we just rejected.
        # News links we kept are always listed as sources.
        sources = []
        for url in result.sources:
            if url in results_by_url and url not in rejected_urls:
                if url not in sources:
                    sources.append(url)
            else:
                dropped += 1
        sources += [n.url for n in news if n.url not in sources]

        findings[competitor] = {
            "pricing": result.pricing,
            "core_features": result.core_features[:MAX_FEATURES],
            "positioning": result.positioning,
            "recent_news": [n.model_dump() for n in news],
            "sources": sources,
            "complete": entry.get("complete", False),
        }

        # One summary line for this competitor.
        pricing_note = "pricing not found" if result.pricing.lower().startswith("not found") else "pricing found"
        old_count = sum(1 for n in news if n.is_old)
        line = (
            f"{competitor}: {pricing_note}, {len(findings[competitor]['core_features'])} features, "
            f"{len(news)} news ({old_count} old)"
        )
        if dropped:
            line += f", dropped {dropped} unverified item(s)"
        _log(line)

    return {"findings": findings, "errors": errors}

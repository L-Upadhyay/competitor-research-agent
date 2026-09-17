# Brief writer: turns the extracted findings into a readable Markdown competitor brief.
#
# How it works, in plain English:
#   - Almost all of the brief is assembled by plain code straight from the findings,
#     so facts, links and dates can't be reworded or invented.
#   - Only the short executive summary at the top is written by an LLM.
#     We try a Nebius-hosted open model first; if that fails for any reason,
#     we fall back to the shared OpenAI model.

import json
import os
from datetime import date

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

from agent.llm import MODEL_NAME as OPENAI_MODEL_NAME
from agent.llm import get_llm

# Load the secret keys (including NEBIUS_API_KEY) from the .env file.
load_dotenv()

# Nebius Token Factory speaks the same language (API) as OpenAI, at this address.
NEBIUS_BASE_URL = "https://api.tokenfactory.nebius.com/v1/"

# A small, inexpensive open instruct model hosted on Nebius (verified working on 2026-09-16).
NEBIUS_MODEL_NAME = "Qwen/Qwen3-30B-A3B-Instruct-2507"

SUMMARY_INSTRUCTIONS = """You write the executive summary of a competitor brief for {company}.

Write 3-5 sentences comparing the competitors below: how they position themselves,
how their pricing and features differ, and anything notable in their recent news.
Rules:
- Use ONLY the findings below. Do not add any facts, numbers or companies.
- If a competitor's data is missing or incomplete, say so briefly.
- Plain prose only: no headings, no bullet points, no links.

Findings (JSON):
{findings}"""


def _log(message):
    """Print one short progress line."""
    print(f"[brief] {message}")


# ---------- Parts of the brief built by plain code ----------


def _text_or_list(value, empty_text="not found"):
    """Show a field that is usually a list, but may be a message like "not available: ..."."""
    if isinstance(value, str):
        return f"_{value}_"
    if not value:
        return f"_{empty_text}_"
    return "\n".join(f"- {item}" for item in value)


def _news(value):
    """Show recent news items with their dates and links."""
    if isinstance(value, str):
        return f"_{value}_"
    if not value:
        return "_no recent news found_"
    lines = []
    for item in value:
        old_note = " (older than 12 months)" if item.get("is_old") else ""
        lines.append(f"- [{item['headline']}]({item['url']}) — {item.get('date', 'not found')}{old_note}")
    return "\n".join(lines)


def _competitor_section(name, info):
    """Build the Markdown section for one competitor."""
    parts = [f"## {name}"]
    if not info.get("complete", False):
        parts.append("⚠ incomplete data: some searches for this competitor failed or were skipped.")
    parts.append(f"**Pricing:** {info.get('pricing', 'not found')}")
    parts.append(f"**Core features:**\n{_text_or_list(info.get('core_features'))}")
    parts.append(f"**Positioning:** {info.get('positioning', 'not found')}")
    parts.append(f"**Recent news:**\n{_news(info.get('recent_news'))}")
    parts.append(f"**Sources:**\n{_text_or_list(info.get('sources'), empty_text='none')}")
    return "\n\n".join(parts)


def _data_gaps(state):
    """List everything that went wrong, so the reader knows what to trust less."""
    lines = []
    for name in state.get("competitors", []):
        info = state.get("findings", {}).get(name, {})
        if not info.get("complete", False):
            lines.append(f"- {name}: incomplete data")
    lines += [f"- {error}" for error in state.get("errors", [])]
    return "\n".join(lines) if lines else "none"


# ---------- The one part written by an LLM ----------


def _nebius_llm():
    """The Nebius-hosted model, reached through the OpenAI-compatible interface."""
    return ChatOpenAI(
        model=NEBIUS_MODEL_NAME,
        base_url=NEBIUS_BASE_URL,
        api_key=os.getenv("NEBIUS_API_KEY") or "missing",
        temperature=0,
        timeout=60,
        max_retries=1,
    )


def _executive_summary(company, findings):
    """Write the summary with Nebius, falling back to OpenAI. Returns (summary, model_used, error)."""
    prompt = SUMMARY_INSTRUCTIONS.format(company=company, findings=json.dumps(findings, indent=2))

    try:
        summary = _nebius_llm().invoke(prompt).content.strip()
        if not summary:
            raise ValueError("empty response")
        return summary, f"Nebius {NEBIUS_MODEL_NAME}", None
    except Exception as e:
        _log(f"Nebius failed ({e.__class__.__name__}) -> falling back to OpenAI")

    try:
        summary = get_llm().invoke(prompt).content.strip()
        return summary, f"OpenAI {OPENAI_MODEL_NAME}", None
    except Exception as e:
        _log(f"OpenAI also failed ({e.__class__.__name__}) -> brief without summary")
        return "_Executive summary unavailable: both LLMs failed._", "none", f"brief summary failed: {e.__class__.__name__}: {e}"


# ---------- Putting it all together ----------


def write_brief(state):
    """Assemble the full Markdown brief. Returns only the changed state fields."""
    company = state["company"]
    context = state.get("company_context", "").strip()
    findings = state.get("findings", {})
    errors = list(state.get("errors", []))

    summary, model_used, summary_error = _executive_summary(company, findings)
    if summary_error:
        errors.append(summary_error)
    _log(f"executive summary written by {model_used}")

    header = f"# Competitor brief: {company}"
    if context:
        header += f"\n\n_Context: {context}_"
    header += f"\n\n_Generated {date.today().isoformat()} · Competitors: {', '.join(state.get('competitors', []))}_"

    sections = [
        header,
        f"## Executive summary\n\n{summary}",
        *[_competitor_section(name, findings.get(name, {})) for name in state.get("competitors", [])],
        f"## Data gaps\n\n{_data_gaps({**state, 'errors': errors})}",
        f"---\n\n_Searches used: {state.get('search_count', 0)} · Summary model: {model_used}_",
    ]

    return {"brief": "\n\n".join(sections) + "\n", "brief_model": model_used, "errors": errors}

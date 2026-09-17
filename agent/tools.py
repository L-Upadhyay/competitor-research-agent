# External tool wrappers (e.g. You.com search API) used by the agent.

import os
import time

import requests
from dotenv import load_dotenv

# Load the secret keys from the .env file into the environment.
load_dotenv()

# Where the You.com search service lives.
SEARCH_URL = "https://api.you.com/v1/search"

# How long (in seconds) to wait for You.com to answer before giving up.
TIMEOUT_SECONDS = 20

# How long (in seconds) to pause before trying a failed request one more time.
RETRY_WAIT_SECONDS = 2

# How far back "recent" goes when recent_only=True.
# You.com accepts "day", "week", "month" or "year" for its freshness setting.
RECENT_WINDOW = "month"

# Longest snippet we keep per result. Shorter text = cheaper LLM calls later.
MAX_SNIPPET_CHARS = 500


def _trim(result):
    """Keep only the title, link and a short piece of text from one search result."""
    # Web results come with a list of "snippets"; news results only have a
    # "description". Use the first snippet if there is one, otherwise the description.
    snippets = result.get("snippets") or []
    text = snippets[0] if snippets else (result.get("description") or "")
    return {
        "title": result.get("title", ""),
        "url": result.get("url", ""),
        "snippet": text[:MAX_SNIPPET_CHARS],
    }


def search_you(query, count=5, recent_only=False):
    """Search the web with You.com.

    Always returns a dictionary and never crashes:
      - if it worked:  {"ok": True, "web": [...], "news": [...]}
      - if it failed:  {"ok": False, "error": "<what went wrong>"}
    """
    # Step 1: make sure we have an API key.
    api_key = os.getenv("YDC_API_KEY")
    if not api_key:
        return {"ok": False, "error": "YDC_API_KEY is missing. Add it to your .env file."}

    # Step 2: build the request.
    headers = {"X-API-Key": api_key}
    params = {"query": query, "count": count}
    if recent_only:
        params["freshness"] = RECENT_WINDOW

    # Demo failure switch: if FAIL_SEARCH_FOR is set (e.g. "Airwallex") and that
    # text is in the query, pretend You.com timed out. Used to show that the
    # agent copes with a broken search instead of crashing.
    fail_for = os.getenv("FAIL_SEARCH_FOR", "").strip()
    simulate_timeout = bool(fail_for) and fail_for.lower() in query.lower()

    # Step 3: send the request, allowing one retry for temporary problems.
    for attempt in (1, 2):
        is_last_attempt = attempt == 2

        try:
            if simulate_timeout:
                raise requests.Timeout("simulated timeout")
            response = requests.get(
                SEARCH_URL, headers=headers, params=params, timeout=TIMEOUT_SECONDS
            )
        except requests.Timeout:
            # You.com took too long. Try once more, then give up.
            if not is_last_attempt:
                print("[search] timeout, retrying once...")
                time.sleep(RETRY_WAIT_SECONDS)
                continue
            if simulate_timeout:
                return {"ok": False, "error": "simulated timeout (FAIL_SEARCH_FOR)"}
            return {"ok": False, "error": f"You.com did not respond within {TIMEOUT_SECONDS} seconds (tried twice)."}
        except requests.RequestException as e:
            # No internet, bad address, etc. Retrying won't help.
            return {"ok": False, "error": f"Could not reach You.com: {e.__class__.__name__}."}

        status = response.status_code

        # Wrong or missing permission: retrying won't fix a bad key.
        if status in (401, 403):
            return {"ok": False, "error": f"You.com rejected the API key (HTTP {status}). Check YDC_API_KEY in your .env file."}

        # Too many requests (429) or a problem on You.com's side (5xx):
        # these are often temporary, so wait a moment and try once more.
        if status == 429 or status >= 500:
            if not is_last_attempt:
                print(f"[search] HTTP {status}, retrying once...")
                time.sleep(RETRY_WAIT_SECONDS)
                continue
            reason = "rate limit reached" if status == 429 else "server error"
            return {"ok": False, "error": f"You.com returned HTTP {status} ({reason}) twice in a row."}

        # Any other unsuccessful answer (e.g. a badly formed request).
        if status != 200:
            return {"ok": False, "error": f"You.com returned HTTP {status}: {response.text[:200]}"}

        # Step 4: read the answer.
        try:
            results = response.json().get("results", {})
        except (ValueError, AttributeError):
            return {"ok": False, "error": "You.com sent back a response we could not read."}

        return {
            "ok": True,
            "web": [_trim(r) for r in results.get("web", [])],
            "news": [_trim(r) for r in results.get("news", [])],
        }

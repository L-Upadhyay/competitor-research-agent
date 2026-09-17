<!-- Log of prompts used while building and tuning the agent. -->

# Prompts Log

Times are local (EDT). Earlier entries marked "~" were added after the fact and use the matching commit time, because the exact send time wasn't recorded.

---

## Project setup

**Time:** ~2026-09-16 18:23

```
Set up this project folder. Run `uv init --python 3.12` (if it creates main.py, README.md or a git repo, keep them, don't duplicate), then `uv add langgraph langchain-openai requests python-dotenv`.

Create this structure with placeholder files, each with a one-line comment saying its purpose:
- main.py
- agent/__init__.py
- agent/state.py
- agent/tools.py
- agent/discovery.py
- agent/researcher.py
- agent/graph.py
- scripts/test_you.py
- outputs/ (with a .gitkeep)
- notes/prompts_log.md
- README.md (title only: Competitor Research Agent)

Create .gitignore covering .env, .venv/, __pycache__/.
Create .env.example with these three lines:
YDC_API_KEY=
OPENAI_API_KEY=
NEBIUS_API_KEY=

Do NOT write any agent logic yet.

Then make sure git is initialized, make a first commit, and run:
gh repo create L-Upadhyay/competitor-research-agent --public --source . --push

Finally, confirm .env is not tracked by git and show me the folder tree.
```

**Result:** Worked. uv's own main.py, README.md, .gitignore and git repo were kept, not duplicated. The repo was created on GitHub and pushed; .env is ignored. Note: the default branch is `master`.

---

## Project setup: status check

**Time:** 2026-09-16, between 18:23 and 20:38 (not recorded)

```
You didn't respond to my last message. Check what already exists in this folder, finish only the remaining setup steps from that message, then show me the folder tree and the GitHub link.
```

**Result:** Worked. Every setup step was already done, so nothing changed; I re-checked each step and showed the tree and link again.

---

## Project setup: branch name

**Time:** 2026-09-16, between 18:23 and 20:38 (not recorded)

```
no
```

**Result:** Worked. Declined renaming `master` to `main`; the branch stays `master`.

---

## You.com search smoke test

**Time:** ~2026-09-16 20:39

```
Two things:
1. Create agent/extractor.py with a one-line comment: "Extraction step: turns raw search results into pricing, features, positioning and recent news."
2. Write scripts/test_you.py: load YDC_API_KEY from .env with python-dotenv (exit with a clear message if missing), call GET https://api.you.com/v1/search with header X-API-Key, query "Ramp corporate card competitors", count 3, timeout 20 seconds. Print the status code, then the title and URL of each web result, and also say how many news results came back. Never print the API key.
Run it with `uv run python scripts/test_you.py` and show me the output. If the response shape differs from what you expected, print the top-level JSON keys so we can see the real structure. Commit when it works.
```

**Result:** Worked on the first run: HTTP 200, 3 web results, 0 news results. The response shape was as expected (`results.web` / `results.news`).

---

## You.com search smoke test: push

**Time:** ~2026-09-16 20:40

```
yes
```

**Result:** Worked. Pushed the commit to GitHub.

---

## Agent state and You.com search tool

**Time:** ~2026-09-16 20:43

```
Next component: agent/state.py and agent/tools.py. Keep both simple and well commented so a non-coder can follow them.

1. agent/state.py: a TypedDict called AgentState with these fields:
   company (str), competitors (list[str]), raw_results (dict: competitor name -> search results),
   findings (dict: competitor name -> extracted info), errors (list[str]),
   search_count (int), brief (str).

2. agent/tools.py: a function search_you(query, count=5, recent_only=False) that calls the You.com search API.
   - Reads YDC_API_KEY from .env.
   - If recent_only is True, restrict results to recent content using You.com's freshness parameter (check the You.com API docs for the exact parameter name and value; don't guess).
   - Timeout 20 seconds.
   - On a timeout, a 429, or a 5xx error: wait 2 seconds and retry once.
   - On a 401/403: don't retry; return an error saying to check YDC_API_KEY.
   - Never raise an exception to the caller. Always return a dict:
     success: {"ok": True, "web": [...], "news": [...]}
     failure: {"ok": False, "error": "<plain-English reason>"}
   - Trim each result to title, url and snippet (first snippet, max 500 characters) to keep LLM costs low.

3. Update scripts/test_you.py to test three cases and print the result of each:
   a) normal: search_you("Brex corporate card pricing")
   b) news: search_you("Brex news", recent_only=True), and report how many news and web results came back
   c) failure: temporarily use a fake API key and show that it returns ok=False with a clear message instead of crashing

Run it, show me the output, then commit and push.
```

**Result:** Worked. All 3 cases passed: (a) 5 web results; (b) 5 web + 5 news results, using `freshness="month"` from the docs; (c) ok=False with "You.com rejected the API key (HTTP 401)". Issues found: news for "Brex news" was mostly off-topic (e.g. Brexit), freshness still let a 2022 web article through, and the retry path wasn't exercised. News results have no snippets, so the tool falls back to the description.

---

## Prompts log process

**Time:** 2026-09-16 20:45

```
From now on, after finishing each task, append the exact prompt I sent you to notes/prompts_log.md, with the time, a heading naming the component, and one line on the result (worked / what failed and what we changed). Start by adding the prompts I've already sent in this session, in order. Include this log update in each commit.
```

**Result:** Worked. Added this log with all earlier prompts from the session in order; from now on each task's prompt is logged and included in its commit.

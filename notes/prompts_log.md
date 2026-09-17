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

---

## Discovery agent (Agent 1)

**Time:** 2026-09-16 20:52

```
Next component: agent/discovery.py (Agent 1). Keep it simple and well commented for a non-coder.

1. Add these fields to AgentState in agent/state.py:
   company_context (str): an optional clarification from the human, e.g. "the fintech bank"
   discovery_status (str): "found" | "ambiguous" | "not_found"
   human_question (str): the question for the human when the agent needs help

2. Model setup: use ChatOpenAI from langchain-openai with an inexpensive current OpenAI mini model. Verify the model name actually works with one quick call before using it. Put the model name in one constant at the top of a new file agent/llm.py so all agents share it. Read OPENAI_API_KEY from .env. temperature=0.

3. agent/discovery.py: a function discover(state) -> dict with state updates.
   - Search with search_you: "{company} {company_context} competitors" (count 5).
   - If the search returns ok=False, record the error in state["errors"] and set discovery_status="not_found" with a human_question explaining what failed.
   - Otherwise send the results to the LLM with structured output (a Pydantic model) returning:
     status: "found" | "ambiguous" | "not_enough_info"
     competitors: list of up to 3 company names (only when found)
     question: a short question for the human (only when ambiguous)
     better_query: an improved search query (only when not_enough_info)
   - The prompt must tell the LLM: use only the search results, don't invent companies, and pick "ambiguous" if the name could refer to more than one company.
   - If not_enough_info: run ONE more search with better_query and ask the LLM again. If it's still not found, set discovery_status="not_found" with a human_question asking for more context.
   - Increment search_count for every search.
   - Print one short log line per step, e.g. "[discovery] searching: ...", "[discovery] decision: found -> Brex, Mercury, Navan".

4. Create scripts/test_discovery.py and run 3 cases, printing the returned state updates:
   a) company="Ramp", company_context="corporate card and spend management"
   b) company="Mercury", company_context=""  (expect ambiguous)
   c) company="Zxqvtrbl Labs", company_context=""  (expect not_found after a retry)

Run it, show me the output, then log, commit and push.
```

**Result:** Worked after several fixes; all 3 cases now match expectations. Model: gpt-5.4-mini (verified with temperature=0 and structured output). What failed and what we changed: (1) Mercury came back "found" because the results only showed the bank, so the LLM now first lists `same_name_companies`, and code forces "ambiguous" when there's no context and 2+ are listed (then 5/5 runs ambiguous; Brex/Airwallex still "found"). (2) Zxqvtrbl Labs got a "better" query identical to the first and was once marked ambiguous ("Labs", "World Labs"), so a repeated query now falls back to a different one, and code forces "not_enough_info" when the company name isn't in the results. (3) Ramp was once "ambiguous" despite its context, so ambiguity is ignored when context is given (one more search instead). Added pydantic as a direct dependency.

---

## Researcher / gatherer agent (Agent 2)

**Time:** 2026-09-16 21:01

```
Next component: agent/researcher.py (Agent 2, the gatherer). Keep it simple and commented for a non-coder. Don't change discovery.py.

1. Demo failure switch in agent/tools.py:
   - If the environment variable FAIL_SEARCH_FOR is set and its value appears in the query (case-insensitive), simulate a timeout INSIDE the request attempt, so the real retry-once logic runs, and then return ok=False with the error "simulated timeout (FAIL_SEARCH_FOR)".
   - Print a log line when the retry happens, e.g. "[search] timeout, retrying once...".

2. agent/researcher.py: a function gather(state) -> dict of state updates.
   - MAX_SEARCHES = 12 constant at the top (whole run, including discovery searches already in search_count).
   - For each competitor in state["competitors"]:
     a) product search: "{competitor} pricing features" (count 5)
     b) news search: "{competitor} {company_context} news" (count 5, recent_only=True); if company_context is empty, use "{competitor} company news"
     - If a search succeeds but returns 0 web AND 0 news results, retry once with a reworded query ("{competitor} official site" for product, "{competitor} announcement" for news).
     - If a search fails (ok=False), append a clear message to errors, and continue with the next search / next competitor. Never crash.
     - Before every search, check search_count against MAX_SEARCHES. If the limit is reached, stop gathering, append "search limit reached" to errors, and return what was gathered so far.
   - Store raw_results[competitor] = {"product": [...], "news": [...], "complete": True/False}, where complete=False if any search for that competitor failed or was skipped.
   - Log lines like "[gather] Brex: product search (5 results)", "[gather] Airwallex: news search FAILED -> skipping", "[gather] search limit reached".

3. scripts/test_researcher.py with company="Ramp", company_context="corporate card and spend management", competitors=["Brex","Airwallex","Expensify"]. Run 3 cases, printing only the log lines, then per competitor: number of product results, number of news results, complete flag, plus the errors list and search_count:
   a) normal run, search_count starting at 1
   b) FAIL_SEARCH_FOR="Airwallex" (set in the script via os.environ): expect the retry log, the Airwallex error recorded, Brex and Expensify still complete
   c) search_count starting at 9: expect the limit to stop it partway

Limit yourself to 2 fix rounds. If something is still off after that, stop and report it rather than continuing to iterate. Then log, commit and push.
```

**Result:** Worked on the first run; 0 of 2 fix rounds used. (a) all 3 complete, search_count 1 -> 7; (b) retry log shown twice, 2 Airwallex errors recorded, Brex and Expensify complete; (c) stopped after 3 searches (9 -> 12): Brex complete, Airwallex product only (complete=False), Expensify not reached (complete=False), "search limit reached" in errors. Fixed before the first run: product results were saved only after the news search, so a limit hit in between would have lost them. Not verified: the empty-result reworded retry (You.com returned results even for "Zxqvtrbl Labs"). discovery.py unchanged.

---

## Extractor agent (Agent 3)

**Time:** 2026-09-16 21:08

```
Next component: agent/extractor.py (Agent 3). Keep it simple and commented for a non-coder. Don't change discovery.py or researcher.py.

1. agent/extractor.py: a function extract(state) -> dict of state updates.
   - For each competitor in state["competitors"]:
     - If raw_results has no entry, or both product and news lists are empty: don't call the LLM. Set findings[competitor] to all fields "not available: search failed or skipped", complete=False. Log "[extract] Airwallex: no data -> skipped".
     - Otherwise call the shared LLM (agent/llm.py) with structured output (Pydantic model CompetitorFindings):
       pricing: str
       core_features: list[str] (max 5)
       positioning: str (1-2 sentences)
       recent_news: list of {headline, date, url, is_old: bool} (max 3)
       sources: list[str] (URLs actually used)
     - Prompt rules: use ONLY the provided results; if something isn't stated, write "not found" (never guess prices); only include news that is clearly about this competitor (drop anything about other topics, e.g. "Brexit" for "Brex"); mark is_old=True if the item is more than 12 months before today's date (pass today's date in the prompt); every item must come from a result's URL.
     - Pass only title, url and snippet to the LLM.
     - If the LLM call raises an error: append a clear message to errors, set that competitor's findings to "not available: extraction failed", complete=False, and continue.
     - Set complete from raw_results[competitor]["complete"].
   - Log one line per competitor, e.g. "[extract] Brex: pricing found, 5 features, 2 news (1 old)".

2. scripts/test_extractor.py with company="Ramp", company_context="corporate card and spend management", competitors=["Brex","Airwallex","Expensify"]:
   - Run gather() once with FAIL_SEARCH_FOR="Airwallex", then extract() on the result.
   - Print the log lines and the findings as readable JSON, plus errors.
   - Expect: Brex and Expensify filled in with source URLs, Airwallex skipped without an LLM call, no off-topic news.

Limit yourself to 2 fix rounds. If something is still off after that, stop and report it. Then log, commit and push.
```

**Result:** Expectations met after 2 fix rounds (limit reached; stopped there). Brex and Expensify filled in with source URLs, Airwallex skipped without an LLM call, no off-topic news. Round 1: Brex pricing was "not found" although a snippet said "Essentials $0 per user/month", so the pricing rule was spelled out; a Motley Fool item not mentioning Brex was listed as news, so code now requires the competitor's name as a whole word in the result; sources missed product pages, so the prompt now asks for every result used. Round 2: a rejected news URL stayed in sources, the "dropped" count included items cut by the 3-item limit, and a "Sponsored" Forbes ad was listed as news; all three fixed. Still off: most news dates are "not found" (search_you drops You.com's page_age); "news" still includes Brex's own blog and a rewards guide while a Capital One/Brex item was missed; one Expensify item got a date apparently borrowed from a duplicate story; the same Rillet story appears twice; Expensify's "dropped 2" wasn't investigated.

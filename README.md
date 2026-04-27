# PawPal+

A Streamlit app that helps a pet owner plan daily pet care tasks. Built in two stages: first as a rule-based priority scheduler (Modules 1–3), then extended with a Retrieval-Augmented Generation layer that lets a language model refine the plan using the owner's real calendar and pet health records.

---

## Original project — PawPal+ Scheduler (Modules 1–3)

**PawPal+ Scheduler** was built to solve a straightforward problem: a busy pet owner needs to fit multiple care tasks — walks, feeding, medication, grooming — into a limited time window each day, without forgetting anything or letting high-priority tasks get pushed aside. The original system let an owner define their available hours and a list of tasks with priorities and durations, then automatically generated a time-blocked daily plan. It supported recurring tasks (daily and weekly), detected scheduling conflicts, and let the owner mark tasks complete — with recurring ones rolling forward to the next due date automatically.

---

## Title and summary

**PawPal+ with RAG** extends the original scheduler by making it context-aware. The rule-based engine is good at fitting tasks into time, but it has no knowledge of the outside world — it doesn't know the owner has a noon lunch where they can't walk the dog, or that a pet is recovering from surgery and should avoid strenuous play. The RAG layer lets the owner upload their own calendar events and pet health records, indexes them locally with ChromaDB, and retrieves the most relevant snippets when generating a plan. Those snippets are sent to Google Gemini alongside the rule-based schedule, and the model returns concrete suggested adjustments with reasoning grounded in the uploaded data.

This matters because context is what separates a useful plan from a merely correct one. The system keeps the deterministic scheduler as the source of truth and positions the LLM as an advisor — the owner reads the AI's reasoning and decides whether to act on it, which keeps a human in the loop for any change that affects real pet care.

---

## Architecture overview

The system has four layers:

```
┌─────────────────────────────────────────────┐
│               Streamlit UI (app.py)         │
│  Owner/Pets form · Tasks · Knowledge Base   │
│  Generate schedule · Generate AI plan       │
└────────────┬──────────────┬─────────────────┘
             │              │
             ▼              ▼
┌────────────────┐   ┌──────────────────────────────┐
│  Domain layer  │   │        RAG layer (rag.py)     │
│ pawpal_system  │   │  RagIndex → ChromaDB          │
│                │   │  MiniLM embeddings (local)    │
│ Pet  Owner     │   │  one collection, source_type  │
│ Task DailyPlan │   │  metadata: calendar | health  │
│                │   └──────────────┬───────────────┘
│ generate()     │                  │ top-k docs
│ rule-based     │◄─────────────────┤
│                │                  ▼
│ generate_      │   ┌──────────────────────────────┐
│  with_ai()     │──►│      LLM layer (llm.py)      │
└────────────────┘   │  GeminiClient                │
                     │  builds prompt, calls Gemini  │
                     │  returns ai_summary (text)    │
                     └──────────────────────────────┘
```

**Data flow for "Generate AI plan":**
1. `DailyPlan.generate()` runs first — produces the deterministic baseline
2. A query is built per task (e.g., `"Mochi Administer medication 2026-04-26"`) and sent to `RagIndex.query()`, which performs a semantic search against the ChromaDB collection
3. The top-k calendar and health documents are de-duplicated and forwarded to `GeminiClient.refine_plan()`
4. Gemini receives the rule-based summary, retrieved snippets, owner info, and task list, and returns suggested adjustments with reasoning
5. The AI output is stored as `plan.ai_summary` — it never modifies `task.start_time`

The UI renders both outputs side by side: the unchanged rule-based plan, then the AI refinement section with a "Retrieved context" expander showing exactly which snippets the model used.

---

## Setup

**Prerequisites:** Python 3.10+, a Gemini API key (get one free at [aistudio.google.com](https://aistudio.google.com))

```bash
# 1. Clone the repository
git clone <repo-url>
cd applied-ai-system-project

# 2. Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt
```

> On the first run, ChromaDB downloads its MiniLM ONNX embedding model (~80 MB). This requires an internet connection once — after that the model is cached locally and the app runs fully offline except for Gemini API calls.

```bash
# 4. Configure your API key
cp .env.example .env
# Open .env and fill in:
#   GEMINI_API_KEY=your_key_here

# 5. Launch the app
streamlit run app.py
```

```bash
# Run tests (no API key or network needed)
pytest -v
```

---

## Sample interactions

### Interaction 1 — Rule-based schedule only

**Input:**
- Owner: Jordan, available 8:00 AM – 6:00 PM
- Pets: Buddy (dog), Mochi (cat)
- Tasks:
  - Morning walk — Buddy — 30 min — high — daily
  - Feed breakfast — Buddy — 10 min — high — daily
  - Administer medication — Mochi — 5 min — high — daily
  - Clean litter box — Mochi — 10 min — medium — daily
  - Enrichment play — Buddy — 20 min — low — weekly

**Action:** Click **Generate schedule**

**Output:**
```
Scheduled tasks:
  ○ 08:00 AM – 08:30 AM  — Morning walk (Buddy)
  ○ 08:30 AM – 08:40 AM  — Feed breakfast (Buddy)
  ○ 08:40 AM – 08:45 AM  — Administer medication (Mochi)
  ○ 08:45 AM – 08:55 AM  — Clean litter box (Mochi)
  ○ 08:55 AM – 09:15 AM  — Enrichment play (Buddy)

Total time scheduled: 75 min of 600 min available.
```

Tasks are placed in priority order (high → medium → low), with shorter tasks breaking ties. All five fit, so nothing is left unscheduled.

---

### Interaction 2 — AI-augmented plan with calendar context

**Input:** Same owner, pets, and tasks as above.

**Knowledge base uploaded:**
- `data/sample_calendar.md` — includes a 2:00–3:00 PM vet appointment for Mochi and a noon lunch where the owner is out of the apartment
- `data/sample_health.json` — includes a note that Mochi is on a 7-day antibiotic course (twice daily with food) and that Buddy has mild arthritis and should keep walks gentle

**Action:** Click **Generate AI plan**

**Retrieved context (shown in expander):**
- *Calendar:* "Vet appointment for Mochi — 2026-04-26 14:00–15:00: Annual checkup at Bayside Animal Clinic. Mochi should not eat for 2 hours before the visit."
- *Calendar:* "Lunch with Sam — 2026-04-26 12:00–13:00: Out of the apartment, cannot walk dogs during this window."
- *Health:* "Mochi 2026-04-20 medication: Started a 7-day antibiotic course (amoxicillin), 1 pill twice daily with food. Last dose 2026-04-27."
- *Health:* "Buddy 2026-04-10 condition: Senior dog with mild arthritis in hind legs. Keep walks gentle and limit stairs."

**AI refinement output:**

```
## Suggested adjustments

- Keep the morning walk at 8:00 AM as scheduled — this is the right window
  given the noon lunch absence and the afternoon vet appointment.
- For Buddy's morning walk, keep the pace gentle and avoid stairs; his
  arthritis note says strenuous activity should be limited.
- Schedule a second medication dose for Mochi around 6:00 PM (with her
  evening meal) to complete the twice-daily antibiotic course.
- Do not feed Mochi within 2 hours of the 2:00 PM vet appointment —
  her last meal should be no later than noon.
- Enrichment play for Buddy is fine in the morning slot; avoid scheduling
  any active play after the vet visit in case Mochi needs rest.

## Reasoning

The calendar shows two constraints that the rule-based scheduler couldn't
see: the owner is out at noon and Mochi has a vet appointment at 2 PM with
a fasting requirement. The health records add two more: Buddy's arthritis
means the morning walk should be low-impact, and Mochi's antibiotic
requires a second dose later in the day with food. The baseline plan places
all tasks in the morning, which is correct given those afternoon constraints,
but it misses the second medication dose entirely and doesn't account for
the pre-vet fasting window.
```

---

### Interaction 3 — Missing API key guard

**Input:** Same setup, but `GEMINI_API_KEY` is not set in `.env`.

**Action:** Click **Generate AI plan**

**Output:**
```
GEMINI_API_KEY missing in .env — AI plan disabled.
```

The rule-based schedule is unaffected and still usable. No crash, no partial state.

---

## Design decisions

**One ChromaDB collection, not two.** An early option was to use separate collections for calendar and health records. A single collection with a `source_type` metadata field was simpler — one client handle, one `reset()` call, and `query()` accepts an optional `source_type` filter when you need to search only one category. For a project of this scale the added flexibility of separate collections wasn't worth the extra surface area.

**AI output is advisory, not authoritative.** Gemini's response is stored as free text on `plan.ai_summary` and displayed as a suggestion — it never writes back to `task.start_time`. This was a deliberate responsible-AI choice: the LLM can hallucinate times or misread context, and any error in pet care (missed medication, walking a dog before a vet's fasting window) has real consequences. Keeping the human in the loop before any AI suggestion is acted on was more important than making the app feel more automated.

**Rule-based scheduler runs first, every time.** `generate_with_ai()` always calls `self.generate()` as its first step. This means the deterministic plan is always available regardless of whether the LLM call succeeds, and the AI refines a concrete baseline rather than reasoning from scratch. It also made testing easier: the rule-based times before and after the AI call could be compared directly.

**No structured JSON output from Gemini.** Asking Gemini to return a JSON diff of proposed task changes would enable an "Apply suggestions" button, but it would also make the model's reasoning harder to read and inspect. Free-text output is more transparent — the owner can read the reasoning and decide whether it's sound before acting on it. The trade-off is that applying a suggestion requires the owner to manually adjust tasks.

---

## Testing summary

**What worked well:** The three RAG tests cover the most important failure modes without hitting the network. `test_index_markdown_retrieves` confirms that ChromaDB's default embeddings produce semantically meaningful results — querying "vet visit for the cat" against a collection containing a "Vet appointment for Mochi" block returns the right document. `test_gemini_client_missing_api_key` catches the most common setup mistake cleanly. `test_generate_with_ai_uses_mocked_llm` gives end-to-end confidence that the two-pass flow (rule-based then LLM) works and that the AI does not mutate task times.

**What didn't work initially:** The monkeypatching in `test_generate_with_ai_uses_mocked_llm` required patching `llm.genai.GenerativeModel` (the reference inside the `llm` module) rather than `google.generativeai.GenerativeModel` (the global namespace). Patching the wrong target left the real import in place and the test would have made a live API call. This is a subtle Python import behaviour that wasn't obvious until the test was inspected carefully.

**What I learned:** Running tests immediately after writing code caught the deprecated-SDK warning (`google-generativeai` is end-of-life, replaced by `google-genai`) before it became a deeper issue. Tests don't just verify logic — they surface environment and dependency problems that a code review alone would miss. The 5-test suite (2 original + 3 new) passes in about 20 seconds on a first run while ChromaDB's embedding model initialises, and in under 5 seconds on subsequent runs once the model is cached.

---

## Reflection

**What this project taught me about AI**

The most useful thing I learned is the difference between AI as an autocomplete tool and AI as a design collaborator. When I used Claude to just generate code, the results were faster but shallow — I got working implementations of things I already knew how to build. When I used it to push back on architectural choices ("should the LLM replace the scheduler or augment it?", "one collection or two?"), the conversation surfaced trade-offs I hadn't thought through and the final design was better for it.

Responsible use meant maintaining understanding at every step. I set a rule for myself: if I couldn't explain why a piece of generated code was correct, I wouldn't commit it. That standard caught the deprecated SDK issue, forced me to actually understand the ChromaDB query API, and meant that when a test failed I could reason about it rather than just re-prompting. AI tools lower the cost of building things, but they don't lower the cost of understanding what you've built — that understanding is still entirely on you.

**What this project taught me about problem-solving**

RAG forced me to think in two separate layers that need to be designed independently but work together: retrieval quality and generation quality. A well-written prompt does nothing if the retrieved documents are irrelevant, and good retrieval does nothing if the prompt doesn't give the model a clear task. Debugging the system required thinking about both at once — when the AI gave a weak response, the first question was always "did the right documents get retrieved?" rather than "is the prompt wrong?".

The advisory-only design decision also taught me something about building AI features into real systems: the question "what happens when the AI is wrong?" should be answered in the architecture, not in a disclaimer. Designing the system so that an AI error cannot corrupt the user's plan was more trustworthy than adding a warning label after the fact.

---

## Project structure

```
applied-ai-system-project/
├── app.py                  # Streamlit UI
├── pawpal_system.py        # Core domain: Pet, Owner, Task, DailyPlan
├── rag.py                  # RagIndex — ChromaDB-backed knowledge retrieval
├── llm.py                  # GeminiClient — prompt builder + Gemini API call
├── main.py                 # CLI demo script
├── data/
│   ├── sample_calendar.md  # Example calendar events (markdown)
│   └── sample_health.json  # Example pet health records (JSON)
├── tests/
│   ├── test_pawpal.py      # Original scheduler tests
│   └── test_rag.py         # RAG indexing, API key, and AI generation tests
├── requirements.txt
├── .env.example
└── .gitignore
```

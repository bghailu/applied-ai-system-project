# PawPal+

A Streamlit app that helps a pet owner plan daily care tasks — originally built as a rule-based scheduling system, then extended with a Retrieval-Augmented Generation (RAG) layer so an LLM can refine the plan using real calendar and pet health data.

---

## Original project (Module 2)

The core of PawPal+ is a deterministic daily scheduler built around four Python classes in [`pawpal_system.py`](pawpal_system.py):

| Class | Purpose |
|---|---|
| `Pet` | Stores a pet's name and species |
| `Owner` | Stores the owner's name and available time window |
| `Task` | A care task with duration, priority, frequency, and scheduling state |
| `DailyPlan` | Coordinates scheduling across all tasks for a given day |

`DailyPlan.generate()` sorts tasks by priority (1 = high) then duration, and packs them sequentially into the owner's available time window. Tasks that don't fit are left unscheduled. The scheduler also supports:

- **Conflict detection** — `detect_conflicts()` flags overlapping time windows
- **Recurring tasks** — marking a `daily` or `weekly` task complete automatically creates the next occurrence
- **Filtering and sorting** — `filter_tasks()` and `sort_by_time()` for viewing subsets of the plan

The Streamlit UI in [`app.py`](app.py) lets the owner enter their info, add pets, build a task list, generate the schedule, and mark tasks done.

---

## RAG extension (Module 3)

The original scheduler has no awareness of context — it doesn't know the owner has a 2pm meeting, or that one of the pets is recovering from surgery. The RAG extension adds that awareness by letting the owner upload their own calendar and pet health records, indexing them locally, and using a language model to refine the baseline plan with concrete, grounded reasoning.

### How it works

```
User uploads files
        │
        ▼
  RagIndex (rag.py)
  ChromaDB — local vector store
  MiniLM embeddings (bundled, offline after first download)
        │
        │  on "Generate AI plan"
        ▼
  DailyPlan.generate_with_ai()
    1. run rule-based generate() → baseline plan
    2. query ChromaDB with task names + date → top-k calendar & health docs
    3. send baseline plan + retrieved docs to Gemini
        │
        ▼
  GeminiClient (llm.py)
  Google Gemini API
        │
        ▼
  AI refinement displayed alongside the rule-based plan
```

**Key design decision:** the AI output is advisory — it never overwrites `task.start_time`. The rule-based plan is always the source of truth. Gemini's response appears in a separate "AI refinement" section with a "Retrieved context" expander showing exactly what snippets the model saw.

### New files

| File | Role |
|---|---|
| [`rag.py`](rag.py) | `RagIndex` — indexes and queries markdown/JSON knowledge docs via ChromaDB |
| [`llm.py`](llm.py) | `GeminiClient` — builds the prompt and calls the Gemini API |
| [`data/sample_calendar.md`](data/sample_calendar.md) | Example calendar events in markdown format |
| [`data/sample_health.json`](data/sample_health.json) | Example pet health records in JSON format |
| [`tests/test_rag.py`](tests/test_rag.py) | Tests for RAG indexing, API key validation, and the AI generation flow |

---

## Setup

```bash
# 1. Clone and enter the project
git clone <repo-url>
cd applied-ai-system-project

# 2. Create a virtual environment
python -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt
# Note: ChromaDB downloads its MiniLM embedding model (~80 MB) on first use.
# After that it runs fully offline.

# 4. Add your Gemini API key
cp .env.example .env
# Open .env and set:  GEMINI_API_KEY=your_key_here
```

Get a Gemini API key at [aistudio.google.com](https://aistudio.google.com).

---

## Running the app

```bash
streamlit run app.py
```

---

## Example workflow

### 1. Set up owner and pets

Fill in your name and available time window (e.g., 8:00 AM – 6:00 PM), then add one or more pets. Click **Save Owner** and **Add Pet** to confirm.

### 2. Add tasks

For each care task, set a title, pick which pet it's for, enter a duration in minutes, choose a priority (high / medium / low), and select a frequency (one-time, daily, or weekly). Click **Add task**.

Example tasks:
- Morning walk — Buddy — 30 min — high — daily
- Feed breakfast — Buddy — 10 min — high — daily
- Administer medication — Mochi — 5 min — high — daily
- Clean litter box — Mochi — 10 min — medium — daily
- Enrichment play — Buddy — 20 min — low — weekly

### 3. Load the knowledge base

Upload your calendar and health files in the **Knowledge Base** section. You can use the sample files in `data/` to try it out:

- `data/sample_calendar.md` — markdown file with one event per `---`-separated block
- `data/sample_health.json` — JSON array of health records

Click **Build / refresh index**. The caption will show how many documents were indexed.

**Calendar JSON shape:**
```json
[{"title": "Vet appointment", "date": "2026-04-26", "start": "14:00", "end": "15:00", "notes": "..."}]
```

**Health JSON shape:**
```json
[{"pet": "Mochi", "date": "2026-04-20", "type": "medication", "notes": "..."}]
```

### 4. Generate a plan

**Option A — Rule-based only:** click **Generate schedule** to produce the deterministic priority-sorted plan with no LLM involved.

**Option B — AI-augmented:** click **Generate AI plan**. This runs the rule-based scheduler first, retrieves the most relevant calendar and health snippets for each task and the day's time window, and sends everything to Gemini. The result shows:

- The rule-based schedule (same as Option A — unchanged)
- **AI refinement** — Gemini's suggested adjustments and reasoning, referencing specific items from your uploaded files (e.g., "move the morning walk earlier — Buddy has a vet appointment at 2pm and should not eat for 2 hours before")
- **Retrieved context** expander — the exact calendar and health snippets the model used

### 5. Mark tasks complete

Click **Done** next to any scheduled task to mark it complete. Recurring tasks (daily / weekly) automatically generate their next occurrence.

---

## Running tests

```bash
pytest -v
```

5 tests total — 2 for the original scheduler, 3 for the RAG and LLM layer (no network calls; Gemini is mocked).

---

## Reflection on AI collaboration and system design

### How I used AI during development

I used Claude as a collaborator throughout the RAG extension — for design decisions, code generation, and debugging. Before accepting any suggestion I made sure I could explain what the code does and why, so that if something broke I could reason about it rather than just re-prompting until it passed.

In practice that looked like three things. First, I had the AI explore the existing codebase and map the architecture before writing anything, so its suggestions were grounded in the actual code rather than generic patterns. Second, I asked it clarifying questions in stages — data ingestion approach, LLM role, vector store choice — rather than giving one vague prompt and accepting whatever came back. Third, I read every generated file before letting it run, and ran the tests myself to verify the output was correct, not just plausible.

 AI-generated code can look correct and still be wrong in subtle ways. The tests were the contract — if they passed, the implementation was trustworthy; if they didn't, I had to understand the failure rather than just ask the AI to patch it.

---

### One helpful suggestion

The most consequential design decision the AI recommended was making the LLM output **advisory only** — storing Gemini's response as `ai_summary` on the plan instance, but never overwriting `task.start_time`. Its argument: if the model hallucinates a time or misreads the context, the user's actual schedule stays intact. The rule-based plan is always the source of truth.

This is responsible AI design at the system level. Any time an LLM output can affect a user's real-world actions — in this case, when they care for their pet — there should be a human review step before that output is acted on. Displaying the AI refinement as a suggestion the owner reads and decides to apply, rather than a change that silently happens, keeps the human in the loop. I kept this recommendation exactly as proposed.

---

### One flawed suggestion

The AI specified `google-generativeai` as the Gemini SDK. When I ran pytest after implementation, the output included a `FutureWarning` that the package had been deprecated in favour of `google-genai` and would no longer receive bug fixes.

---

### System limitations and future improvements

**Free-text output limits automation.** Because Gemini returns markdown prose, the app can display suggestions but cannot apply them automatically. A structured output contract (asking the model to return JSON with proposed task changes) would enable an "Apply suggestions" button — but it would also make the model's reasoning less transparent. That tradeoff deserves deliberate attention, not just implementation convenience.

**No persistence.** Owner info, pets, tasks, and the plan all live in Streamlit session state and disappear on refresh. Responsible handling of any persistent user data — even something as low-stakes as pet care tasks — would require thinking about storage, access control, and what happens when data is deleted.

**Retrieval quality degrades with generic queries.** The RAG queries are built from task names and the plan date. A health record phrased differently from the query may not surface, which means the LLM could give advice without seeing a relevant record that exists in the knowledge base. A future version could improve this with better query construction, date-range metadata filtering, or showing the owner which records were *not* retrieved so they can judge whether the model had enough context.

---

## Project structure

```
applied-ai-system-project/
├── app.py                  # Streamlit UI
├── pawpal_system.py        # Core domain: Pet, Owner, Task, DailyPlan
├── rag.py                  # RagIndex — ChromaDB-backed knowledge retrieval
├── llm.py                  # GeminiClient — LLM refinement via Gemini API
├── main.py                 # CLI demo script
├── data/
│   ├── sample_calendar.md  # Example calendar events (markdown)
│   └── sample_health.json  # Example pet health records (JSON)
├── tests/
│   ├── test_pawpal.py      # Scheduler tests
│   └── test_rag.py         # RAG + LLM tests
├── requirements.txt
├── .env.example
└── .gitignore
```
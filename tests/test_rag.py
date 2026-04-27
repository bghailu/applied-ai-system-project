from datetime import date, time

import pytest

from pawpal_system import DailyPlan, Owner, Pet, Task
from rag import RagIndex


# ---------------------------------------------------------------------------
# Test 1: indexed markdown blocks are retrievable by semantic query
# ---------------------------------------------------------------------------

def test_index_markdown_retrieves(tmp_path):
    rag = RagIndex(persist_dir=str(tmp_path / "chroma"))
    text = (
        "# Vet appointment for Mochi\n"
        "Annual checkup at Bayside Animal Clinic on 2026-04-26 at 2pm.\n"
        "\n---\n"
        "# Morning walk with Buddy\n"
        "Buddy enjoys a 30-minute walk in the park before breakfast.\n"
    )
    added = rag.index_markdown(text, source_type="calendar", source_name="sample.md")
    assert added == 2

    results = rag.query("vet visit for the cat", source_type="calendar", k=1)
    assert len(results) == 1
    assert "Vet" in results[0]["document"]


# ---------------------------------------------------------------------------
# Test 2: missing API key raises a clear error
# ---------------------------------------------------------------------------

def test_gemini_client_missing_api_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    # Re-import inside the test so load_dotenv at import time has no effect
    import importlib

    import llm
    importlib.reload(llm)

    with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
        llm.GeminiClient()


# ---------------------------------------------------------------------------
# Test 3: generate_with_ai uses retrieved context and does not mutate times
# ---------------------------------------------------------------------------

class _FakeResponse:
    def __init__(self, text):
        self.text = text


class _FakeModel:
    def __init__(self, *args, **kwargs):
        pass

    def generate_content(self, prompt):
        # Echo back so we can assert the prompt carried our context
        return _FakeResponse(
            "## Suggested adjustments\n"
            "- Move walk earlier because of vet appointment.\n"
            "\n## Reasoning\n"
            f"Saw context. Prompt length: {len(prompt)}."
        )


def test_generate_with_ai_uses_mocked_llm(tmp_path, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")

    import importlib

    import llm
    importlib.reload(llm)

    monkeypatch.setattr(llm.genai, "configure", lambda **kwargs: None)
    monkeypatch.setattr(llm.genai, "GenerativeModel", _FakeModel)

    rag = RagIndex(persist_dir=str(tmp_path / "chroma"))
    rag.index_markdown(
        "# Vet appointment for Mochi\nMochi has a vet visit at 2pm on 2026-04-26.",
        source_type="calendar",
        source_name="cal.md",
    )
    rag.index_json(
        [{"pet": "Mochi", "date": "2026-04-15", "type": "vet visit",
          "notes": "Recovering, avoid strenuous play."}],
        source_type="health",
        source_name="health.json",
    )

    owner = Owner(name="Alex", available_start=time(8, 0), available_end=time(18, 0))
    cat = Pet(name="Mochi", species="cat")
    tasks = [
        Task(name="Morning walk", pet=cat, duration_minutes=30, priority=1),
        Task(name="Feed lunch", pet=cat, duration_minutes=10, priority=2),
    ]
    plan = DailyPlan(owner=owner, tasks=tasks, plan_date=date(2026, 4, 26))

    rule_based_times_before = [t.start_time for t in plan.tasks]
    plan.generate()
    rule_based_times = [t.start_time for t in plan.tasks]
    assert rule_based_times != rule_based_times_before  # rule scheduler ran

    plan.generate_with_ai(rag, llm.GeminiClient())

    assert hasattr(plan, "ai_summary")
    assert "Suggested adjustments" in plan.ai_summary
    assert plan.ai_context["calendar"]  # something retrieved
    # AI must NOT mutate task times — they should match the rule-based result
    assert [t.start_time for t in plan.tasks] == rule_based_times

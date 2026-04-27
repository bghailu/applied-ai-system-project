"""Gemini LLM client used to refine the rule-based daily plan."""

from __future__ import annotations

import os
from typing import Any

import google.generativeai as genai
from dotenv import load_dotenv


load_dotenv()

DEFAULT_MODEL = "gemini-2.5-flash"


def _format_docs(docs: list[dict]) -> str:
    if not docs:
        return "(none)"
    return "\n".join(f"  {i + 1}. {d['document']}" for i, d in enumerate(docs))


def _format_tasks(tasks: list[Any]) -> str:
    lines = []
    priority_label = {1: "high", 2: "medium", 3: "low"}
    for t in tasks:
        when = t.start_time.strftime("%I:%M %p") if t.start_time else "unscheduled"
        lines.append(
            f"  - {t.name} for {t.pet.name} "
            f"({t.duration_minutes} min, {priority_label.get(t.priority, '?')} priority) "
            f"— {when}"
        )
    return "\n".join(lines) if lines else "  (no tasks)"


def build_prompt(rule_based_summary, calendar_docs, health_docs, owner, pets, tasks) -> str:
    pet_list = ", ".join(f"{p.name} ({p.species})" for p in pets) or "(none)"
    return f"""You are PawPal+, an assistant that helps a pet owner plan daily care tasks.

Owner: {owner.name}
Available window: {owner.available_start.strftime('%I:%M %p')} – {owner.available_end.strftime('%I:%M %p')}
Pets: {pet_list}

Tasks for today:
{_format_tasks(tasks)}

A rule-based scheduler already produced this baseline plan:
---
{rule_based_summary}
---

Relevant calendar context retrieved from the owner's knowledge base:
{_format_docs(calendar_docs)}

Relevant pet health context retrieved from the knowledge base:
{_format_docs(health_docs)}

Using the calendar and health context above, suggest refinements to the baseline plan.
Be concrete: reference specific events or health notes when they justify a change
(e.g., "move the walk earlier because of the 2pm vet appointment", or
"shorten the play session — Mochi is recovering from surgery").
If the baseline already looks fine given the context, say so and explain why.

Respond in plain text with these two sections, each starting with the heading exactly as shown:

## Suggested adjustments
- bullet list of concrete changes (or "No changes recommended.")

## Reasoning
- short paragraph explaining how the calendar / health context shaped your suggestions.
"""


class GeminiClient:
    def __init__(self, model: str = DEFAULT_MODEL):
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY not set")
        genai.configure(api_key=api_key)
        self.model_name = model
        self.model = genai.GenerativeModel(model)

    def refine_plan(self, rule_based_summary, calendar_docs, health_docs, owner, pets, tasks) -> dict:
        prompt = build_prompt(rule_based_summary, calendar_docs, health_docs, owner, pets, tasks)
        response = self.model.generate_content(prompt)
        return {"summary": response.text, "prompt": prompt}

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta


# ---------------------------------------------------------------------------
# Pet
# ---------------------------------------------------------------------------

@dataclass
class Pet:
    name: str
    species: str


# ---------------------------------------------------------------------------
# Task
# ---------------------------------------------------------------------------

@dataclass
class Task:
    name: str
    pet: Pet
    duration_minutes: int
    priority: int                    # 1 = high, 2 = medium, 3 = low
    frequency: str | None = None     # "daily", "weekly", or None (one-time)
    due_date: date | None = None
    start_time: time | None = None
    reason: str | None = None
    completed: bool = False

    def is_scheduled(self) -> bool:
        return self.start_time is not None

    def schedule(self, start_time: time, reason: str) -> None:
        self.start_time = start_time
        self.reason = reason

    def mark_completed(self) -> "Task | None":
        self.completed = True
        return self._next_occurrence()

    def mark_incomplete(self) -> None:
        self.completed = False

    def _next_occurrence(self) -> "Task | None":
        if self.frequency == "daily":
            next_due = (self.due_date or date.today()) + timedelta(days=1)
        elif self.frequency == "weekly":
            next_due = (self.due_date or date.today()) + timedelta(weeks=1)
        else:
            return None
        return Task(
            name=self.name,
            pet=self.pet,
            duration_minutes=self.duration_minutes,
            priority=self.priority,
            frequency=self.frequency,
            due_date=next_due,
        )

    @property
    def end_time(self) -> time | None:
        if self.start_time is None:
            return None
        dt = datetime.combine(date.today(), self.start_time) + timedelta(minutes=self.duration_minutes)
        return dt.time()


# ---------------------------------------------------------------------------
# Owner
# ---------------------------------------------------------------------------

class Owner:
    def __init__(self, name: str, available_start: time, available_end: time):
        self.name = name
        self.available_start = available_start
        self.available_end = available_end

    def available_minutes(self) -> int:
        start = datetime.combine(date.today(), self.available_start)
        end = datetime.combine(date.today(), self.available_end)
        return int((end - start).total_seconds() // 60)


# ---------------------------------------------------------------------------
# DailyPlan
# ---------------------------------------------------------------------------

class DailyPlan:
    def __init__(self, owner: Owner, tasks: list[Task], plan_date: date):
        self.owner = owner
        self.tasks = tasks
        self.plan_date = plan_date

    def generate(self) -> None:
        # Reset any previous scheduling
        for task in self.tasks:
            task.start_time = None
            task.reason = None

        # Sort by priority (1=high first), then by duration (shorter first as tiebreak)
        sorted_tasks = sorted(self.tasks, key=lambda t: (t.priority, t.duration_minutes))

        current_time = datetime.combine(self.plan_date, self.owner.available_start)
        end_time = datetime.combine(self.plan_date, self.owner.available_end)

        for task in sorted_tasks:
            task_end = current_time + timedelta(minutes=task.duration_minutes)
            if task_end <= end_time:
                priority_label = {1: "high", 2: "medium", 3: "low"}.get(task.priority, "unknown")
                reason = (
                    f"Scheduled at {current_time.strftime('%I:%M %p')} — "
                    f"{priority_label} priority task for {task.pet.name} "
                    f"({task.duration_minutes} min)"
                )
                task.schedule(current_time.time(), reason)
                current_time = task_end
            # If it doesn't fit, leave start_time and reason as None

    def scheduled_tasks(self) -> list[Task]:
        return [t for t in self.tasks if t.is_scheduled()]

    def unscheduled_tasks(self) -> list[Task]:
        return [t for t in self.tasks if not t.is_scheduled()]

    def detect_conflicts(self) -> list[str]:
        warnings = []
        scheduled = self.scheduled_tasks()

        for i, a in enumerate(scheduled):
            for b in scheduled[i + 1:]:
                # Overlap when: a starts before b ends AND b starts before a ends
                if a.start_time < b.end_time and b.start_time < a.end_time:
                    warnings.append(
                        f"Conflict: '{a.name}' ({a.pet.name}, "
                        f"{a.start_time.strftime('%I:%M %p')}–{a.end_time.strftime('%I:%M %p')}) "
                        f"overlaps with '{b.name}' ({b.pet.name}, "
                        f"{b.start_time.strftime('%I:%M %p')}–{b.end_time.strftime('%I:%M %p')})"
                    )
        return warnings

    def mark_task_complete(self, task: Task) -> Task | None:
        next_task = task.mark_completed()
        if next_task is not None:
            self.tasks.append(next_task)
        return next_task

    def filter_tasks(self, *, completed: bool | None = None, pet_name: str | None = None) -> list[Task]:
        result = self.tasks
        if completed is not None:
            result = [t for t in result if t.completed == completed]
        if pet_name is not None:
            result = [t for t in result if t.pet.name.lower() == pet_name.lower()]
        return result

    def sort_by_time(self) -> list[Task]:
        scheduled = self.scheduled_tasks()
        return sorted(scheduled, key=lambda t: t.start_time.strftime("%H:%M"))

    def generate_with_ai(self, rag_index, llm_client) -> None:
        # Rule-based plan stays the source of truth
        self.generate()

        queries = [
            f"{t.pet.name} {t.name} {self.plan_date.isoformat()}"
            for t in self.tasks
        ]
        window_q = (
            f"{self.plan_date.isoformat()} "
            f"{self.owner.available_start.strftime('%H:%M')}-"
            f"{self.owner.available_end.strftime('%H:%M')}"
        )

        cal_docs: list[dict] = []
        health_docs: list[dict] = []
        for q in queries + [window_q]:
            cal_docs += rag_index.query(q, source_type="calendar", k=2)
            health_docs += rag_index.query(q, source_type="health", k=2)

        cal_docs = list({d["document"]: d for d in cal_docs}.values())
        health_docs = list({d["document"]: d for d in health_docs}.values())

        result = llm_client.refine_plan(
            self.summary(),
            cal_docs,
            health_docs,
            self.owner,
            [t.pet for t in self.tasks],
            self.tasks,
        )
        self.ai_summary = result["summary"]
        self.ai_context = {"calendar": cal_docs, "health": health_docs}

    def summary(self) -> str:
        lines = [f"Daily Plan for {self.owner.name} — {self.plan_date.strftime('%A, %B %d %Y')}"]
        lines.append(f"Available window: {self.owner.available_start.strftime('%I:%M %p')} – "
                     f"{self.owner.available_end.strftime('%I:%M %p')} "
                     f"({self.owner.available_minutes()} min)\n")

        scheduled = self.scheduled_tasks()
        unscheduled = self.unscheduled_tasks()

        if scheduled:
            lines.append("Scheduled tasks:")
            for task in sorted(scheduled, key=lambda t: t.start_time):
                status = "[x]" if task.completed else "[ ]"
                lines.append(f"  {status} {task.start_time.strftime('%I:%M %p')} – {task.end_time.strftime('%I:%M %p')}"
                             f"  {task.name} ({task.pet.name})")
        else:
            lines.append("No tasks could be scheduled.")

        if unscheduled:
            lines.append("\nCould not fit:")
            for task in unscheduled:
                lines.append(f"  - {task.name} ({task.pet.name}, {task.duration_minutes} min)")

        total = sum(t.duration_minutes for t in scheduled)
        lines.append(f"\nTotal time scheduled: {total} min of {self.owner.available_minutes()} min available.")
        return "\n".join(lines)

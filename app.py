import json
import os

import streamlit as st
from datetime import date, time
from dotenv import load_dotenv

import pawpal_system as ps
from rag import RagIndex


load_dotenv()

st.set_page_config(page_title="PawPal+", page_icon="🐾", layout="centered")
st.title("🐾 PawPal+")

# ---------------------------------------------------------------------------
# Owner & Pets
# ---------------------------------------------------------------------------
st.subheader("Owner & Pets")

col1, col2 = st.columns(2)
with col1:
    owner_name = st.text_input("Owner name", value="Jordan")
    avail_start = st.time_input("Available from", value=time(8, 0))
    avail_end = st.time_input("Available until", value=time(18, 0))
with col2:
    pet_name = st.text_input("Pet name", value="Mochi")
    species = st.selectbox("Species", ["dog", "cat", "other"])

if "pets" not in st.session_state:
    st.session_state.pets = []

col_save, col_add = st.columns(2)
with col_save:
    if st.button("Save Owner"):
        st.session_state.owner = ps.Owner(
            name=owner_name,
            available_start=avail_start,
            available_end=avail_end,
        )
        st.session_state.tasks = []
        st.session_state.plan = None
        st.success(f"Saved owner: {owner_name}")
with col_add:
    if st.button("Add Pet"):
        if not pet_name.strip():
            st.warning("Enter a pet name.")
        else:
            st.session_state.pets.append(ps.Pet(name=pet_name.strip(), species=species))
            st.success(f"Added {pet_name} ({species})")

if "owner" in st.session_state:
    o = st.session_state.owner
    st.caption(
        f"Owner: **{o.name}** | "
        f"{o.available_start.strftime('%I:%M %p')} – {o.available_end.strftime('%I:%M %p')} "
        f"({o.available_minutes()} min available)"
    )

if st.session_state.pets:
    st.write("**Pets:**")
    for i, p in enumerate(st.session_state.pets):
        col_pet, col_remove = st.columns([5, 1])
        with col_pet:
            st.write(f"- {p.name} ({p.species})")
        with col_remove:
            if st.button("Remove", key=f"remove_pet_{i}"):
                st.session_state.pets.pop(i)
                st.rerun()

st.divider()

# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------
st.subheader("Tasks")

if "tasks" not in st.session_state:
    st.session_state.tasks = []

if "owner" not in st.session_state or not st.session_state.pets:
    st.info("Save an owner and add at least one pet above before adding tasks.")
else:
    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        task_title = st.text_input("Task title", value="Morning walk")
    with col2:
        pet_options = [p.name for p in st.session_state.pets]
        selected_pet_name = st.selectbox("Pet", pet_options)
    with col3:
        duration = st.number_input("Duration (minutes)", min_value=1, max_value=240, value=20)
    with col4:
        priority_label = st.selectbox("Priority", ["high", "medium", "low"])
    with col5:
        frequency_label = st.selectbox("Frequency", ["one-time", "daily", "weekly"])

    if st.button("Add task"):
        priority_map = {"high": 1, "medium": 2, "low": 3}
        frequency_map = {"one-time": None, "daily": "daily", "weekly": "weekly"}
        selected_pet = next(p for p in st.session_state.pets if p.name == selected_pet_name)
        task = ps.Task(
            name=task_title,
            pet=selected_pet,
            duration_minutes=int(duration),
            priority=priority_map[priority_label],
            frequency=frequency_map[frequency_label],
            due_date=date.today(),
        )
        st.session_state.tasks.append(task)

    if st.session_state.tasks:
        with st.expander("Filter tasks"):
            filter_status = st.selectbox("Show", ["all", "incomplete", "completed"])
            completed_map = {"all": None, "completed": True, "incomplete": False}
            temp_plan = ps.DailyPlan(
                owner=st.session_state.owner,
                tasks=st.session_state.tasks,
                plan_date=date.today(),
            )
            filtered = temp_plan.filter_tasks(completed=completed_map[filter_status])

        priority_names = {1: "high", 2: "medium", 3: "low"}
        st.write(f"Tasks ({len(filtered)} shown):")
        rows = [
            {
                "Task": t.name,
                "Pet": t.pet.name,
                "Duration (min)": t.duration_minutes,
                "Priority": priority_names[t.priority],
                "Frequency": t.frequency or "one-time",
                "Done": "✓" if t.completed else "",
            }
            for t in filtered
        ]
        st.table(rows)
    else:
        st.info("No tasks yet. Add one above.")

st.divider()

# ---------------------------------------------------------------------------
# Knowledge Base (RAG)
# ---------------------------------------------------------------------------
st.subheader("Knowledge Base")
st.caption(
    "Upload owner calendar files and pet health records (Markdown or JSON). "
    "These are indexed locally with ChromaDB and used to ground the AI plan."
)

cal_uploads = st.file_uploader(
    "Calendar files",
    type=["md", "json"],
    accept_multiple_files=True,
    key="cal_uploads",
)
health_uploads = st.file_uploader(
    "Health records",
    type=["md", "json"],
    accept_multiple_files=True,
    key="health_uploads",
)


def _index_uploads(rag: RagIndex, files, source_type: str) -> int:
    total = 0
    for f in files or []:
        raw = f.read()
        text = raw.decode("utf-8") if isinstance(raw, bytes) else raw
        if f.name.lower().endswith(".json"):
            try:
                data = json.loads(text)
            except json.JSONDecodeError as e:
                st.error(f"{f.name}: invalid JSON ({e})")
                continue
            if not isinstance(data, list):
                st.error(f"{f.name}: expected a JSON list of objects")
                continue
            total += rag.index_json(data, source_type=source_type, source_name=f.name)
        else:
            total += rag.index_markdown(text, source_type=source_type, source_name=f.name)
    return total


col_build, col_reset = st.columns(2)
with col_build:
    if st.button("Build / refresh index"):
        if "rag" not in st.session_state:
            st.session_state.rag = RagIndex()
        rag = st.session_state.rag
        added = 0
        added += _index_uploads(rag, cal_uploads, "calendar")
        added += _index_uploads(rag, health_uploads, "health")
        if added:
            st.success(f"Indexed {added} new docs — total {rag.count()}")
        else:
            st.info("No files to index. Upload calendar or health files first.")
with col_reset:
    if st.button("Reset index"):
        if "rag" in st.session_state:
            st.session_state.rag.reset()
            st.success("Knowledge base cleared.")
        else:
            st.info("Nothing to reset.")

if "rag" in st.session_state:
    st.caption(f"Indexed documents: **{st.session_state.rag.count()}**")

st.divider()

# ---------------------------------------------------------------------------
# Generate Schedule
# ---------------------------------------------------------------------------
st.subheader("Build Schedule")

if "plan" not in st.session_state:
    st.session_state.plan = None

col_gen, col_ai = st.columns(2)
with col_gen:
    gen_clicked = st.button("Generate schedule")
with col_ai:
    ai_clicked = st.button("Generate AI plan")

if gen_clicked:
    if "owner" not in st.session_state:
        st.warning("Set an owner and pet first.")
    elif not st.session_state.tasks:
        st.warning("Add at least one task before generating a schedule.")
    else:
        plan = ps.DailyPlan(
            owner=st.session_state.owner,
            tasks=list(st.session_state.tasks),
            plan_date=date.today(),
        )
        plan.generate()
        st.session_state.plan = plan

if ai_clicked:
    if "owner" not in st.session_state:
        st.warning("Set an owner and pet first.")
    elif not st.session_state.tasks:
        st.warning("Add at least one task before generating a schedule.")
    elif not os.getenv("GEMINI_API_KEY"):
        st.error("GEMINI_API_KEY missing in .env — AI plan disabled.")
    elif st.session_state.get("rag") is None or st.session_state.rag.count() == 0:
        st.warning("Upload and index knowledge base files first.")
    else:
        from llm import GeminiClient

        plan = ps.DailyPlan(
            owner=st.session_state.owner,
            tasks=list(st.session_state.tasks),
            plan_date=date.today(),
        )
        try:
            with st.spinner("Asking Gemini to refine the plan…"):
                plan.generate_with_ai(st.session_state.rag, GeminiClient())
            st.session_state.plan = plan
        except Exception as e:
            st.error(f"AI plan failed: {e}")

if st.session_state.get("plan"):
    plan = st.session_state.plan

    # Conflict warnings
    conflicts = plan.detect_conflicts()
    if conflicts:
        for c in conflicts:
            st.warning(f"⚠️ {c}")

    # Scheduled tasks sorted by time with Done buttons
    scheduled = plan.sort_by_time()
    unscheduled = plan.unscheduled_tasks()

    if scheduled:
        st.write("**Scheduled tasks:**")
        for i, task in enumerate(scheduled):
            col1, col2 = st.columns([5, 1])
            with col1:
                status = "✓" if task.completed else "○"
                st.write(
                    f"{status} **{task.start_time.strftime('%I:%M %p')} – "
                    f"{task.end_time.strftime('%I:%M %p')}** "
                    f"— {task.name} ({task.pet.name})"
                )
            with col2:
                if not task.completed:
                    if st.button("Done", key=f"complete_{i}"):
                        next_task = plan.mark_task_complete(task)
                        if next_task:
                            st.toast(f"'{task.name}' done! Next due: {next_task.due_date}")
                        else:
                            st.toast(f"'{task.name}' marked complete.")
                        st.rerun()
                else:
                    st.write("✓ Done")

    if unscheduled:
        st.warning(f"{len(unscheduled)} task(s) didn't fit in the available window.")
        for task in unscheduled:
            st.write(f"  - {task.name} ({task.pet.name}, {task.duration_minutes} min)")

    if getattr(plan, "ai_summary", None):
        st.divider()
        st.subheader("AI refinement")
        st.markdown(plan.ai_summary)
        ctx = getattr(plan, "ai_context", {}) or {}
        with st.expander("Retrieved context"):
            cal = ctx.get("calendar", [])
            health = ctx.get("health", [])
            st.markdown("**Calendar**")
            if cal:
                for d in cal:
                    st.write(f"- {d['document']}")
            else:
                st.caption("(none retrieved)")
            st.markdown("**Health**")
            if health:
                for d in health:
                    st.write(f"- {d['document']}")
            else:
                st.caption("(none retrieved)")

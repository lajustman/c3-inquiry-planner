"""
Streamlit playground for the C3 Inquiry Planner.

Run with:
    streamlit run streamlit_app.py
"""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Dict, List, Tuple

import streamlit as st
from flask import session

from webapp.app import (
    APP_ROOT,
    app,
    api_learning_path,
    build_lesson_from_expectation,
    store_student_interests,
)
from webapp.standards_catalog import StandardsCatalog, get_michigan_catalog


@st.cache_resource(show_spinner=False)
def load_catalog() -> StandardsCatalog:
    """Load and cache the Michigan standards catalog once per Streamlit session."""
    catalog_dir = Path(APP_ROOT) / "Curriculum-Ontology" / "michigan"
    with app.app_context():
        return get_michigan_catalog(catalog_dir)


def _unit_label(unit: Dict[str, object]) -> str:
    if unit.get("type") == "grade":
        return f"Grade {unit.get('code')}"
    return unit.get("label", "Unit")


def _list_expectations(catalog: StandardsCatalog) -> List[Tuple[str, str]]:
    options: List[Tuple[str, str]] = []
    for unit in getattr(catalog, "units", []):
        unit_data = unit if isinstance(unit, dict) else unit.__dict__
        unit_label = _unit_label(unit_data)
        for category in unit_data.get("categories", []):
            category_data = category if isinstance(category, dict) else category.__dict__
            for expectation in category_data.get("expectations", []):
                expectation_data = expectation if isinstance(expectation, dict) else expectation.__dict__
                display = f"{expectation_data['full_code']} – {expectation_data['label']} ({unit_label})"
                options.append((display, expectation_data["full_code"]))
    return options


@contextmanager
def flask_session_context(path: str = "/", method: str = "GET", json_payload: Dict | None = None):
    stored = st.session_state.get("flask_session", {})
    ctx = app.test_request_context(path, method=method, json=json_payload)
    ctx.push()
    session.clear()
    session.update(stored)
    try:
        yield
        st.session_state["flask_session"] = dict(session)
    finally:
        ctx.pop()


def _render_plan(plan: Dict[str, object]) -> None:
    st.subheader(plan.get("title", "Lesson Overview"))

    cols = st.columns(3)
    cols[0].metric("Grade Band", plan.get("grade_band", "–"))
    cols[1].metric("Disciplines", ", ".join(plan.get("disciplines", [])) or "–")
    cols[2].metric("Focus Concepts", ", ".join(plan.get("focus_concepts", [])) or "–")

    with st.expander("Lesson Objectives", expanded=True):
        for obj in plan.get("objectives", []):
            st.write(f"- {obj}")

    with st.expander("Suggested Resources"):
        st.info(
            "Generate a personalized learning path below to see stage-specific resources for this lesson."
        )

    with st.expander("Key Vocabulary", expanded=False):
        for vocab in plan.get("vocabulary", []):
            st.markdown(f"- **{vocab['term']}** – {vocab['definition']}")


def main() -> None:
    st.set_page_config(page_title="C3 Inquiry Planner – Streamlit Demo", layout="wide")
    st.title("C3 Inquiry Planner – Streamlit Demo")
    st.caption("Build a Michigan standards-aligned lesson on the fly.")

    catalog = load_catalog()
    expectation_options = _list_expectations(catalog)
    if not expectation_options:
        st.error("No Michigan expectations found. Check the ontology assets.")
        return

    option_labels = [label for label, _ in expectation_options]
    selected_label = st.selectbox("Select a standard:", option_labels, index=0)
    selected_code = next((code for label, code in expectation_options if label == selected_label), "")

    if "plan" not in st.session_state:
        st.session_state["plan"] = None

    if selected_code and st.button("Build Lesson", type="primary"):
        with st.spinner("Building lesson..."):
            with flask_session_context(f"/streamlit/preview/{selected_code}", method="POST"):
                runtime, _, _, _ = build_lesson_from_expectation(selected_code)
            st.session_state["plan"] = runtime.plan
            st.success(f'Lesson ready for {selected_code}')

    plan = st.session_state.get("plan")
    if plan:
        _render_plan(plan)

        st.markdown("---")
        st.header("Shape Your Inquiry Preferences")
        interest_options = [
            "debates",
            "stories",
            "data",
            "maps",
            "design",
            "art",
            "action",
        ]
        learning_modes = ["speaking", "visual", "data", "writing", "project"]
        support_levels = ["structure", "balance", "independent"]

        with st.form("interest-form"):
            selected_modes = st.multiselect("What sparks your curiosity?", interest_options)
            topic_focus = st.text_area(
                "Topics you care about",
                placeholder="youth climate strikes, school discipline, local government",
            )
            chosen_learning = st.multiselect("Learning experiences that fit you", learning_modes)
            support_choice = st.radio("Support preference", support_levels, horizontal=True)
            exemplar_text = st.text_area(
                "Preferred exemplar contexts (comma separated)",
                placeholder="Student climate walkouts, Youth voting drives",
            )
            save_clicked = st.form_submit_button("Save interests")

        if save_clicked:
            keywords = [piece.strip() for piece in topic_focus.split(",") if piece.strip()]
            selected_exemplars = [piece.strip() for piece in exemplar_text.split(",") if piece.strip()]
            interests_payload = {
                "interest_modes": selected_modes,
                "topic_focus": topic_focus.strip(),
                "learning_mode": chosen_learning,
                "support_preference": support_choice,
                "selected_exemplars": selected_exemplars,
                "keywords": keywords,
                "ai_suggestions": [],
            }
            with flask_session_context("/streamlit/interests", method="POST"):
                store_student_interests(interests_payload)
            st.success("Interests saved. Generate a learning path when ready.")

        st.markdown("---")
        st.header("Generate Learning Path")
        if st.button("Generate Personalized Path"):
            with st.spinner("Assembling learning path..."):
                with flask_session_context("/api/learning-path", method="POST", json_payload={"force": True}):
                    response = api_learning_path()
                data = response.get_json()
                st.session_state["learning_path"] = data.get("path")
                st.success("Learning path updated!")

        learning_path = st.session_state.get("learning_path")
        if learning_path:
            for idx, stage in enumerate(learning_path.get("stages", []), start=1):
                st.subheader(f"Stage {idx}: {stage.get('title', 'Stage')}")
                st.write(stage.get("prompt") or stage.get("purpose", ""))
                resources = stage.get("resources", [])
                if resources:
                    st.markdown("**Resources**")
                    for res in resources:
                        title = res.get("title", "Resource")
                        desc = res.get("description", "")
                        url = res.get("url")
                        if url:
                            st.markdown(f"- [{title}]({url}) – {desc}")
                        else:
                            st.markdown(f"- {title} – {desc}")
                if stage.get("activities"):
                    st.markdown("**Activities**")
                    for act in stage["activities"]:
                        st.markdown(f"- {act}")
                st.markdown("---")
    else:
        st.info("Build a lesson to unlock inquiry preferences and learning path tools.")


if __name__ == "__main__":
    main()

"""
Streamlit playground for the C3 Inquiry Planner.

Run with:
    streamlit run streamlit_app.py
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Tuple

import streamlit as st
from webapp.app import APP_ROOT, app, build_lesson_from_expectation
from webapp.standards_catalog import StandardsCatalog, get_michigan_catalog


@st.cache_resource(show_spinner=False)
def load_catalog() -> StandardsCatalog:
    """Load and cache the Michigan standards catalog once per Streamlit session."""
    catalog_dir = Path(APP_ROOT) / "Curriculum-Ontology" / "michigan"
    with app.app_context():
        return get_michigan_catalog(catalog_dir)


def _unit_label(unit: Dict[str, object]) -> str:
    if unit["type"] == "grade":
        return f"Grade {unit['code']}"
    return unit["label"]


def _list_expectations(catalog: StandardsCatalog) -> List[Tuple[str, str, object]]:
    options: List[Tuple[str, str, object]] = []
    for unit in catalog.units:
        unit_label = _unit_label(unit)
        for category in unit.categories:
            for expectation in category.expectations:
                display = f"{expectation.full_code} – {expectation.label} ({unit_label})"
                options.append((display, expectation.full_code, category))
    return options


@st.cache_data(show_spinner=False)
def _expectation_index(catalog: StandardsCatalog) -> Dict[str, Dict[str, object]]:
    index: Dict[str, Dict[str, object]] = {}
    for label, code, category in _list_expectations(catalog):
        index[code] = {
            "label": label,
            "category": category,
        }
    return index


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
        stages = plan.get("sequence", [])
        for stage in stages:
            title = stage.get("stage") or stage.get("goal") or "Stage"
            st.markdown(f"**{title}** – {stage.get('goal', '').strip()}")
            for resource in stage.get("resources", []):
                label = resource.get("title", "Resource")
                url = resource.get("url", "")
                description = resource.get("description", "")
                if url:
                    st.markdown(f"- [{label}]({url}) – {description}")
                else:
                    st.markdown(f"- {label} – {description}")

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

    option_labels = [label for label, _, _ in expectation_options]
    selected_label = st.selectbox("Select a standard:", option_labels, index=0)
    selected_code = ""
    for label, code, _ in expectation_options:
        if label == selected_label:
            selected_code = code
            break

    if not selected_code:
        st.warning("Choose a standard to generate a lesson preview.")
        return

    if st.button("Generate Lesson Preview", type="primary"):
        with st.spinner("Building lesson..."):
            with app.test_request_context(f"/streamlit/preview/{selected_code}"):
                runtime, _, _, _ = build_lesson_from_expectation(selected_code)
                st.success("Lesson ready!")
                _render_plan(runtime.plan)
    else:
        st.info("Choose a standard above and click “Generate Lesson Preview”.")


if __name__ == "__main__":
    main()

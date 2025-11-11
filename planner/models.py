from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class SourceSpec:
    """Representation of an instructional source with provenance notes."""

    id: str
    title: str
    type: str
    origin: str
    value: str
    citation: Optional[str] = None
    url: Optional[str] = None
    reading_level: Optional[str] = None
    differentiation: Optional[str] = None


@dataclass
class Indicator:
    """C3 Indicator entry parsed from the ontology files."""

    code: str
    label: str
    dimension: str
    grade_band: str
    discipline: Optional[str] = None
    concepts: List[str] = field(default_factory=list)


@dataclass
class ExemplarCase:
    """Contextual exemplar used to demonstrate concept transfer."""

    id: str
    title: str
    description: str
    era_or_setting: Optional[str] = None
    discipline_emphasis: Optional[str] = None


@dataclass
class PlanConfig:
    """User-supplied configuration for building an inquiry plan."""

    title: str
    grade_band: str
    time_box_minutes: int
    disciplines: List[str]
    focus_concepts: List[str]
    anchor_context: str
    transfer_context: str
    reading_range: str = "6-8"
    teacher_intent: Optional[str] = None
    required_standards: List[str] = field(default_factory=list)
    student_needs: Dict[str, str] = field(default_factory=dict)
    compelling_question: Optional[str] = None
    supporting_questions: Optional[List[str]] = None
    indicator_overrides: Dict[str, List[str]] = field(default_factory=dict)
    extend_move: Optional[str] = None
    sources: List[SourceSpec] = field(default_factory=list)
    exemplars: List[ExemplarCase] = field(default_factory=list)
    interest_prompts: List[str] = field(default_factory=list)
    dok_overrides: Dict[str, str] = field(default_factory=dict)
    iteration_focus: Optional[str] = None
    selected_exemplars: List[str] = field(default_factory=list)


@dataclass
class PlanBundle:
    """Rendered artifacts for a single inquiry plan."""

    teacher_markdown: str
    student_markdown: str
    learning_graph: Dict[str, object]
    plan_data: Dict[str, object]

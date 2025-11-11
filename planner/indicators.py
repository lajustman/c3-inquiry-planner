from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from .models import Indicator


GRADE_MAP = {
    "K_2": "K-2",
    "G3_5": "3-5",
    "G6_8": "6-8",
    "G9_12": "9-12",
}


CONCEPT_SPLIT_RE = re.compile(r"c3:([A-Za-z0-9_]+)")
INDICATOR_HEADER_RE = re.compile(r"^(c3:I_[^\s]+)\s+a c3:Indicator ;")
CODE_RE = re.compile(r'c3:hasCode\s+"([^"]+)"')
LABEL_RE = re.compile(r'rdfs:label\s+"([^"]+)"')
DIMENSION_RE = re.compile(r"c3:inDimension\s+c3:Dimension([1-4])")
DISCIPLINE_RE = re.compile(r"c3:isIndicatorOf\s+c3:([A-Za-z0-9_]+)")
GRADE_RE = re.compile(r"c3:targetsGradeBand\s+c3:([A-Za-z0-9_]+)")
CONCEPT_BLOCK_RE = re.compile(r"c3:addressesConcept\s+(.+?);")


def _normalise_concepts(block: str) -> List[str]:
    matches = CONCEPT_SPLIT_RE.findall(block)
    cleaned: List[str] = []
    for match in matches:
        cleaned.append(match.replace("_", " "))
    return cleaned


@dataclass
class IndicatorCatalog:
    """Container providing filtered access to C3 indicators."""

    indicators: List[Indicator]

    def __post_init__(self) -> None:
        self._by_code = {indicator.code: indicator for indicator in self.indicators}

    @classmethod
    def from_directory(cls, ontology_dir: Path) -> "IndicatorCatalog":
        indicators: List[Indicator] = []
        for ttl_path in sorted(ontology_dir.glob("c3-dimension*.ttl")):
            text = ttl_path.read_text(encoding="utf-8")
            indicators.extend(parse_indicators(text))
        return cls(indicators=indicators)

    def by_dimension(
        self,
        dimension: str,
        grade_band: Optional[str] = None,
        discipline: Optional[str] = None,
        concept: Optional[str] = None,
    ) -> List[Indicator]:
        dimension = dimension.upper()
        filtered = [ind for ind in self.indicators if ind.dimension == dimension]
        if grade_band:
            filtered = [ind for ind in filtered if ind.grade_band == grade_band]
        if discipline:
            norm = normalise_discipline(discipline)
            filtered = [ind for ind in filtered if ind.discipline == norm]
        if concept:
            norm_concept = normalise_concept(concept)
            filtered = [
                ind
                for ind in filtered
                if any(c.lower() == norm_concept.lower() for c in ind.concepts)
            ]
        filtered.sort(key=lambda ind: ind.code)
        return filtered

    def find_first(
        self,
        dimension: str,
        grade_band: str,
        *,
        discipline: Optional[str] = None,
        concept: Optional[str] = None,
    ) -> Optional[Indicator]:
        matches = self.by_dimension(
            dimension=dimension,
            grade_band=grade_band,
            discipline=discipline,
            concept=concept,
        )
        if matches:
            return matches[0]
        if concept:
            matches = self.by_dimension(
                dimension=dimension,
                grade_band=grade_band,
                discipline=discipline,
            )
            if matches:
                return matches[0]
        if discipline:
            matches = self.by_dimension(dimension=dimension, grade_band=grade_band)
            if matches:
                return matches[0]
        return None

    def by_codes(self, codes: Iterable[str]) -> List[Indicator]:
        found = []
        for code in codes:
            indicator = self._by_code.get(code)
            if indicator:
                found.append(indicator)
        return found


def parse_indicators(text: str) -> List[Indicator]:
    indicators: List[Indicator] = []
    block: List[str] = []
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        if not block:
            if INDICATOR_HEADER_RE.match(line):
                block.append(line)
        else:
            block.append(line)
            if line.endswith("."):
                indicator = block_to_indicator(block)
                if indicator:
                    indicators.append(indicator)
                block = []
    return indicators


def block_to_indicator(lines: List[str]) -> Optional[Indicator]:
    chunk = "\n".join(lines)
    code_match = CODE_RE.search(chunk)
    label_match = LABEL_RE.search(chunk)
    dimension_match = DIMENSION_RE.search(chunk)
    grade_match = GRADE_RE.search(chunk)
    if not (code_match and label_match and dimension_match and grade_match):
        return None
    code = code_match.group(1)
    label = label_match.group(1)
    dimension = f"D{dimension_match.group(1)}"
    grade_token = grade_match.group(1)
    grade_band = GRADE_MAP.get(grade_token, grade_token.replace("_", "-"))
    discipline = None
    discipline_match = DISCIPLINE_RE.search(chunk)
    if discipline_match:
        discipline = normalise_discipline(discipline_match.group(1))
    concepts: List[str] = []
    concept_block = CONCEPT_BLOCK_RE.search(chunk)
    if concept_block:
        concepts = [
            normalise_concept(token)
            for token in concept_block.group(1).split(",")
            if token.strip()
        ]
    return Indicator(
        code=code,
        label=label,
        dimension=dimension,
        grade_band=grade_band,
        discipline=discipline,
        concepts=concepts,
    )


def normalise_concept(raw: str) -> str:
    slug = raw.strip().replace("c3:", "").replace("_", " ")
    if not slug:
        return ""
    return " ".join(word.capitalize() for word in slug.split())


def normalise_discipline(raw: str) -> str:
    token = raw.replace("c3:", "").replace("_", " ").strip()
    mapping: Dict[str, str] = {
        "History": "History",
        "Civics": "Civics",
        "Civics And Government": "Civics",
        "Geography": "Geography",
        "Economics": "Economics",
        "EvidenceDomain": "Evidence",
        "CommunicatingConclusions": "Communicate",
    }
    if token in mapping:
        return mapping[token]
    return " ".join(word.capitalize() for word in token.split())

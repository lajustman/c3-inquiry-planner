from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
import re
from typing import Dict, Iterable, List, Optional


@dataclass
class ExpectationEntry:
    id: str
    code: str
    full_code: str
    label: str
    text: str


@dataclass
class CategoryEntry:
    id: str
    code: str
    label: str
    description: Optional[str]
    discipline_id: str
    discipline_label: str
    discipline_code: str
    expectations: List[ExpectationEntry] = field(default_factory=list)


@dataclass
class UnitEntry:
    id: str
    type: str  # "grade" or "course"
    code: str
    label: str
    order: int
    categories: List[CategoryEntry] = field(default_factory=list)


@dataclass
class StandardsCatalog:
    units: List[UnitEntry]
    expectation_index: Dict[str, Dict[str, object]]
    disciplines: Dict[str, str]


COURSE_ORDER = {
    "WHG": 1,
    "USHG": 2,
    "CIVICS": 3,
    "ECON": 4,
    "CG": 5,
}

DISCIPLINE_PATTERN = re.compile(
    r"(mi:Discipline_[A-Za-z0-9_]+)\s+a mi:Discipline\s*;\s*skos:prefLabel\s+\"([^\"]+)\"",
    re.MULTILINE,
)


def _collect_blocks(lines: List[str], prefix: str, marker: str) -> List[str]:
    blocks: List[str] = []
    idx = 0
    total = len(lines)
    while idx < total:
        stripped = lines[idx].strip()
        if stripped.startswith(prefix) and marker in stripped:
            block_lines = [lines[idx]]
            idx += 1
            while idx < total:
                block_lines.append(lines[idx])
                if lines[idx].strip().endswith("."):
                    idx += 1
                    break
                idx += 1
            blocks.append("\n".join(block_lines))
        else:
            idx += 1
    return blocks


def _extract_subject_id(block: str) -> str:
    first_line = block.splitlines()[0].strip()
    return first_line.split()[0]


def _extract_literal(block: str, predicate: str) -> Optional[str]:
    match = re.search(rf"{predicate}\s+\"([^\"]+)\"", block)
    if match:
        return match.group(1)
    return None


def _extract_reference(block: str, predicate: str) -> Optional[str]:
    match = re.search(rf"{predicate}\s+(mi:[A-Za-z0-9_]+)\s*;", block)
    if match:
        return match.group(1)
    return None


def _extract_integer(block: str, predicate: str) -> Optional[int]:
    match = re.search(rf"{predicate}\s+([0-9]+)", block)
    if match:
        try:
            return int(match.group(1))
        except ValueError:
            return None
    return None


def _code_sort_key(code: str) -> Iterable[object]:
    parts = re.split(r"[-._]", code)
    key: List[tuple[int, object]] = []
    for part in parts:
        token = part.strip()
        if not token:
            continue
        if token.isdigit():
            key.append((0, int(token)))
        else:
            key.append((1, token.upper()))
    return tuple(key)


def _parse_disciplines(standards_path: Path) -> Dict[str, str]:
    text = standards_path.read_text(encoding="utf-8")
    mapping: Dict[str, str] = {}
    for match in DISCIPLINE_PATTERN.finditer(text):
        mapping[match.group(1)] = match.group(2)
    return mapping


def _parse_unit_metadata(block: str, unit_type: str) -> Dict[str, object]:
    unit_id = _extract_subject_id(block)
    label = _extract_literal(block, "skos:prefLabel") or unit_id
    if unit_type == "grade":
        code = _extract_literal(block, "mi:gradeCode") or label
        order = _extract_integer(block, "mi:gradeOrder") or 0
    else:
        code = _extract_literal(block, "mi:courseCode") or unit_id
        order = 100 + COURSE_ORDER.get(code.upper(), len(COURSE_ORDER) + 1)
    return {
        "id": unit_id,
        "type": unit_type,
        "code": code,
        "label": label,
        "order": order,
    }


def _parse_categories(text: str, disciplines: Dict[str, str]) -> List[CategoryEntry]:
    categories: List[CategoryEntry] = []
    lines = text.splitlines()
    category_blocks = _collect_blocks(lines, "mi:Cat_", "a mi:StandardCategory")
    for block in category_blocks:
        category_id = _extract_subject_id(block)
        code = _extract_literal(block, "mi:categoryCode") or category_id
        label = _extract_literal(block, "skos:prefLabel") or category_id
        description = _extract_literal(block, "mi:categoryDescription")
        discipline_id = _extract_reference(block, "mi:inDiscipline") or ""
        discipline_label = disciplines.get(discipline_id, discipline_id.replace("mi:", ""))
        discipline_code = discipline_id.replace("mi:Discipline_", "")
        categories.append(
            CategoryEntry(
                id=category_id,
                code=code,
                label=label,
                description=description,
                discipline_id=discipline_id,
                discipline_label=discipline_label,
                discipline_code=discipline_code,
            )
        )
    return categories


def _parse_expectations(text: str) -> Dict[str, List[ExpectationEntry]]:
    expectations: Dict[str, List[ExpectationEntry]] = {}
    lines = text.splitlines()
    expectation_blocks = _collect_blocks(lines, "mi:Exp_", "a mi:Expectation")
    for block in expectation_blocks:
        expectation_id = _extract_subject_id(block)
        category_id = _extract_reference(block, "mi:inCategory")
        if not category_id:
            continue
        full_code = _extract_literal(block, "mi:fullCode") or expectation_id
        code = _extract_literal(block, "mi:expectationCode") or full_code
        label = _extract_literal(block, "skos:prefLabel") or full_code
        official_text = _extract_literal(block, "mi:officialText") or label
        entry = ExpectationEntry(
            id=expectation_id,
            code=code,
            full_code=full_code,
            label=label,
            text=official_text,
        )
        expectations.setdefault(category_id, []).append(entry)
    for entries in expectations.values():
        entries.sort(key=lambda item: _code_sort_key(item.full_code))
    return expectations


def _load_unit(path: Path, disciplines: Dict[str, str]) -> Optional[UnitEntry]:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()

    unit_blocks = _collect_blocks(lines, "mi:Grade_", "a mi:Grade")
    unit_type = "grade"
    if not unit_blocks:
        unit_blocks = _collect_blocks(lines, "mi:Course_", "a mi:Course")
        unit_type = "course"
    if not unit_blocks:
        return None

    unit_meta = _parse_unit_metadata(unit_blocks[0], unit_type)
    categories = _parse_categories(text, disciplines)
    expectations_map = _parse_expectations(text)

    category_index = {category.id: category for category in categories}
    for category_id, expectation_list in expectations_map.items():
        category = category_index.get(category_id)
        if category:
            category.expectations.extend(expectation_list)

    for category in categories:
        category.expectations.sort(key=lambda item: _code_sort_key(item.full_code))

    categories.sort(key=lambda item: (_code_sort_key(item.code), item.label))
    return UnitEntry(
        id=unit_meta["id"],
        type=unit_meta["type"],
        code=unit_meta["code"],
        label=unit_meta["label"],
        order=unit_meta["order"],
        categories=categories,
    )


def _load_catalog(root: Path) -> StandardsCatalog:
    disciplines = _parse_disciplines(root / "mi-standards.ttl")
    units: List[UnitEntry] = []
    expectation_index: Dict[str, Dict[str, object]] = {}

    for path in sorted(root.glob("mi-*.ttl")):
        if path.name in {"mi-base.ttl", "mi-standards.ttl"}:
            continue
        unit = _load_unit(path, disciplines)
        if not unit:
            continue
        units.append(unit)
        for category in unit.categories:
            for expectation in category.expectations:
                expectation_index[expectation.full_code] = {
                    "unit_id": unit.id,
                    "unit_label": unit.label,
                    "unit_type": unit.type,
                    "unit_code": unit.code,
                    "category_id": category.id,
                    "category_label": category.label,
                    "discipline_label": category.discipline_label,
                    "discipline_code": category.discipline_code,
                    "expectation": expectation,
                }

    units.sort(key=lambda item: (0 if item.type == "grade" else 1, item.order, item.label))
    return StandardsCatalog(units=units, expectation_index=expectation_index, disciplines=disciplines)


@lru_cache(maxsize=1)
def _cached_catalog(root_str: str) -> StandardsCatalog:
    root = Path(root_str)
    return _load_catalog(root)


def get_michigan_catalog(root: Path) -> StandardsCatalog:
    return _cached_catalog(str(root.resolve()))

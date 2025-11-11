#!/usr/bin/env python3

"""
Convert the C3 glossary Markdown file into a SKOS/Turtle module.

Reads:  Background Information/c3 Framework/c3-Vocab.md
Writes: c3/c3-glossary.ttl
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MD_PATH = ROOT / "Background Information" / "c3 Framework" / "c3-Vocab.md"
ONTO_DIR = ROOT / "Curriculum-Ontology" / "c3"
TTL_PATH = ONTO_DIR / "c3-glossary.ttl"


def parse_entries(text: str) -> list[dict[str, str]]:
    entries = []
    current = None
    state = "def"

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        if line.startswith("Example"):
            if current is None:
                continue
            current.setdefault("examples", []).append(line.split(":", 1)[1].strip())
            state = "example"
            continue

        if ":" in line and not line.startswith("Example"):
            term, rest = line.split(":", 1)
            if current:
                entries.append(current)
            current = {
                "term": term.strip(),
                "definition_lines": [rest.strip()] if rest.strip() else [],
                "examples": [],
            }
            state = "def"
            continue

        if current is None:
            continue

        if state == "def":
            current["definition_lines"].append(line)
        else:
            current["examples"].append(line)

    if current:
        entries.append(current)

    normalised = []
    for entry in entries:
        term = normalise_text(entry["term"])
        definition = " ".join(entry["definition_lines"]).strip()
        definition = normalise_text(definition)
        examples = " ".join(entry["examples"]).strip()
        examples = normalise_text(examples)
        normalised.append(
            {
                "term": term,
                "definition": definition,
                "example": examples,
            }
        )
    return normalised


def normalise_text(text: str) -> str:
    replacements = {
        "’": "'",
        "‘": "'",
        "“": '"',
        "”": '"',
        "–": "-",
        "—": "-",
        "…": "...",
        "\u00a0": " ",
    }
    for src, dst in replacements.items():
        text = text.replace(src, dst)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def slugify(term: str) -> str:
    slug = re.sub(r"[^0-9a-zA-Z]+", "_", term).strip("_").lower()
    if not slug:
        slug = "entry"
    return slug


def build_ttl(entries: list[dict[str, str]]) -> str:
    header = """@prefix c3:     <urn:c3:> .
@prefix dcterms:<http://purl.org/dc/terms/> .
@prefix owl:    <http://www.w3.org/2002/07/owl#> .
@prefix rdf:    <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix rdfs:   <http://www.w3.org/2000/01/rdf-schema#> .
@prefix skos:   <http://www.w3.org/2004/02/skos/core#> .
@prefix xsd:    <http://www.w3.org/2001/XMLSchema#> .

@base <urn:c3:> .

<urn:c3:glossary> a owl:Ontology ;
  rdfs:label "C3 Framework — Glossary" ;
  dcterms:description "Glossary terms extracted from the C3 Framework (pp. 102–112)." ;
  dcterms:creator "NCSS — College, Career, and Civic Life (C3) Framework for Social Studies State Standards" ;
  dcterms:source "C3 Framework, pp. 102–112" .

c3:GlossaryScheme a skos:ConceptScheme ;
  skos:prefLabel "C3 Glossary" ;
  dcterms:source "C3 Framework, pp. 102–112" .

"""
    lines = [header]
    for entry in entries:
        slug = slugify(entry["term"])
        iri = f"c3:glossary_term_{slug}"
        lines.append(f"{iri} a skos:Concept , c3:GlossaryTerm ;\n")
        lines.append(f'  skos:prefLabel "{entry["term"]}" ;\n')
        if entry["definition"]:
            lines.append(f'  skos:definition "{entry["definition"]}" ;\n')
            lines.append(f'  c3:hasDefinition "{entry["definition"]}" ;\n')
        if entry["example"]:
            lines.append(f'  skos:example "{entry["example"]}" ;\n')
            lines.append(f'  c3:hasExample "{entry["example"]}" ;\n')
        lines.append("  skos:inScheme c3:GlossaryScheme .\n\n")
    return "".join(lines)


def main() -> None:
    text = MD_PATH.read_text(encoding="utf-8")
    entries = parse_entries(text)
    ttl = build_ttl(entries)
    TTL_PATH.parent.mkdir(parents=True, exist_ok=True)
    TTL_PATH.write_text(ttl, encoding="utf-8")
    print(f"Wrote {TTL_PATH} with {len(entries)} entries.")


if __name__ == "__main__":
    main()

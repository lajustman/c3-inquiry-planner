from __future__ import annotations

import json
import os
import textwrap
import re
import socket
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Dict, List, Optional

try:  # Attempt to load project-level config if provided
        from llm_config import (
            OPENAI_API_BASE as CONFIGURED_BASE,
            OPENAI_API_KEY as CONFIGURED_KEY,
            OPENAI_MODEL as CONFIGURED_MODEL,
            OPENAI_TIMEOUT as CONFIGURED_TIMEOUT,
        )
except ImportError:  # pragma: no cover
    CONFIGURED_KEY = CONFIGURED_BASE = CONFIGURED_MODEL = CONFIGURED_TIMEOUT = None

from .models import PlanConfig


class LLMUnavailable(RuntimeError):
    """Raised when a configured LLM endpoint cannot complete the request."""


@dataclass
class ExemplarIdea:
    """Structured exemplar suggestion returned by an LLM."""

    id: str
    title: str
    description: str
    era_or_setting: Optional[str]
    discipline_emphasis: Optional[str]

    def to_dict(self) -> Dict[str, Optional[str]]:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "era_or_setting": self.era_or_setting,
            "discipline_emphasis": self.discipline_emphasis,
        }


class LLMClient:
    """Interface for LLM backends that can suggest exemplar ideas."""

    def suggest_exemplars(
        self,
        config: PlanConfig,
        conversation: List[Dict[str, str]],
        keywords: List[str],
    ) -> List[ExemplarIdea]:
        raise NotImplementedError

    def plan_learning_path(
        self,
        config: PlanConfig,
        student_state: Dict[str, object],
        interests: Dict[str, object],
    ) -> Dict[str, object]:
        raise NotImplementedError


class OpenAIChatClient(LLMClient):
    """Minimal client for the OpenAI chat completions API."""

    def __init__(
        self,
        api_key: str,
        *,
        model: str = "gpt-4o-mini",
        base_url: str = "https://api.openai.com/v1/chat/completions",
        timeout: float = 20.0,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.base_url = base_url
        self.timeout = timeout

    def suggest_exemplars(
        self,
        config: PlanConfig,
        conversation: List[Dict[str, str]],
        keywords: List[str],
    ) -> List[ExemplarIdea]:
        body = self._build_payload(config, conversation, keywords)
        data = json.dumps(body).encode("utf-8")
        request = urllib.request.Request(
            self.base_url,
            data=data,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:  # pragma: no cover - network dependent
            raise LLMUnavailable(f"LLM request failed with HTTP {exc.code}") from exc
        except (urllib.error.URLError, TimeoutError, socket.timeout) as exc:  # pragma: no cover
            raise LLMUnavailable("LLM request timed out or could not reach the endpoint") from exc

        try:
            message = payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError) as exc:  # pragma: no cover - defensive
            raise LLMUnavailable("LLM response missing content") from exc

        suggestions = self._parse_exemplar_response(message)
        if not suggestions:
            raise LLMUnavailable("LLM response did not contain exemplar suggestions")
        return suggestions

    def plan_learning_path(
        self,
        config: PlanConfig,
        student_state: Dict[str, object],
        interests: Dict[str, object],
    ) -> Dict[str, object]:
        body = self._build_learning_payload(config, student_state, interests)
        data = json.dumps(body).encode("utf-8")
        request = urllib.request.Request(
            self.base_url,
            data=data,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:  # pragma: no cover - network dependent
            raise LLMUnavailable(f"LLM request failed with HTTP {exc.code}") from exc
        except (urllib.error.URLError, TimeoutError, socket.timeout) as exc:  # pragma: no cover
            raise LLMUnavailable("LLM request timed out or could not reach the endpoint") from exc

        try:
            content = payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError) as exc:  # pragma: no cover - defensive
            raise LLMUnavailable("LLM response missing content") from exc

        path = self._parse_learning_path_response(content)
        if not path:
            raise LLMUnavailable("LLM response did not contain a usable learning path")
        return path

    def _parse_exemplar_response(self, content: str) -> List[ExemplarIdea]:
        # Try strict JSON first
        try:
            payload = json.loads(content)
        except json.JSONDecodeError:
            payload = None

        if isinstance(payload, list):
            ideas: List[ExemplarIdea] = []
            for idx, entry in enumerate(payload, start=1):
                if not isinstance(entry, dict):
                    continue
                title = entry.get("title") or f"Student Exemplar {idx}"
                identifier = entry.get("id") or self._slugify(title, idx)
                description = entry.get("description") or "LLM suggested exemplar."
                era = entry.get("era_or_setting")
                discipline = entry.get("discipline_emphasis")
                ideas.append(
                    ExemplarIdea(
                        id=identifier,
                        title=title,
                        description=description,
                        era_or_setting=era,
                        discipline_emphasis=discipline,
                    )
                )
            if ideas:
                return ideas

        # Fallback: parse free-form text bullet list
        return self._parse_text_exemplars(content)

    def _parse_text_exemplars(self, content: str) -> List[ExemplarIdea]:
        chunks = [chunk.strip() for chunk in re.split(r"\n\s*\n", content) if chunk.strip()]
        ideas: List[ExemplarIdea] = []
        for idx, chunk in enumerate(chunks, start=1):
            lines = [line.strip("•*- \t") for line in chunk.splitlines() if line.strip()]
            if not lines:
                continue
            title_line = lines[0]
            title, description = self._split_title_description(title_line)

            era = discipline = None
            extra_lines = lines[1:]
            description_parts = [description] if description else []
            for line in extra_lines:
                lower = line.lower()
                if "setting" in lower or "era" in lower:
                    era = line.split(":", 1)[-1].strip() if ":" in line else line.strip()
                elif "discipline" in lower:
                    discipline = line.split(":", 1)[-1].strip() if ":" in line else line.strip()
                else:
                    description_parts.append(line)
            description_text = " ".join(part for part in description_parts if part).strip() or "LLM suggested exemplar."

            ideas.append(
                ExemplarIdea(
                    id=self._slugify(title, idx),
                    title=title,
                    description=description_text,
                    era_or_setting=era,
                    discipline_emphasis=discipline,
                )
            )
        return ideas

    @staticmethod
    def _split_title_description(line: str) -> tuple[str, str]:
        if ":" in line:
            title, desc = line.split(":", 1)
            return title.strip() or "Student Exemplar", desc.strip()
        return line.strip() or "Student Exemplar", ""

    @staticmethod
    def _slugify(title: str, idx: int) -> str:
        slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
        return slug or f"exemplar-ai-{idx}"

    def _build_learning_payload(
        self,
        config: PlanConfig,
        student_state: Dict[str, object],
        interests: Dict[str, object],
    ) -> Dict[str, object]:
        objectives = student_state.get("plan_objectives") or []
        objectives_block = "\n".join(f"- {item}" for item in objectives[:4]) or "- Objective focus not specified"
        focus = ", ".join(config.focus_concepts) or "Core concept"
        disciplines = ", ".join(config.disciplines) or "Integrated Social Studies"
        grade_band = config.grade_band or "6-8"

        compelling_question = student_state.get("compelling_question") or config.compelling_question or "the compelling question"
        supporting_questions = student_state.get("supporting_questions") or config.supporting_questions or []
        supporting_block = "\n".join(f"- {q}" for q in supporting_questions[:3]) or "- Supporting questions will be developed with the learner."

        student_questions = student_state.get("questions") or []
        question_block = "\n".join(f"- {q}" for q in student_questions) or "- No student-authored questions captured yet."

        primers = student_state.get("primers") or []
        primer_block = "\n".join(f"- {primer}" for primer in primers[:3]) if primers else "- No primer is required."

        interest_modes = interests.get("interest_modes") or []
        interest_modes_block = ", ".join(interest_modes) or "Not specified"

        learning_modes = interests.get("learning_mode") or []
        if isinstance(learning_modes, str):
            learning_modes = [learning_modes]
        learning_modes_block = ", ".join(learning_modes) or "Not specified"

        support_pref = interests.get("support_preference") or "balance"
        selected_exemplars = interests.get("selected_exemplars") or []
        exemplar_block = ", ".join(selected_exemplars) or "No exemplars chosen yet"
        keyword_block = ", ".join(interests.get("keywords", [])) or "No explicit keywords supplied"

        instructions = textwrap.dedent(
            f"""
            You are designing a personalised learning pathway for a secondary student working within the C3 Framework.

            Lesson focus: {config.title}
            Grade band: {grade_band}
            Disciplines: {disciplines}
            Focus concepts: {focus}

            Learning objectives:
            {objectives_block}

            Student-authored questions:
            {question_block}

            Interest signals:
            • Exploration modes: {interest_modes_block}
            • Preferred learning experiences: {learning_modes_block}
            • Desired support level: {support_pref}
            • Interest keywords: {keyword_block}
            • Chosen exemplars or contexts: {exemplar_block}

            Lesson questions:
            • Compelling: {compelling_question}
            Supporters:
            {supporting_block}

            Quick primers to include when needed:
            {primer_block}

            Produce a JSON object describing a student-facing learning path with these parts:
            {{
              "summary": "<2 sentence overview of how the path connects to their interests and the concepts>",
              "stages": [
                {{
                  "id": "<unique slug>",
                  "type": "<launch_connect|investigate|create|primer>",
                  "title": "<stage name>",
                  "duration": null,
                  "purpose": "<why this step matters>",
                  "prompt": "<student-facing prompt>",
                  "student_questions": ["<include when the stage connects to their own questions>", ...],
                  "activities": ["<student-facing action>", "<another action>", ...],
                  "resources": [
                    {{"title": "<resource name>", "url": "<optional url or null>", "description": "<how to use it>", "format": "<article|video|audio|interactive>"}}
                  ],
                  "keywords": ["<list of concepts or interest terms>", ...],
                  "product_suggestions": ["<short product option>", ...],
                  "checkpoint": "<how they show understanding during this stage>"
                }}, ...
              ],
              "mastery_tip": "<guidance for meeting proficiency aligned to the support preference>",
              "next_focus": ["<short bullet about what to review next>", ...]
            }}

            Requirements:
            • Use 3-4 stages that respect the preferred learning experiences and support level.
            • Include a "launch_connect" stage that draws directly on the student's own questions.
            • Include an "investigate" stage with at least one resource for each format (article, video, audio, interactive).
            • Include a "create" stage with product_suggestions the student could complete quickly.
            • Reference selected exemplars or similar contexts to keep transfer explicit.
            • Tie activities to the lesson's focus concepts and the student's questions.
            • Do not introduce exemplars or case studies that are not listed under the chosen exemplars/contexts or clearly implied by the student's interests.
            • Avoid referencing the Birmingham Children's Crusade unless it appears in the chosen exemplars list.
            • Keep language student-friendly and actionable for an individual learner. Avoid instructions that require class presentations, whole-group sharing, or partner work.
            • Set "duration" to null so the UI can omit time estimates.
            • Use null for missing URLs; do not invent long URLs.
            • Return ONLY valid JSON as specified.
            """
        ).strip()

        return {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": "You are a learning-experience designer who creates inquiry-based, student-facing plans aligned to the C3 Framework.",
                },
                {"role": "user", "content": instructions},
            ],
            "temperature": 0.3,
        }

    def describe_artifact(self, mime_type: str, feature_summary: str) -> str:
        prompt = textwrap.dedent(
            f"""
            You are providing friendly feedback on a student's product.
            Artifact type: {mime_type}
            Observed details: {feature_summary}

            Write two sentences that praise a strength and offer one specific suggestion framed as encouragement. Tie your suggestion to the observed details.
            """
        ).strip()

        body = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": "You provide concise, supportive feedback on student work products.",
                },
                {
                    "role": "user",
                    "content": prompt,
                },
            ],
            "temperature": 0.2,
            "max_tokens": 220,
        }

        data = json.dumps(body).encode("utf-8")
        request = urllib.request.Request(
            self.base_url,
            data=data,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise LLMUnavailable(f"LLM request failed with HTTP {exc.code}") from exc
        except (urllib.error.URLError, TimeoutError, socket.timeout) as exc:
            raise LLMUnavailable("LLM request timed out or could not reach the endpoint") from exc

        try:
            message = payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError) as exc:
            raise LLMUnavailable("LLM response missing content") from exc

        return message.strip()

    def _parse_learning_path_response(self, content: str) -> Dict[str, object]:
        stripped = content.strip()
        if stripped.startswith("```"):
            match = re.search(r"```(?:json)?\s*(.*?)\s*```", stripped, re.DOTALL)
            if match:
                stripped = match.group(1)
        try:
            payload = json.loads(stripped)
        except json.JSONDecodeError:
            return {}

        if not isinstance(payload, dict):
            return {}

        stages_raw = payload.get("stages")
        if not isinstance(stages_raw, list):
            return {}

        stages: List[Dict[str, object]] = []
        for idx, stage in enumerate(stages_raw):
            if not isinstance(stage, dict):
                continue
            title = str(stage.get("title", "Stage")).strip() or "Stage"
            purpose = str(stage.get("purpose", "")).strip()
            prompt = str(stage.get("prompt", "")).strip()
            stage_type = str(stage.get("type", "custom")).strip() or "custom"
            stage_id = str(stage.get("id", "")).strip() or self._slugify(title, idx + 1)

            activities_raw = stage.get("activities") or []
            if not isinstance(activities_raw, list):
                activities_raw = [activities_raw]
            activities = [str(item).strip() for item in activities_raw if str(item).strip()]

            resources_raw = stage.get("resources") or []
            if not isinstance(resources_raw, list):
                resources_raw = [resources_raw]
            resources: List[Dict[str, str]] = []
            for resource in resources_raw:
                if not isinstance(resource, dict):
                    continue
                url_value = resource.get("url")
                if isinstance(url_value, str):
                    url_r = url_value.strip()
                else:
                    url_r = None
                if not url_r:
                    continue
                title_r = str(resource.get("title", "Resource")).strip() or "Resource"
                description_r = str(resource.get("description", "")).strip()
                format_r = str(resource.get("format", "article")).strip().lower() or "article"
                source_r = str(resource.get("source", "")).strip()
                resources.append({
                    "title": title_r,
                    "url": url_r,
                    "description": description_r,
                    "format": format_r,
                    "source": source_r,
                })

            checkpoint = str(stage.get("checkpoint", "")).strip()

            student_questions_raw = stage.get("student_questions") or []
            if not isinstance(student_questions_raw, list):
                student_questions_raw = [student_questions_raw]
            student_questions = [str(item).strip() for item in student_questions_raw if str(item).strip()]

            keywords_raw = stage.get("keywords") or []
            if not isinstance(keywords_raw, list):
                keywords_raw = [keywords_raw]
            keywords = [str(item).strip() for item in keywords_raw if str(item).strip()]

            product_suggestions_raw = stage.get("product_suggestions") or []
            if not isinstance(product_suggestions_raw, list):
                product_suggestions_raw = [product_suggestions_raw]
            product_suggestions = [str(item).strip() for item in product_suggestions_raw if str(item).strip()]

            stages.append(
                {
                    "id": stage_id,
                    "type": stage_type,
                    "title": title,
                    "purpose": purpose,
                    "prompt": prompt,
                    "activities": activities,
                    "resources": resources,
                    "checkpoint": checkpoint,
                    "student_questions": student_questions,
                    "keywords": keywords,
                    "product_suggestions": product_suggestions,
                }
            )

        if not stages:
            return {}

        summary = str(payload.get("summary", "")).strip()
        mastery_tip = str(payload.get("mastery_tip", "")).strip()
        notes_raw = payload.get("next_focus") or []
        if not isinstance(notes_raw, list):
            notes_raw = [notes_raw]
        notes = [str(item).strip() for item in notes_raw if str(item).strip()]

        return {
            "summary": summary,
            "stages": stages,
            "mastery_tip": mastery_tip,
            "next_focus": notes,
        }

    def suggest_supporting_questions(self, prompt: str) -> List[str]:
        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "You generate short, student-friendly inquiry questions."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.4,
        }
        data = json.dumps(body).encode("utf-8")
        request = urllib.request.Request(
            self.base_url,
            data=data,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:  # pragma: no cover
            raise LLMUnavailable(f"LLM request failed with HTTP {exc.code}") from exc
        except (urllib.error.URLError, TimeoutError) as exc:  # pragma: no cover
            raise LLMUnavailable("LLM request timed out or could not reach the endpoint") from exc

        try:
            content = payload["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError) as exc:  # pragma: no cover
            raise LLMUnavailable("LLM response missing content") from exc

        candidates = [line.strip("- ") for line in content.splitlines() if line.strip()]
        return [cand for cand in candidates if len(cand) > 3]

    def _build_payload(
        self,
        config: PlanConfig,
        conversation: List[Dict[str, str]],
        keywords: List[str],
    ) -> Dict[str, object]:
        convo_lines = [
            f"Prompt: {turn['prompt']}\nStudent: {turn['response']}"
            for turn in conversation
            if turn.get("response")
        ]
        conversation_block = "\n\n".join(convo_lines) or "No student responses captured."
        exemplar_lines = [
            f"- {ex.title}: {ex.description}"
            for ex in config.exemplars
        ]
        existing_block = "\n".join(exemplar_lines) or "No existing exemplars provided."
        focus = ", ".join(config.focus_concepts) or "Concept"
        disciplines = ", ".join(config.disciplines) or "Integrated Social Studies"
        grade_band = config.grade_band or "6-8"
        standards = ", ".join(config.required_standards) or "C3 Framework D1-D4 indicators"
        keyword_block = ", ".join(keywords) if keywords else "No explicit keywords supplied."

        instructions = textwrap.dedent(
            f"""
            Design 2-3 additional exemplar inquiry contexts that align with these parameters:
            • Focus concepts: {focus}
            • Grade band: {grade_band}
            • Disciplines: {disciplines}
            • Standards / indicators: {standards}
            • Existing exemplars: 
            {existing_block}

            Student interest signals (keep language age-appropriate and apolitical):
            {conversation_block}

            Summarized interest keywords: {keyword_block}

            Requirements for each suggested exemplar:
            • Must advance the same concepts and indicators listed above.
            • Should be developmentally appropriate for grade band {grade_band}.
            • Should reflect the disciplinary habits of mind for {disciplines}.
            • Provide a concise 1-2 sentence description that explains the transferable concept move.
            • Include an optional era_or_setting (time period, locality, or context) when known.
            • Include an optional discipline_emphasis describing which disciplinary tools are foregrounded.

            Return ONLY valid JSON matching this schema:
            [
              {{
                "id": "exemplar.ai-<slug>",
                "title": "<concise title>",
                "description": "<1-2 sentence description>",
                "era_or_setting": "<optional context or null>",
                "discipline_emphasis": "<optional emphasis or null>"
              }}
            ]

            Do not repeat existing exemplars exactly. Ensure IDs are unique, kebab-case, and prefixed with "exemplar.ai-".
            """
        ).strip()

        return {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": "You are a curriculum designer who proposes transferable inquiry contexts aligned to the C3 Framework.",
                },
                {"role": "user", "content": instructions},
            ],
            "temperature": 0.2,
        }


def _normalise_base_url(base_url: str) -> str:
    """Ensure the base URL points at the chat completions endpoint."""

    trimmed = base_url.strip()
    if not trimmed:
        return "https://api.openai.com/v1/chat/completions"

    # Remove redundant trailing slashes for comparison.
    stripped = trimmed.rstrip("/")
    if stripped.endswith("chat/completions"):
        return stripped

    return f"{stripped}/chat/completions"


def default_llm_client() -> Optional[LLMClient]:
    """Instantiate an LLM client based on environment variables or project config."""

    api_key = os.environ.get("OPENAI_API_KEY") or CONFIGURED_KEY
    if not api_key:
        return None

    model = os.environ.get("OPENAI_MODEL") or CONFIGURED_MODEL or "gpt-4o-mini"
    base_url_raw = os.environ.get("OPENAI_API_BASE") or CONFIGURED_BASE or "https://api.openai.com/v1/chat/completions"
    base_url = _normalise_base_url(base_url_raw)
    timeout_str = os.environ.get("OPENAI_TIMEOUT") or (str(CONFIGURED_TIMEOUT) if CONFIGURED_TIMEOUT else None)
    timeout = float(timeout_str) if timeout_str is not None else 20.0
    return OpenAIChatClient(api_key, model=model, base_url=base_url, timeout=timeout)

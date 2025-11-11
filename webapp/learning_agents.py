from __future__ import annotations

import json
import os
from typing import Dict, List, Optional

try:  # LangChain 0.1+ preferred package
    from langchain_openai import ChatOpenAI  # type: ignore
except ImportError:  # pragma: no cover - optional dependency
    try:
        from langchain.chat_models import ChatOpenAI  # type: ignore
    except ImportError:  # pragma: no cover - optional dependency
        ChatOpenAI = None  # type: ignore

try:
    from langchain.schema import HumanMessage, SystemMessage  # type: ignore
except ImportError:  # pragma: no cover - optional dependency
    try:
        from langchain_core.messages import HumanMessage, SystemMessage  # type: ignore
    except ImportError:  # pragma: no cover - optional dependency
        HumanMessage = SystemMessage = None  # type: ignore

try:  # project-level defaults
    from llm_config import (  # type: ignore
        OPENAI_API_BASE as CONFIGURED_BASE,
        OPENAI_API_KEY as CONFIGURED_KEY,
        OPENAI_MODEL as CONFIGURED_MODEL,
        OPENAI_TIMEOUT as CONFIGURED_TIMEOUT,
    )
except ImportError:  # pragma: no cover - optional dependency
    CONFIGURED_BASE = CONFIGURED_KEY = CONFIGURED_MODEL = CONFIGURED_TIMEOUT = None


class StageAgentUnavailable(RuntimeError):
    """Raised when LangChain sub-agents cannot be initialised."""


def _normalise_base_url(base_url: Optional[str]) -> Optional[str]:
    if not base_url:
        return None
    stripped = base_url.rstrip("/")
    if stripped.endswith("chat/completions"):
        return stripped
    return f"{stripped}/chat/completions"


def _extract_json_block(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        start = stripped.find("```")
        end = stripped.rfind("```")
        if end > start:
            inner = stripped[start + 3 : end]
            if inner.lstrip().startswith("json"):
                inner = inner.split("\n", 1)[1] if "\n" in inner else ""
            return inner.strip()
    return stripped


def _tokenise(text: str) -> List[str]:
    return [token.strip() for token in str(text or "").split(",") if token.strip()]


class StageAgentCoordinator:
    """Hands each learning path stage to a LangChain-powered sub-agent."""

    def __init__(
        self,
        *,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout: Optional[float] = None,
        temperature: float = 0.25,
    ) -> None:
        if ChatOpenAI is None or HumanMessage is None or SystemMessage is None:
            raise StageAgentUnavailable("LangChain is not installed. Run `pip install langchain langchain-openai`.")

        resolved_key = api_key or os.environ.get("OPENAI_API_KEY") or CONFIGURED_KEY
        if not resolved_key:
            raise StageAgentUnavailable("Missing OPENAI_API_KEY for LangChain stage agents.")

        resolved_model = model or os.environ.get("OPENAI_MODEL") or CONFIGURED_MODEL or "gpt-4o-mini"
        resolved_base = (
            base_url or os.environ.get("OPENAI_API_BASE") or CONFIGURED_BASE or "https://api.openai.com/v1/chat/completions"
        )
        resolved_timeout = timeout or os.environ.get("OPENAI_TIMEOUT") or CONFIGURED_TIMEOUT
        request_timeout = float(resolved_timeout) if resolved_timeout is not None else 30.0

        base_url_normalised = _normalise_base_url(resolved_base)
        os.environ.setdefault("OPENAI_API_KEY", resolved_key)
        if base_url_normalised:
            os.environ.setdefault("OPENAI_API_BASE", base_url_normalised)

        attempts: List[Dict[str, object]] = [
            {
                "model": resolved_model,
                "temperature": temperature,
                "max_retries": 2,
                "timeout": request_timeout,
                "openai_api_key": resolved_key,
                "openai_api_base": base_url_normalised,
            },
            {
                "model": resolved_model,
                "temperature": temperature,
                "max_retries": 2,
                "request_timeout": request_timeout,
                "api_key": resolved_key,
                "base_url": base_url_normalised,
            },
            {
                "model_name": resolved_model,
                "temperature": temperature,
                "max_retries": 2,
                "request_timeout": request_timeout,
                "openai_api_key": resolved_key,
                "openai_api_base": base_url_normalised,
            },
        ]

        self._llm = None
        last_error: Optional[Exception] = None
        for attempt in attempts:
            compact = {k: v for k, v in attempt.items() if v is not None}
            try:
                self._llm = ChatOpenAI(**compact)  # type: ignore[arg-type]
                break
            except TypeError as exc:
                last_error = exc
                continue
            except Exception as exc:  # pragma: no cover - dependency specific
                last_error = exc
                continue

        if self._llm is None:
            raise StageAgentUnavailable(str(last_error) if last_error else "Unable to initialise stage agent")
        self._system_prompt = (
            "You orchestrate specialist sub-agents for inquiry-based learning steps. "
            "Each stage must feel bespoke to the student's current lesson, expectation, and interests. "
            "Return JSON only."
        )

    def refine_learning_path(
        self,
        path: Dict[str, object],
        plan: Dict[str, object],
        interests: Dict[str, object],
    ) -> Dict[str, object]:
        stages = path.get("stages")
        if not isinstance(stages, list):
            return path

        updated: List[Dict[str, object]] = []
        for stage in stages:
            if not isinstance(stage, dict):
                updated.append(stage)
                continue
            try:
                agent_result = self._run_stage_agent(stage, plan, interests)
            except StageAgentUnavailable:
                return path
            if agent_result:
                self._merge_stage(stage, agent_result)
            updated.append(stage)
        path["stages"] = updated
        return path

    def _run_stage_agent(
        self,
        stage: Dict[str, object],
        plan: Dict[str, object],
        interests: Dict[str, object],
    ) -> Dict[str, object]:
        interest_modes = interests.get("interest_modes", [])
        if isinstance(interest_modes, str):
            interest_modes = [interest_modes]

        payload = {
            "lesson_title": plan.get("title"),
            "objective_sample": plan.get("objectives", [])[:2],
            "focus_concepts": plan.get("focus_concepts", []),
            "compelling_question": plan.get("questions", {}).get("compelling"),
            "supporting_questions": plan.get("questions", {}).get("supporting", []),
            "selected_exemplars": interests.get("selected_exemplars", []),
            "interest_topics": interests.get("topic_focus"),
            "interest_modes": interest_modes,
            "stage": {
                "id": stage.get("id"),
                "title": stage.get("title"),
                "type": stage.get("type"),
                "prompt": stage.get("prompt"),
                "activities": stage.get("activities"),
                "resources": stage.get("resources"),
            },
        }

        schema = {
            "stage_title": "string",
            "student_prompt": "string",
            "objective_focus": "string",
            "student_moves": ["list of short actionable steps"],
            "resources": [
                {
                    "title": "string",
                    "format": "article|video|audio|interactive",
                    "url": "string or null",
                    "rationale": "string",
                }
            ],
            "evidence_focus": ["list of keywords relevant for this stage"],
            "summary_note": "string with quick explanation for teachers",
        }

        instructions = (
            "Hand this stage to a specialised agent. "
            "Use the student's interests to avoid repeating examples from other lessons. "
            "Prioritise new sources tied to the expectation named in focus_concepts. "
            "Provide exactly 3-4 resources with short rationales (no duplicate titles). "
            "Return JSON matching the schema."
        )

        context_blob = json.dumps(payload, ensure_ascii=False, indent=2)
        schema_blob = json.dumps(schema, ensure_ascii=False, indent=2)
        human_prompt = (
            f"{instructions}\n\nLesson + stage context:\n{context_blob}\n\n"
            f"JSON schema (field names only):\n{schema_blob}\n"
            "Respond with JSON only."
        )

        messages = [
            SystemMessage(content=self._system_prompt),
            HumanMessage(content=human_prompt),
        ]
        try:
            response = self._llm.invoke(messages)
        except Exception as exc:  # pragma: no cover - network / sdk errors
            raise StageAgentUnavailable(str(exc)) from exc

        text = getattr(response, "content", str(response)).strip()
        if not text:
            return {}
        blob = _extract_json_block(text)
        try:
            data = json.loads(blob)
        except json.JSONDecodeError:
            return {}
        if not isinstance(data, dict):
            return {}
        return data

    def _merge_stage(self, stage: Dict[str, object], agent_result: Dict[str, object]) -> None:
        title = str(agent_result.get("stage_title") or "").strip()
        if title:
            stage["title"] = title

        student_prompt = str(agent_result.get("student_prompt") or "").strip()
        if student_prompt:
            stage["prompt"] = student_prompt

        objective_focus = str(agent_result.get("objective_focus") or "").strip()
        if objective_focus:
            stage["purpose"] = objective_focus

        student_moves = agent_result.get("student_moves") or []
        if isinstance(student_moves, list) and student_moves:
            stage["activities"] = [str(move).strip() for move in student_moves if str(move).strip()]

        resources = self._normalise_resources(agent_result.get("resources"))
        if resources:
            stage["resources"] = resources

        evidence_focus = agent_result.get("evidence_focus") or []
        if isinstance(evidence_focus, list) and evidence_focus:
            existing = stage.get("keywords") or []
            if not isinstance(existing, list):
                existing = _tokenise(existing)
            keywords = []
            seen = set()
            for collection in (existing, evidence_focus):
                for item in collection:
                    token = str(item).strip()
                    if not token:
                        continue
                    key = token.lower()
                    if key in seen:
                        continue
                    seen.add(key)
                    keywords.append(token)
            stage["keywords"] = keywords

        summary_note = str(agent_result.get("summary_note") or "").strip()
        if summary_note:
            stage["agent_summary"] = summary_note

        stage["source"] = "langchain-agent"

    @staticmethod
    def _normalise_resources(raw: object) -> List[Dict[str, str]]:
        if not isinstance(raw, list):
            return []
        resources: List[Dict[str, str]] = []
        for entry in raw:
            if not isinstance(entry, dict):
                continue
            title = str(entry.get("title") or "").strip()
            if not title:
                continue
            url = str(entry.get("url") or "").strip()
            fmt = str(entry.get("format") or "").strip().lower() or "article"
            rationale = str(entry.get("rationale") or "").strip()
            resources.append(
                {
                    "title": title,
                    "url": url,
                    "format": fmt,
                    "rationale": rationale,
                }
            )
        return resources

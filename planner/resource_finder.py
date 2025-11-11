from __future__ import annotations

import json
import logging
import os
import re
import urllib.parse
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional

import httpx

try:
    from resource_config import (
        BROWSERLESS_API_KEY,
        PERPLEXITY_API_KEY,
    )
except ImportError:  # pragma: no cover
    PERPLEXITY_API_KEY = os.environ.get("PERPLEXITY_API_KEY")
    BROWSERLESS_API_KEY = os.environ.get("BROWSERLESS_API_KEY")

logger = logging.getLogger(__name__)


@dataclass
class ResourceCandidate:
    title: str
    url: str
    description: str
    medium: str
    source: Optional[str] = None


class ResourceFinder:
    """Searches for and validates learning resources using external services."""

    def __init__(
        self,
        *,
        perplexity_key: Optional[str] = PERPLEXITY_API_KEY,
        browserless_key: Optional[str] = BROWSERLESS_API_KEY,
        timeout: float = 20.0,
    ) -> None:
        self.perplexity_key = perplexity_key
        self.browserless_key = browserless_key
        self.timeout = timeout
        self._client = httpx.Client(timeout=timeout)

    def close(self) -> None:
        self._client.close()

    def find_resources(
        self,
        query_terms: Iterable[str],
        preferred_media: Optional[Iterable[str]] = None,
        limit: int = 6,
    ) -> List[Dict[str, str]]:
        if not self.perplexity_key:
            logger.debug("Perplexity API key not configured; skipping resource discovery.")
            return []

        query_text = self._build_query_text(query_terms, preferred_media, limit)
        candidates = self._ask_perplexity(query_text)
        logger.debug("Perplexity returned %d candidates", len(candidates))

        verified: List[Dict[str, str]] = []
        for candidate in candidates:
            if len(verified) >= limit:
                break

            url = candidate.url
            if not url or not url.startswith(("http://", "https://")):
                continue

            if not self._check_availability(url):
                continue

            if not self._check_reputable_domain(url, candidate.source):
                continue

            if self.browserless_key:
                snippet = self._fetch_preview_safe(url)
                if snippet:
                    candidate.description = snippet

            verified.append(
                {
                    "title": candidate.title,
                    "url": url,
                    "description": candidate.description,
                    "format": candidate.medium or "article",
                    "source": candidate.source or urllib.parse.urlparse(url).netloc,
                }
            )

        return verified

    # ------------------------------------------------------------------ #
    # Perplexity integration
    # ------------------------------------------------------------------ #

    def _build_query_text(
        self,
        query_terms: Iterable[str],
        preferred_media: Optional[Iterable[str]],
        limit: int,
    ) -> str:
        terms = [term for term in query_terms if term]
        query_focus = ", ".join(terms) if terms else "youth civic engagement"
        media_hint = ""
        if preferred_media:
            pref = ", ".join(preferred_media)
            media_hint = f" Prioritize media types: {pref}. Include at least one short video from a reputable channel (PBS, TED, National Geographic, major news organizations, non-profits)."
        return (
            f"You are a research assistant for middle-school social studies. "
            f"Find up to {limit} recent, reputable sources about {query_focus}.{media_hint} "
            "Return a JSON array of objects with keys: "
            "`title`, `url`, `description`, `medium` (article, video, audio, interactive, guide), "
            "`source` (publisher). Only include reliable outlets suitable for classroom use."
        )

    def _ask_perplexity(self, query_text: str) -> List[ResourceCandidate]:
        payload = {
            "model": "sonar-pro",
            "messages": [
                {
                    "role": "system",
                    "content": "Respond only with valid JSON as instructed. Each item must have title, url, description, medium, and source.",
                },
                {"role": "user", "content": query_text},
            ],
            "temperature": 0.2,
        }
        headers = {
            "Authorization": f"Bearer {self.perplexity_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        resp = self._client.post(
            "https://api.perplexity.ai/chat/completions",
            headers=headers,
            json=payload,
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
        return self._parse_candidates(content)

    def _parse_candidates(self, content: str) -> List[ResourceCandidate]:
        content_stripped = content.strip()
        try:
            data = json.loads(content_stripped)
        except json.JSONDecodeError:
            match = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", content_stripped, re.DOTALL)
            if match:
                try:
                    data = json.loads(match.group(1))
                except json.JSONDecodeError:
                    logger.warning("Failed to parse Perplexity content: %s", content)
                    return []
            else:
                logger.warning("Failed to parse Perplexity content: %s", content)
                return []

        candidates: List[ResourceCandidate] = []
        for item in data:
            try:
                candidates.append(
                    ResourceCandidate(
                        title=item.get("title", "").strip(),
                        url=item.get("url", "").strip(),
                        description=item.get("description", "").strip(),
                        medium=(item.get("medium") or "article").strip().lower(),
                        source=(item.get("source") or "").strip(),
                    )
                )
            except Exception as exc:  # pragma: no cover
                logger.debug("Skipping malformed candidate %s: %s", item, exc)
        return candidates

    # ------------------------------------------------------------------ #
    # Validation helpers
    # ------------------------------------------------------------------ #

    def _check_availability(self, url: str) -> bool:
        try:
            resp = self._client.head(url, follow_redirects=True)
            if 200 <= resp.status_code < 400:
                return True
            if resp.status_code == 405:
                resp = self._client.get(url, follow_redirects=True, headers={"Range": "bytes=0-512"})
                return 200 <= resp.status_code < 400
        except Exception as exc:  # pragma: no cover
            logger.debug("Availability check failed for %s: %s", url, exc)
        return False

    def _check_reputable_domain(self, url: str, source: Optional[str]) -> bool:
        domain = urllib.parse.urlparse(url).netloc.lower()
        domain = domain.split(":")[0]
        if domain.startswith("www."):
            domain = domain[4:]

        trusted_suffixes = (".org", ".edu", ".gov")
        trusted_domains = {
            "npr.org",
            "pbs.org",
            "nationalgeographic.com",
            "smithsonianmag.com",
            "icivics.org",
            "unicef.org",
            "who.int",
            "ed.gov",
            "edweek.org",
            "abcnews.go.com",
            "sandyhookpromise.org",
            "whitehouse.gov",
            "whitehouse.archives.gov",
            "everytownresearch.org",
            "k12ssdb.org",
            "adcouncil.org",
            "gca.org",
            "thisisplaneted.org",
            "nature.org",
            "climateforhealth.org",
            "circle.tufts.edu",
            "giffords.org",
            "studentsdemandaction.org",
            "marchforourlives.com",
            "wusf.org",
            "savethesound.org",
        }

        if "youtube.com" in domain or "youtu.be" in domain:
            parsed = urllib.parse.urlparse(url)
            qs = urllib.parse.parse_qs(parsed.query)
            allowed_channels = {
                "PBSNewsHour",
                "PBS",
                "TED",
                "NationalGeographic",
                "SmithsonianChannel",
                "NPR",
                "edutopia",
                "ProPublica",
                "guardian",
                "UNICEF",
            }
            channel = None
            if "ab_channel" in qs:
                channel = qs["ab_channel"][0]
            elif "channel" in qs:
                channel = qs["channel"][0]
            if channel and channel.replace("+", "") in {c.replace("+", "") for c in allowed_channels}:
                return True
            if source and source.strip() in {
                "PBS NewsHour",
                "PBS",
                "TED",
                "TEDx Talks",
                "National Geographic",
                "Smithsonian Channel",
                "NPR",
                "BBC News",
                "Guardian News",
                "UNICEF",
            }:
                return True
            return False

        if domain in trusted_domains or domain.endswith(trusted_suffixes):
            return True

        # Light-weight GDELT check: ensure the domain appears in the summary page.
        try:
            resp = self._client.get(
                "https://api.gdeltproject.org/api/v2/summary/summary",
                params={"QUERY": domain},
            )
            if resp.status_code == 200 and domain in resp.text.lower():
                return True
        except Exception as exc:  # pragma: no cover
            logger.debug("GDELT check failed for %s: %s", domain, exc)

        return False

    def _fetch_preview_safe(self, url: str) -> Optional[str]:
        if not self.browserless_key:
            return None
        try:
            resp = self._client.post(
                f"https://chrome.browserless.io/content?token={self.browserless_key}",
                json={
                    "url": url,
                    "gotoOptions": {"waitUntil": "networkidle0"},
                    "elements": [{"selector": "article"}],
                    "context": {"body": {"removeScripts": True}},
                },
            )
            resp.raise_for_status()
            payload = resp.json()
            if isinstance(payload, dict) and "data" in payload:
                text = " ".join(payload.get("data", []))
                return text.strip()[:500]
        except Exception as exc:  # pragma: no cover
            logger.debug("Browserless fetch failed for %s: %s", url, exc)
        return None


RESOURCE_FINDER = ResourceFinder()

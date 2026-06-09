"""LLM-based classifier — deep enrichment via API.

Optional module. Only runs when an API key is configured.
Wraps any OpenAI-compatible endpoint (OpenAI, local Ollama, LiteLLM, etc.)
"""

from __future__ import annotations
import json
import logging
from typing import Optional

from . import BaseClassifier, ClassificationResult

logger = logging.getLogger("bis.classifier.llm")

# System prompt for lead enrichment
SYSTEM_PROMPT = """You are a lead intelligence analyst for a tattoo studio in Edmonton, Alberta.
Given a social media post, analyze the person's intent and return a JSON object with these fields:

{
  "intent_summary": "1-2 sentence summary of what this person wants",
  "booking_likelihood": <int 0-100>,
  "project_size": "small | medium | large | multi-session",
  "tone": "excited | nervous | frustrated | urgent | casual | serious",
  "urgency": "low | medium | high | immediate",
  "style_interest": "detected tattoo style(s)",
  "outreach_angle": "suggested approach for reaching out naturally",
  "reason_codes": ["list", "of", "signal", "codes"]
}

Be concise. Focus on actionable intelligence. The studio specializes in realism, black and grey, and coverups in Edmonton."""


class LLMClassifier(BaseClassifier):
    """LLM-based deep classifier. Requires httpx and an API endpoint."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        api_base: str = "https://api.openai.com/v1",
        model: str = "gpt-4o-mini",
    ):
        self._api_key = api_key
        self._api_base = api_base.rstrip("/")
        self._model = model

    @property
    def name(self) -> str:
        return "llm_classifier"

    @property
    def available(self) -> bool:
        return self._api_key is not None and len(self._api_key) > 0

    def classify(self, title: str, body: str, metadata: dict) -> ClassificationResult:
        if not self.available:
            logger.debug("LLM classifier unavailable (no API key)")
            return ClassificationResult()

        try:
            import httpx
        except ImportError:
            logger.warning("httpx not available for LLM classifier")
            return ClassificationResult()

        text = f"Title: {title}\n\nBody: {body}"
        if metadata.get("subreddit"):
            text += f"\n\nSubreddit: r/{metadata['subreddit']}"
        if metadata.get("geo_estimate"):
            text += f"\nLocation signal: {metadata['geo_estimate']}"

        try:
            resp = httpx.post(
                f"{self._api_base}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self._model,
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": text},
                    ],
                    "temperature": 0.3,
                    "max_tokens": 500,
                    "response_format": {"type": "json_object"},
                },
                timeout=30.0,
            )
            resp.raise_for_status()
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            parsed = json.loads(content)

            return ClassificationResult(
                intent_summary=parsed.get("intent_summary", ""),
                booking_likelihood=int(parsed.get("booking_likelihood", 0)),
                project_size=parsed.get("project_size", ""),
                tone=parsed.get("tone", ""),
                urgency=parsed.get("urgency", ""),
                style_interest=parsed.get("style_interest", ""),
                outreach_angle=parsed.get("outreach_angle", ""),
                reason_codes=parsed.get("reason_codes", []),
                confidence=0.9,
            )
        except Exception as e:
            logger.error(f"LLM classification failed: {e}")
            return ClassificationResult()

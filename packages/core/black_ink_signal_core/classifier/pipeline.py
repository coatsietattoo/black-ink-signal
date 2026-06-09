"""Classification pipeline — orchestrates multiple classifiers and merges results."""

from __future__ import annotations
import logging
from typing import Optional

from . import BaseClassifier, ClassificationResult
from .rule_classifier import RuleClassifier
from .llm_classifier import LLMClassifier

logger = logging.getLogger("bis.classifier.pipeline")


class ClassifierPipeline:
    """Runs classifiers in priority order and merges results.

    Architecture:
    1. Rule classifier always runs (fast, no deps)
    2. LLM classifier runs if available and result needs enrichment
    3. Results merge: LLM takes priority where it has data, rule fills gaps
    """

    def __init__(self, llm_api_key: Optional[str] = None, llm_api_base: str = "https://api.openai.com/v1", llm_model: str = "gpt-4o-mini"):
        self._rule = RuleClassifier()
        self._llm = LLMClassifier(api_key=llm_api_key, api_base=llm_api_base, model=llm_model)

    def classify(self, title: str, body: str, metadata: dict | None = None) -> ClassificationResult:
        """Run classification pipeline and return merged result."""
        metadata = metadata or {}

        # Always run rules
        rule_result = self._rule.classify(title, body, metadata)
        logger.debug(f"Rule classifier: confidence={rule_result.confidence:.2f}")

        # Try LLM if available
        if self._llm.available:
            llm_result = self._llm.classify(title, body, metadata)
            if llm_result.confidence > 0:
                logger.debug(f"LLM classifier: confidence={llm_result.confidence:.2f}")
                return self._merge(rule_result, llm_result)

        return rule_result

    def _merge(self, rule: ClassificationResult, llm: ClassificationResult) -> ClassificationResult:
        """Merge results — LLM takes priority where it has values."""
        return ClassificationResult(
            intent_summary=llm.intent_summary or rule.intent_summary,
            booking_likelihood=llm.booking_likelihood if llm.booking_likelihood > 0 else rule.booking_likelihood,
            project_size=llm.project_size or rule.project_size,
            tone=llm.tone or rule.tone,
            urgency=llm.urgency or rule.urgency,
            style_interest=llm.style_interest or rule.style_interest,
            outreach_angle=llm.outreach_angle or rule.outreach_angle,
            reason_codes=list(set(rule.reason_codes + llm.reason_codes)),
            confidence=max(rule.confidence, llm.confidence),
        )

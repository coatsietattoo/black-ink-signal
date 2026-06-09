"""AI Classification Layer for Black Ink Signal.

Provides lead enrichment through:
1. Rule-based fast classification (always available, no external deps)
2. LLM-based deep enrichment (optional, requires API key)

Architecture:
- ClassifierPipeline orchestrates multiple classifiers
- Each classifier implements a common interface
- Results are merged and stored on the lead
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ClassificationResult:
    """Output of the AI classification layer."""
    intent_summary: str = ""
    booking_likelihood: int = 0  # 0-100
    project_size: str = ""  # small | medium | large | multi-session
    tone: str = ""  # excited | nervous | frustrated | urgent | casual | serious
    urgency: str = ""  # low | medium | high | immediate
    style_interest: str = ""  # realism | traditional | neo-trad | geometric | fine-line | japanese | etc
    outreach_angle: str = ""  # suggested approach
    reason_codes: list[str] = field(default_factory=list)
    confidence: float = 0.0  # 0.0-1.0


class BaseClassifier(ABC):
    """Interface for classification modules."""

    @abstractmethod
    def classify(self, title: str, body: str, metadata: dict) -> ClassificationResult:
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        ...

"""Rule-based classifier — fast, no external dependencies.

Provides instant classification using pattern matching and heuristics.
Always available as the baseline even without LLM access.
"""

from __future__ import annotations
import re
from . import BaseClassifier, ClassificationResult


class RuleClassifier(BaseClassifier):
    """Deterministic rule-based lead classifier."""

    @property
    def name(self) -> str:
        return "rule_classifier"

    def classify(self, title: str, body: str, metadata: dict) -> ClassificationResult:
        text = f"{title} {body}".lower()
        result = ClassificationResult()
        reasons: list[str] = []

        # --- Intent Summary ---
        result.intent_summary = self._detect_intent(text, reasons)

        # --- Booking Likelihood ---
        result.booking_likelihood = self._estimate_booking(text, metadata, reasons)

        # --- Project Size ---
        result.project_size = self._estimate_size(text, reasons)

        # --- Tone ---
        result.tone = self._detect_tone(text, reasons)

        # --- Urgency ---
        result.urgency = self._detect_urgency(text, reasons)

        # --- Style Interest ---
        result.style_interest = self._detect_style(text)

        # --- Outreach Angle ---
        result.outreach_angle = self._suggest_outreach(text, result)

        result.reason_codes = reasons
        result.confidence = min(len(reasons) * 0.15, 0.85)  # rule-based caps at 0.85

        return result

    def _detect_intent(self, text: str, reasons: list[str]) -> str:
        # Priority order matters — check most specific patterns first
        if any(p in text for p in ["memorial", "tribute", "in memory", "lost my", "passed away"]):
            reasons.append("memorial_piece")
            return "Planning memorial/tribute tattoo"
        if any(p in text for p in ["cover up", "coverup", "cover-up"]):
            reasons.append("coverup_need")
            return "Looking for coverup work on existing tattoo"
        if any(p in text for p in ["looking for artist", "recommend", "who does", "anyone know"]):
            reasons.append("seeking_artist")
            return "Actively seeking a tattoo artist"
        if "first tattoo" in text:
            reasons.append("first_timer")
            return "Planning first tattoo, seeking guidance"
        if any(p in text for p in ["sleeve", "back piece", "chest piece", "leg sleeve"]):
            reasons.append("large_project")
            return "Planning a large multi-session project"
        if any(p in text for p in ["heal", "touch up", "patchy", "faded"]):
            reasons.append("touchup_need")
            return "Needs touchup or repair work"
        if any(p in text for p in ["quote", "how much", "cost", "price"]):
            reasons.append("pricing_inquiry")
            return "Inquiring about pricing/quotes"
        return "General tattoo interest"

    def _estimate_booking(self, text: str, metadata: dict, reasons: list[str]) -> int:
        score = 30  # base

        # Strong booking signals
        if any(p in text for p in ["looking for artist", "recommend", "book", "appointment"]):
            score += 25
            reasons.append("active_search")
        if any(p in text for p in ["asap", "this week", "soon", "urgent", "walk in", "walk-in"]):
            score += 20
            reasons.append("time_pressure")
        if any(p in text for p in ["budget", "money isn't", "price doesn't matter", "willing to pay", "price does not matter"]):
            score += 15
            reasons.append("budget_ready")
        if any(p in text for p in ["memorial", "tribute", "in memory", "lost my", "passed away"]):
            score += 15
            reasons.append("memorial_emotional")
        if any(p in text for p in ["edmonton", "yeg", "st albert", "sherwood park"]):
            score += 10
            reasons.append("local_match")

        # Negative signals
        if any(p in text for p in ["just got", "just finished", "so happy", "healed"]):
            score -= 30
            reasons.append("already_done")
        if any(p in text for p in ["meme", "lol", "😂", "funny"]):
            score -= 25
            reasons.append("meme_content")
        if any(p in text for p in ["aftercare", "healing", "saniderm", "aquaphor"]):
            if "touch up" not in text and "patchy" not in text:
                score -= 15
                reasons.append("aftercare_only")

        return max(min(score, 95), 5)

    def _estimate_size(self, text: str, reasons: list[str]) -> str:
        if any(p in text for p in ["full sleeve", "full back", "back piece", "leg sleeve", "multiple sessions", "multi session"]):
            reasons.append("multi_session_indicators")
            return "multi-session"
        if any(p in text for p in ["half sleeve", "chest piece", "thigh", "large"]):
            reasons.append("large_piece")
            return "large"
        if any(p in text for p in ["small", "tiny", "minimalist", "finger", "wrist", "ankle"]):
            reasons.append("small_piece")
            return "small"
        return "medium"

    def _detect_tone(self, text: str, reasons: list[str]) -> str:
        if any(p in text for p in ["nervous", "scared", "anxious", "worried"]):
            return "nervous"
        if any(p in text for p in ["unhappy", "regret", "hate", "terrible", "bad", "frustrated"]):
            reasons.append("negative_experience")
            return "frustrated"
        if any(p in text for p in ["excited", "can't wait", "finally", "stoked", "pumped"]):
            return "excited"
        if any(p in text for p in ["asap", "urgent", "need it", "important"]):
            return "urgent"
        if any(p in text for p in ["memorial", "tribute", "lost", "passed away"]):
            reasons.append("emotional_context")
            return "serious"
        return "casual"

    def _detect_urgency(self, text: str, reasons: list[str]) -> str:
        if any(p in text for p in ["asap", "today", "tomorrow", "this week", "urgent", "cancellation"]):
            return "immediate"
        if any(p in text for p in ["soon", "next month", "coming up", "before"]):
            return "high"
        if any(p in text for p in ["thinking about", "planning", "considering", "eventually"]):
            return "low"
        return "medium"

    def _detect_style(self, text: str) -> str:
        styles = {
            "realism": ["realism", "realistic", "portrait", "photorealistic", "hyper realistic"],
            "black_and_grey": ["black and grey", "black and gray", "b&g"],
            "traditional": ["traditional", "old school", "americana"],
            "neo_traditional": ["neo trad", "neo-trad", "neo traditional", "neo-traditional"],
            "japanese": ["japanese", "irezumi", "oriental"],
            "geometric": ["geometric", "geo", "sacred geometry", "mandala"],
            "fine_line": ["fine line", "fineline", "delicate", "minimalist"],
            "illustrative": ["illustrative", "illustration", "dark illustrative"],
            "watercolor": ["watercolor", "water color", "painterly"],
            "dotwork": ["dotwork", "dot work", "stipple"],
            "script": ["script", "lettering", "quote", "text", "calligraphy"],
            "floral": ["flower", "floral", "botanical", "rose"],
        }
        detected: list[str] = []
        for style, keywords in styles.items():
            if any(k in text for k in keywords):
                detected.append(style)
        return ", ".join(detected) if detected else "unspecified"

    def _suggest_outreach(self, text: str, result: ClassificationResult) -> str:
        if "memorial_piece" in result.reason_codes or "memorial_emotional" in result.reason_codes:
            return "Lead with empathy, emphasize care and attention to meaningful pieces, share similar memorial/portrait work"
        if "coverup_need" in result.reason_codes or "negative_experience" in result.reason_codes:
            return "Empathize with frustration, share portfolio of successful coverups, offer free consultation"
        if "first_timer" in result.reason_codes:
            return "Be welcoming and reassuring, share first-timer FAQ, emphasize consultation process"
        if "time_pressure" in result.reason_codes:
            return "Highlight availability, respond quickly, mention cancellation openings"
        if "large_project" in result.reason_codes or "multi_session_indicators" in result.reason_codes:
            return "Share large project portfolio, discuss planning process, emphasize commitment to quality over speed"
        if "budget_ready" in result.reason_codes:
            return "Share premium portfolio work, emphasize quality and custom design process"
        return "Share relevant portfolio work, invite to consultation"

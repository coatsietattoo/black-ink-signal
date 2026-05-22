"""Notification manager for Black Ink Signal.

Sends desktop system notifications for hot leads.
Also provides in-app notification events via the API.
"""

from __future__ import annotations
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session

from .models import Lead, LeadEvent

logger = logging.getLogger("bis.notifications")

# Notification threshold
HOT_LEAD_THRESHOLD = int(os.environ.get("BIS_HOT_LEAD_THRESHOLD", "80"))

# Cooldown: don't re-notify for the same lead within N minutes
COOLDOWN_MINUTES = int(os.environ.get("BIS_NOTIFICATION_COOLDOWN", "30"))

# In-app notification queue file (read by frontend via API)
_NOTIFY_DIR = Path(__file__).resolve().parents[3] / "data" / "notifications"


def _ensure_notify_dir():
    _NOTIFY_DIR.mkdir(parents=True, exist_ok=True)


def _send_desktop_notification(title: str, body: str, urgency: str = "normal"):
    """Send a native desktop notification.

    Uses notify-send on Linux, osascript on macOS.
    Fails silently if not available (e.g., headless server).
    """
    import platform
    import subprocess

    system = platform.system()
    try:
        if system == "Linux":
            subprocess.run(
                ["notify-send", f"🔥 {title}", body, f"--urgency={urgency}", "--app-name=Black Ink Signal"],
                timeout=5,
                capture_output=True,
            )
        elif system == "Darwin":
            script = f'display notification "{body}" with title "🔥 {title}" subtitle "Black Ink Signal"'
            subprocess.run(["osascript", "-e", script], timeout=5, capture_output=True)
        elif system == "Windows":
            # Windows toast via PowerShell (basic)
            ps = f"""
            [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] > $null
            $template = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02)
            $textNodes = $template.GetElementsByTagName("text")
            $textNodes.Item(0).AppendChild($template.CreateTextNode("{title}")) > $null
            $textNodes.Item(1).AppendChild($template.CreateTextNode("{body}")) > $null
            $toast = [Windows.UI.Notifications.ToastNotification]::new($template)
            [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("Black Ink Signal").Show($toast)
            """
            subprocess.run(["powershell", "-Command", ps], timeout=10, capture_output=True)
        else:
            logger.debug(f"No desktop notification support for {system}")
    except Exception as e:
        logger.debug(f"Desktop notification failed (non-critical): {e}")


def check_and_notify(db_session: Session, lead: Lead) -> bool:
    """Check if a lead should trigger a notification and send it.

    Returns True if notification was sent.
    """
    if lead.lead_score < HOT_LEAD_THRESHOLD:
        return False

    if lead.hidden or lead.lead_status == "dismissed":
        return False

    # Check cooldown — look for recent notification events
    recent = (
        db_session.query(LeadEvent)
        .filter(
            LeadEvent.lead_id == lead.id,
            LeadEvent.event_type == "notification_sent",
        )
        .order_by(LeadEvent.created_at.desc())
        .first()
    )

    if recent and recent.created_at:
        elapsed = (datetime.now(timezone.utc) - recent.created_at.replace(tzinfo=timezone.utc)).total_seconds()
        if elapsed < COOLDOWN_MINUTES * 60:
            return False

    # Build notification
    title = f"Hot Lead [{lead.lead_score}]"
    geo_str = f" — {lead.geo_estimate}" if lead.geo_estimate else ""
    body_text = f"{lead.title or 'New lead'}{geo_str}"
    if lead.semantic_label:
        body_text += f"\n{lead.semantic_label.replace('_', ' ').title()}"

    # Send desktop notification
    _send_desktop_notification(title, body_text, urgency="critical")

    # Write in-app notification event
    _write_inapp_notification(lead)

    # Record in DB
    db_session.add(LeadEvent(
        lead_id=lead.id,
        event_type="notification_sent",
        payload_json={"score": lead.lead_score, "channel": "desktop"},
    ))
    db_session.commit()

    logger.info(f"🔥 Notification sent for lead {lead.id} (score {lead.lead_score}): {lead.title}")
    return True


def _write_inapp_notification(lead: Lead):
    """Write a notification file for the in-app feed."""
    _ensure_notify_dir()
    notif = {
        "id": lead.id,
        "score": lead.lead_score,
        "title": lead.title,
        "geo": lead.geo_estimate,
        "label": lead.semantic_label,
        "url": lead.canonical_url,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    path = _NOTIFY_DIR / f"hot_{lead.id}_{int(datetime.now(timezone.utc).timestamp())}.json"
    path.write_text(json.dumps(notif))


def get_recent_notifications(limit: int = 20) -> list[dict]:
    """Read recent in-app notifications from disk."""
    _ensure_notify_dir()
    files = sorted(_NOTIFY_DIR.glob("hot_*.json"), reverse=True)[:limit]
    results = []
    for f in files:
        try:
            results.append(json.loads(f.read_text()))
        except Exception:
            continue
    return results


def notify_hot_leads(db_session: Session, min_score: int | None = None):
    """Scan for hot leads and notify. Called by scheduler after ingestion."""
    threshold = min_score or HOT_LEAD_THRESHOLD
    leads = (
        db_session.query(Lead)
        .filter(
            Lead.lead_score >= threshold,
            Lead.hidden == False,
            Lead.lead_status.in_(["new", "reviewing"]),
        )
        .order_by(Lead.lead_score.desc())
        .all()
    )

    sent = 0
    for lead in leads:
        if check_and_notify(db_session, lead):
            sent += 1

    if sent > 0:
        logger.info(f"Sent {sent} hot lead notifications")
    return sent

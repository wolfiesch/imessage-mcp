#!/usr/bin/env python3
"""
iMessage Follow-up Notifier

Sends Discord notifications for messages needing follow-up.
Designed to run via macOS LaunchAgent on login/wake.

Features:
- Rate limiting to prevent spam (min 4 hours between notifications)
- Smart filtering (only notifies if actionable items exist)
- Rich Discord embeds with categorized follow-ups
- State persistence to track what's been notified
"""

import os
import sys
import json
import logging
import hashlib
import urllib.request
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.messages_interface import MessagesInterface

# Configuration
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")
STATE_FILE = PROJECT_ROOT / "data" / "notifier_state.json"
LOG_FILE = PROJECT_ROOT / "logs" / "notifier.log"
MIN_NOTIFICATION_INTERVAL_HOURS = 4
LOOKBACK_DAYS = 7
STALE_THRESHOLD_DAYS = 3

# Ensure directories exist
STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


def load_state() -> Dict[str, Any]:
    """Load persistent state from disk."""
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception as e:
            logger.warning(f"Failed to load state: {e}")
    return {}


def save_state(state: Dict[str, Any]) -> None:
    """Save persistent state to disk."""
    try:
        STATE_FILE.write_text(json.dumps(state, indent=2, default=str))
    except Exception as e:
        logger.error(f"Failed to save state: {e}")


def get_content_hash(data: Dict) -> str:
    """Generate hash of notification content for deduplication."""
    # Hash the summary counts - if these change, it's new info
    summary = data.get("summary", {})
    content = f"{summary.get('unanswered_questions', 0)}:{summary.get('pending_promises', 0)}:{summary.get('stale_conversations', 0)}"
    return hashlib.md5(content.encode()).hexdigest()[:8]


def should_notify(state: Dict, current_data: Dict) -> tuple[bool, str]:
    """
    Determine if we should send a notification.

    Returns:
        (should_notify: bool, reason: str)
    """
    summary = current_data.get("summary", {})
    total_items = summary.get("total_action_items", 0)

    # No items = no notification
    if total_items == 0:
        return False, "No action items"

    # Check time since last notification
    last_notified = state.get("last_notified")
    if last_notified:
        last_time = datetime.fromisoformat(last_notified)
        hours_since = (datetime.now() - last_time).total_seconds() / 3600

        if hours_since < MIN_NOTIFICATION_INTERVAL_HOURS:
            # Check if content changed significantly
            current_hash = get_content_hash(current_data)
            last_hash = state.get("last_content_hash", "")

            if current_hash == last_hash:
                return False, f"Rate limited ({hours_since:.1f}h since last, same content)"
            else:
                # Content changed - allow notification even if recent
                return True, "Content changed since last notification"

    return True, "Time threshold passed or first notification"


def format_discord_embed(data: Dict) -> Dict:
    """Format follow-up data as a Discord embed."""
    summary = data.get("summary", {})
    total = summary.get("total_action_items", 0)

    # Color based on urgency (orange for moderate, red for high)
    color = 0xFF6B35 if total < 10 else 0xFF0000

    fields = []

    # Add summary fields
    if summary.get("unanswered_questions", 0) > 0:
        fields.append({
            "name": "❓ Unanswered Questions",
            "value": str(summary["unanswered_questions"]),
            "inline": True
        })

    if summary.get("pending_promises", 0) > 0:
        fields.append({
            "name": "🤝 Promises Made",
            "value": str(summary["pending_promises"]),
            "inline": True
        })

    if summary.get("waiting_on_them", 0) > 0:
        fields.append({
            "name": "⏳ Waiting On",
            "value": str(summary["waiting_on_them"]),
            "inline": True
        })

    if summary.get("stale_conversations", 0) > 0:
        fields.append({
            "name": "💤 Stale Convos",
            "value": str(summary["stale_conversations"]),
            "inline": True
        })

    if summary.get("time_sensitive", 0) > 0:
        fields.append({
            "name": "⏰ Time Sensitive",
            "value": str(summary["time_sensitive"]),
            "inline": True
        })

    # Add top examples
    examples = []

    # Most urgent unanswered question
    if data.get("unanswered_questions"):
        q = data["unanswered_questions"][0]
        phone = q["phone"][-4:] if len(q["phone"]) > 4 else q["phone"]
        examples.append(f"**Question from ...{phone}** ({q['days_ago']}d ago)")

    # Oldest stale conversation
    if data.get("stale_conversations"):
        s = sorted(data["stale_conversations"], key=lambda x: x["days_since_reply"], reverse=True)[0]
        phone = s["phone"][-4:] if len(s["phone"]) > 4 else s["phone"]
        examples.append(f"**No reply to ...{phone}** ({s['days_since_reply']}d)")

    if examples:
        fields.append({
            "name": "📌 Top Priority",
            "value": "\n".join(examples[:3]),
            "inline": False
        })

    embed = {
        "title": f"📱 {total} iMessage Follow-ups",
        "description": f"Messages from the last {LOOKBACK_DAYS} days needing attention",
        "color": color,
        "fields": fields,
        "footer": {
            "text": f"Run 'detect_follow_up_needed' in Claude for details"
        },
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    }

    return embed


def send_discord_notification(embed: Dict) -> bool:
    """Send notification to Discord webhook."""
    if not DISCORD_WEBHOOK_URL:
        logger.error("Missing DISCORD_WEBHOOK_URL environment variable")
        return False

    payload = {
        "embeds": [embed]
    }

    data = json.dumps(payload).encode('utf-8')

    req = urllib.request.Request(
        DISCORD_WEBHOOK_URL,
        data=data,
        headers={
            'Content-Type': 'application/json',
            'User-Agent': 'iMessage-MCP-Notifier/1.0'
        }
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            if response.status in (200, 204):
                logger.info("Discord notification sent successfully")
                return True
            else:
                logger.error(f"Discord returned status {response.status}")
                return False
    except Exception as e:
        logger.error(f"Failed to send Discord notification: {e}")
        return False


def main():
    """Main entry point."""
    logger.info("=" * 50)
    logger.info("iMessage Follow-up Notifier starting")
    logger.info(f"Timestamp: {datetime.now().isoformat()}")

    # Load state
    state = load_state()
    logger.info(f"Loaded state: last_notified={state.get('last_notified', 'never')}")

    # Initialize messages interface
    try:
        messages = MessagesInterface()
    except Exception as e:
        logger.error(f"Failed to initialize MessagesInterface: {e}")
        return 1

    # Get follow-up data
    logger.info(f"Checking for follow-ups (last {LOOKBACK_DAYS} days)...")
    try:
        follow_ups = messages.detect_follow_up_needed(
            days=LOOKBACK_DAYS,
            min_stale_days=STALE_THRESHOLD_DAYS,
            limit=50
        )
    except Exception as e:
        logger.error(f"Failed to detect follow-ups: {e}")
        return 1

    if follow_ups.get("error"):
        logger.error(f"Error from detect_follow_up_needed: {follow_ups['error']}")
        return 1

    summary = follow_ups.get("summary", {})
    total = summary.get("total_action_items", 0)
    logger.info(f"Found {total} action items")

    # Check if we should notify
    should_send, reason = should_notify(state, follow_ups)
    logger.info(f"Should notify: {should_send} ({reason})")

    if not should_send:
        logger.info("Skipping notification")
        return 0

    # Format and send notification
    embed = format_discord_embed(follow_ups)
    success = send_discord_notification(embed)

    if success:
        # Update state
        state["last_notified"] = datetime.now().isoformat()
        state["last_content_hash"] = get_content_hash(follow_ups)
        state["last_total_items"] = total
        save_state(state)
        logger.info("State updated")

    logger.info("Notifier finished")
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())

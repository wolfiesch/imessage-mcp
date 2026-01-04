#!/usr/bin/env python3
"""
iMessage Gateway Client - Standalone CLI for iMessage operations.

No MCP server required. Queries Messages.db directly and uses
the imessage-mcp library for contact resolution and message parsing.

Usage:
    python3 gateway/imessage_client.py search "Angus" --limit 20
    python3 gateway/imessage_client.py messages "John" --limit 20
    python3 gateway/imessage_client.py recent --limit 10
    python3 gateway/imessage_client.py unread
    python3 gateway/imessage_client.py send "John" "Running late!"
    python3 gateway/imessage_client.py contacts
    python3 gateway/imessage_client.py analytics "Sarah" --days 30
"""

import sys
import argparse
import json
from pathlib import Path

# Add parent directory to path for imports
SCRIPT_DIR = Path(__file__).parent
REPO_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(REPO_ROOT))

try:
    from src.messages_interface import MessagesInterface
    from src.contacts_manager import ContactsManager
except ImportError as e:
    print(f"Error: Could not import modules: {e}")
    print(f"Make sure you're running from the imessage-mcp repository root")
    print(f"Expected path: {REPO_ROOT}")
    sys.exit(1)

# Default config path (relative to repo root)
CONTACTS_CONFIG = REPO_ROOT / "config" / "contacts.json"


def get_interfaces():
    """Initialize MessagesInterface and ContactsManager."""
    mi = MessagesInterface()
    cm = ContactsManager(str(CONTACTS_CONFIG))
    return mi, cm


def resolve_contact(cm: ContactsManager, name: str):
    """Resolve contact name to Contact object using fuzzy matching."""
    contact = cm.get_contact_by_name(name)
    # get_contact_by_name already does partial matching
    if contact and contact.name.lower() != name.lower():
        print(f"Matched '{name}' to '{contact.name}'", file=sys.stderr)
    return contact


def cmd_search(args):
    """Search messages with a contact."""
    mi, cm = get_interfaces()
    contact = resolve_contact(cm, args.contact)

    if not contact:
        print(f"Contact '{args.contact}' not found.", file=sys.stderr)
        print("Available contacts:", ", ".join(c.name for c in cm.contacts[:10]), file=sys.stderr)
        return 1

    # Use efficient database-level search when query provided
    if args.query:
        messages = mi.search_messages(query=args.query, phone=contact.phone, limit=args.limit)
    else:
        messages = mi.get_messages_by_phone(contact.phone, limit=args.limit)

    print(f"Messages with {contact.name} ({contact.phone}):")
    print("-" * 60)

    for m in messages:
        sender = "Me" if m.get('is_from_me') else contact.name
        text = m.get('text', '[media/attachment]') or '[media/attachment]'
        timestamp = m.get('timestamp', '')
        print(f"{timestamp} | {sender}: {text[:200]}")

    return 0


def cmd_messages(args):
    """Get messages with a specific contact."""
    mi, cm = get_interfaces()
    contact = resolve_contact(cm, args.contact)

    if not contact:
        print(f"Contact '{args.contact}' not found.", file=sys.stderr)
        return 1

    messages = mi.get_messages_by_phone(contact.phone, limit=args.limit)

    if args.json:
        print(json.dumps(messages, indent=2, default=str))
    else:
        for m in messages:
            sender = "Me" if m.get('is_from_me') else contact.name
            text = m.get('text', '[media]') or '[media]'
            print(f"{sender}: {text[:200]}")

    return 0


def cmd_recent(args):
    """Get recent conversations across all contacts."""
    mi, _ = get_interfaces()

    conversations = mi.get_all_recent_conversations(limit=args.limit)

    if args.json:
        print(json.dumps(conversations, indent=2, default=str))
    else:
        print("Recent Conversations:")
        print("-" * 60)
        for conv in conversations:
            handle = conv.get('handle_id', 'Unknown')
            last_msg = conv.get('last_message', '')[:80]
            timestamp = conv.get('last_message_date', '')
            print(f"{handle}: {last_msg} ({timestamp})")

    return 0


def cmd_unread(args):
    """Get unread messages."""
    mi, _ = get_interfaces()

    messages = mi.get_unread_messages(limit=args.limit)

    if args.json:
        print(json.dumps(messages, indent=2, default=str))
    else:
        if not messages:
            print("No unread messages.")
            return 0

        print(f"Unread Messages ({len(messages)}):")
        print("-" * 60)
        for m in messages:
            sender = m.get('sender', 'Unknown')
            text = m.get('text', '[media]') or '[media]'
            print(f"{sender}: {text[:150]}")

    return 0


def cmd_send(args):
    """Send a message to a contact."""
    mi, cm = get_interfaces()
    contact = resolve_contact(cm, args.contact)

    if not contact:
        print(f"Contact '{args.contact}' not found.", file=sys.stderr)
        return 1

    message = " ".join(args.message)

    print(f"Sending to {contact.name} ({contact.phone}): {message[:50]}...", file=sys.stderr)
    result = mi.send_message(contact.phone, message)

    if result.get('success'):
        print("Message sent successfully.", file=sys.stderr)
        return 0
    else:
        print(f"Failed to send: {result.get('error', 'Unknown error')}", file=sys.stderr)
        return 1


def cmd_contacts(args):
    """List all contacts."""
    _, cm = get_interfaces()

    if args.json:
        print(json.dumps([c.to_dict() for c in cm.contacts], indent=2))
    else:
        print(f"Contacts ({len(cm.contacts)}):")
        print("-" * 40)
        for c in cm.contacts:
            print(f"{c.name}: {c.phone}")

    return 0


def cmd_analytics(args):
    """Get conversation analytics for a contact."""
    mi, cm = get_interfaces()

    if args.contact:
        contact = resolve_contact(cm, args.contact)
        if not contact:
            print(f"Contact '{args.contact}' not found.", file=sys.stderr)
            return 1
        analytics = mi.get_conversation_analytics(contact.phone, days=args.days)
    else:
        analytics = mi.get_conversation_analytics(days=args.days)

    if args.json:
        print(json.dumps(analytics, indent=2, default=str))
    else:
        print("Conversation Analytics:")
        print("-" * 40)
        for key, value in analytics.items():
            print(f"{key}: {value}")

    return 0


def cmd_followup(args):
    """Detect messages needing follow-up."""
    mi, cm = get_interfaces()

    followups = mi.detect_follow_up_needed(days=args.days, min_stale_days=args.stale)

    if args.json:
        print(json.dumps(followups, indent=2, default=str))
    else:
        # Check if there are any action items
        summary = followups.get("summary", {})
        total_items = summary.get("total_action_items", 0) if summary else 0

        # Also count items across categories if no summary
        if not total_items:
            for key, items in followups.items():
                if key not in ("summary", "analysis_period_days") and isinstance(items, list):
                    total_items += len(items)

        if not total_items:
            print("No follow-ups needed.")
            return 0

        print("Follow-ups Needed:")
        print("-" * 60)

        # Iterate through categories (skip metadata keys)
        for category, items in followups.items():
            if category in ("summary", "analysis_period_days"):
                continue
            if not items or not isinstance(items, list):
                continue

            print(f"\n--- {category.replace('_', ' ').title()} ---")
            for item in items:
                phone = item.get('phone')
                contact = cm.get_contact_by_phone(phone) if phone else None
                name = contact.name if contact else phone or "Unknown"
                text = item.get('text') or item.get('last_message', '')
                date = item.get('date', '')
                print(f"  {name}: {text[:100]} ({date})")

    return 0


def main():
    parser = argparse.ArgumentParser(
        description="iMessage Gateway - Standalone CLI for iMessage operations",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s search "Angus" --query "SF"     Search messages with Angus containing "SF"
  %(prog)s messages "John" --limit 10      Get last 10 messages with John
  %(prog)s recent                          Show recent conversations
  %(prog)s unread                          Show unread messages
  %(prog)s send "John" "Running late!"     Send message to John
  %(prog)s contacts                        List all contacts
  %(prog)s followup --days 7               Find messages needing follow-up
        """
    )

    subparsers = parser.add_subparsers(dest='command', help='Command to run')

    # search command
    p_search = subparsers.add_parser('search', help='Search messages with a contact')
    p_search.add_argument('contact', help='Contact name (fuzzy matched)')
    p_search.add_argument('--query', '-q', help='Text to search for in messages')
    p_search.add_argument('--limit', '-l', type=int, default=30, help='Max messages to return')
    p_search.set_defaults(func=cmd_search)

    # messages command
    p_messages = subparsers.add_parser('messages', help='Get messages with a contact')
    p_messages.add_argument('contact', help='Contact name')
    p_messages.add_argument('--limit', '-l', type=int, default=20, help='Max messages')
    p_messages.add_argument('--json', action='store_true', help='Output as JSON')
    p_messages.set_defaults(func=cmd_messages)

    # recent command
    p_recent = subparsers.add_parser('recent', help='Get recent conversations')
    p_recent.add_argument('--limit', '-l', type=int, default=10, help='Max conversations')
    p_recent.add_argument('--json', action='store_true', help='Output as JSON')
    p_recent.set_defaults(func=cmd_recent)

    # unread command
    p_unread = subparsers.add_parser('unread', help='Get unread messages')
    p_unread.add_argument('--limit', '-l', type=int, default=20, help='Max messages')
    p_unread.add_argument('--json', action='store_true', help='Output as JSON')
    p_unread.set_defaults(func=cmd_unread)

    # send command
    p_send = subparsers.add_parser('send', help='Send a message')
    p_send.add_argument('contact', help='Contact name')
    p_send.add_argument('message', nargs='+', help='Message to send')
    p_send.set_defaults(func=cmd_send)

    # contacts command
    p_contacts = subparsers.add_parser('contacts', help='List all contacts')
    p_contacts.add_argument('--json', action='store_true', help='Output as JSON')
    p_contacts.set_defaults(func=cmd_contacts)

    # analytics command
    p_analytics = subparsers.add_parser('analytics', help='Get conversation analytics')
    p_analytics.add_argument('contact', nargs='?', help='Contact name (optional)')
    p_analytics.add_argument('--days', '-d', type=int, default=30, help='Days to analyze')
    p_analytics.add_argument('--json', action='store_true', help='Output as JSON')
    p_analytics.set_defaults(func=cmd_analytics)

    # followup command
    p_followup = subparsers.add_parser('followup', help='Detect messages needing follow-up')
    p_followup.add_argument('--days', '-d', type=int, default=7, help='Days to look back')
    p_followup.add_argument('--stale', '-s', type=int, default=2, help='Min stale days')
    p_followup.add_argument('--json', action='store_true', help='Output as JSON')
    p_followup.set_defaults(func=cmd_followup)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    return args.func(args)


if __name__ == '__main__':
    sys.exit(main())

# ============================================================================
# CHANGELOG (recent first, max 5 entries)
# 01/03/2026 - Extracted from server.py during MCP refactoring (Claude)
# ============================================================================
"""
Analytics Handlers

Handles tools for message analysis and insights:
- get_reactions: Get reactions/tapbacks from messages
- get_conversation_analytics: Get analytics about messaging patterns
- get_conversation_for_summary: Get conversation data for AI summarization
- detect_follow_up_needed: Smart reminders for conversations needing attention
"""

import logging
from mcp import types

from utils.validation import validate_positive_int, validate_limit
from utils.responses import text_response

logger = logging.getLogger(__name__)


async def handle_get_reactions(
    arguments: dict,
    messages,
    contacts
) -> list[types.TextContent]:
    """
    Handle get_reactions tool call (T0 Feature).

    Args:
        arguments: {"contact_name": Optional[str], "limit": Optional[int]}
        messages: MessagesInterface instance
        contacts: ContactsManager instance

    Returns:
        Reactions/tapbacks from messages
    """
    contact_name = arguments.get("contact_name")

    # Validate limit
    limit, error = validate_limit(arguments, default=100)
    if error:
        return text_response(f"Validation error: {error}")

    # If contact_name provided, look up phone
    phone_filter = None
    if contact_name:
        contact = contacts.get_contact_by_name(contact_name)
        if not contact:
            return text_response(f"Contact '{contact_name}' not found")
        phone_filter = contact.phone

    # Get reactions
    reactions = messages.get_reactions(phone=phone_filter, limit=limit)

    if not reactions:
        filter_text = f" with {contact_name}" if contact_name else ""
        return text_response(f"No reactions found{filter_text}.")

    # Format response
    filter_text = f" with {contact_name}" if contact_name else ""
    response_lines = [
        f"Reactions{filter_text} ({len(reactions)} found):",
        ""
    ]

    for r in reactions:
        reactor = r.get("reactor_handle", "unknown")
        if r.get("is_from_me"):
            reactor = "You"
        else:
            contact = contacts.get_contact_by_phone(reactor)
            if contact:
                reactor = contact.name

        reaction_type = r.get("reaction_type", "reacted")
        date = r["date"][:10] if r["date"] else "Unknown"
        original_text = r.get("original_text", "[message]")[:60]

        response_lines.append(f"{reaction_type} by {reactor} ({date})")
        response_lines.append(f"   On: \"{original_text}...\"" if len(original_text) == 60 else f"   On: \"{original_text}\"")
        response_lines.append("")

    return text_response("\n".join(response_lines))


async def handle_get_conversation_analytics(
    arguments: dict,
    messages,
    contacts
) -> list[types.TextContent]:
    """
    Handle get_conversation_analytics tool call (T0 Feature).

    Args:
        arguments: {"contact_name": Optional[str], "days": Optional[int]}
        messages: MessagesInterface instance
        contacts: ContactsManager instance

    Returns:
        Analytics about messaging patterns
    """
    contact_name = arguments.get("contact_name")
    days = arguments.get("days", 30)

    # Validate days
    if days:
        validated, error = validate_positive_int(days, "days", min_val=1, max_val=365)
        if error:
            return text_response(f"Validation error: {error}")
        days = validated

    # If contact_name provided, look up phone
    phone_filter = None
    if contact_name:
        contact = contacts.get_contact_by_name(contact_name)
        if not contact:
            return text_response(f"Contact '{contact_name}' not found")
        phone_filter = contact.phone

    # Get analytics
    analytics = messages.get_conversation_analytics(phone=phone_filter, days=days)

    if analytics.get("error"):
        return text_response(f"Error: {analytics['error']}")

    # Format response
    filter_text = f" with {contact_name}" if contact_name else ""
    response_lines = [
        f"Conversation Analytics{filter_text} (last {days} days):",
        "",
        f"📊 Message Stats:",
        f"   Total: {analytics.get('total_messages', 0)}",
        f"   Sent: {analytics.get('sent', 0)}",
        f"   Received: {analytics.get('received', 0)}",
        f"   Ratio: {analytics.get('sent_received_ratio', 0):.2f}",
        "",
        f"📈 Activity:",
        f"   Avg/day: {analytics.get('avg_messages_per_day', 0):.1f}",
        f"   Busiest day: {analytics.get('busiest_day', 'N/A')}",
        f"   Busiest hour: {analytics.get('busiest_hour', 'N/A')}",
    ]

    if analytics.get("top_contacts"):
        response_lines.append("")
        response_lines.append("👥 Top Contacts:")
        for tc in analytics["top_contacts"][:5]:
            contact = contacts.get_contact_by_phone(tc["phone"])
            name = contact.name if contact else tc["phone"][:15]
            response_lines.append(f"   {name}: {tc['count']} messages")

    if analytics.get("response_time_avg"):
        response_lines.append("")
        response_lines.append(f"⏱️ Avg Response Time: {analytics['response_time_avg']}")

    return text_response("\n".join(response_lines))


async def handle_get_conversation_for_summary(
    arguments: dict,
    messages,
    contacts
) -> list[types.TextContent]:
    """
    Handle get_conversation_for_summary tool call (T2 Feature).

    Returns conversation data formatted for AI summarization.

    Args:
        arguments: {"contact_name": str, "days": Optional[int], "limit": Optional[int]}
        messages: MessagesInterface instance
        contacts: ContactsManager instance

    Returns:
        Formatted conversation for summarization
    """
    contact_name = arguments.get("contact_name")
    days = arguments.get("days")
    limit = arguments.get("limit", 200)

    if not contact_name:
        return text_response("Error: contact_name is required")

    # Look up contact
    contact = contacts.get_contact_by_name(contact_name)
    if not contact:
        return text_response(
            f"Contact '{contact_name}' not found. "
            f"Run 'python3 scripts/sync_contacts.py' to sync contacts."
        )

    # Get conversation data
    result = messages.get_conversation_for_summary(
        phone=contact.phone,
        days=days,
        limit=limit
    )

    if result.get("error"):
        return text_response(f"Error: {result['error']}")

    if result.get("message_count", 0) == 0:
        return text_response(
            f"No messages found with {contact.name} in the specified time range."
        )

    # Format response
    response_lines = [
        f"Conversation with {contact.name} ready for summarization:",
        "",
        "📊 Stats:",
        f"   Messages: {result['message_count']} ({result['key_stats']['sent']} sent, {result['key_stats']['received']} received)",
        f"   Avg length: {result['key_stats']['avg_message_length']} chars",
        f"   Date range: {result['date_range']['start'][:10]} to {result['date_range']['end'][:10]}",
        f"   Last interaction: {result['last_interaction'][:10]}",
    ]

    if result.get("recent_topics"):
        response_lines.append(f"   Topics: {', '.join(result['recent_topics'][:8])}")

    response_lines.extend([
        "",
        "💬 Conversation:",
        result["conversation_text"]
    ])

    return text_response("\n".join(response_lines))


async def handle_detect_follow_up_needed(
    arguments: dict,
    messages,
    contacts
) -> list[types.TextContent]:
    """
    Handle detect_follow_up_needed tool call (T2 Feature).

    Smart reminders - detects conversations needing follow-up.

    Args:
        arguments: {"days": Optional[int], "min_stale_days": Optional[int], "limit": Optional[int]}
        messages: MessagesInterface instance
        contacts: ContactsManager instance

    Returns:
        Follow-up recommendations
    """
    days = arguments.get("days", 7)
    min_stale_days = arguments.get("min_stale_days", 3)
    limit = arguments.get("limit", 50)

    result = messages.detect_follow_up_needed(
        days=days,
        min_stale_days=min_stale_days,
        limit=limit
    )

    if result.get("error"):
        return text_response(f"Error: {result['error']}")

    summary = result.get("summary", {})
    total = summary.get("total_action_items", 0)

    response_lines = [
        f"Follow-up Analysis (last {days} days):",
        "",
        f"📊 Summary: {total} items needing attention",
        f"   • Unanswered questions: {summary.get('unanswered_questions', 0)}",
        f"   • Pending promises: {summary.get('pending_promises', 0)}",
        f"   • Waiting on them: {summary.get('waiting_on_them', 0)}",
        f"   • Stale conversations: {summary.get('stale_conversations', 0)}",
        f"   • Time-sensitive: {summary.get('time_sensitive', 0)}",
        ""
    ]

    def format_phone(phone):
        """Get contact name for phone if available."""
        contact = contacts.get_contact_by_phone(phone)
        return contact.name if contact else phone[:20]

    # Unanswered questions
    if result.get("unanswered_questions"):
        response_lines.append("❓ Unanswered Questions:")
        for item in result["unanswered_questions"][:5]:
            text = item['text']
            display_text = f"\"{text[:80]}...\"" if len(text) > 80 else f"\"{text}\""
            response_lines.append(f"   From {format_phone(item['phone'])} ({item['days_ago']}d ago):")
            response_lines.append(f"   {display_text}")
            response_lines.append("")

    # Pending promises
    if result.get("pending_promises"):
        response_lines.append("🤝 Promises You Made:")
        for item in result["pending_promises"][:5]:
            text = item['text']
            display_text = f"\"{text[:80]}...\"" if len(text) > 80 else f"\"{text}\""
            response_lines.append(f"   To {format_phone(item['phone'])} ({item['days_ago']}d ago):")
            response_lines.append(f"   {display_text}")
            response_lines.append("")

    # Waiting on them
    if result.get("waiting_on_them"):
        response_lines.append("⏳ Waiting On Them:")
        for item in result["waiting_on_them"][:5]:
            text = item['text']
            display_text = f"\"{text[:80]}...\"" if len(text) > 80 else f"\"{text}\""
            response_lines.append(f"   From {format_phone(item['phone'])} ({item['days_waiting']}d waiting):")
            response_lines.append(f"   {display_text}")
            response_lines.append("")

    # Stale conversations
    if result.get("stale_conversations"):
        response_lines.append("💤 Stale Conversations (no reply):")
        for item in result["stale_conversations"][:5]:
            text = item['last_message']
            display_text = f"\"{text[:60]}...\"" if len(text) > 60 else f"\"{text}\""
            response_lines.append(f"   {format_phone(item['phone'])} ({item['days_since_reply']}d ago):")
            response_lines.append(f"   {display_text}")
            response_lines.append("")

    # Time-sensitive
    if result.get("time_sensitive"):
        response_lines.append("⏰ Time-Sensitive Messages:")
        for item in result["time_sensitive"][:5]:
            who = "You" if item["is_from_me"] else format_phone(item["phone"])
            text = item['text']
            display_text = f"\"{text[:80]}...\"" if len(text) > 80 else f"\"{text}\""
            response_lines.append(f"   {who} ({item['days_ago']}d ago):")
            response_lines.append(f"   {display_text}")
            response_lines.append("")

    if total == 0:
        response_lines.append("✅ All caught up! No follow-ups needed.")

    return text_response("\n".join(response_lines))

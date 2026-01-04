# ============================================================================
# CHANGELOG (recent first, max 5 entries)
# 01/03/2026 - Extracted from server.py during MCP refactoring (Claude)
# ============================================================================
"""
Groups Handlers

Handles tools for group chat operations:
- list_group_chats: List group conversations with participant info
- get_group_messages: Get messages from a specific group
"""

import logging
from mcp import types

from utils.validation import (
    validate_non_empty_string,
    validate_limit,
)
from utils.responses import text_response, empty_result

logger = logging.getLogger(__name__)


async def handle_list_group_chats(
    arguments: dict,
    messages,
    contacts
) -> list[types.TextContent]:
    """
    Handle list_group_chats tool call (Sprint 3).

    Args:
        arguments: {"limit": Optional[int]}
        messages: MessagesInterface instance
        contacts: ContactsManager instance

    Returns:
        List of group conversations with participant info
    """
    # Validate limit
    limit, error = validate_limit(arguments, default=50)
    if error:
        return text_response(f"Validation error: {error}")

    # Get group chats
    group_list = messages.list_group_chats(limit)

    if not group_list:
        return text_response(
            "No group chats found.\n\n"
            "Note: Requires Full Disk Access permission.\n"
            "Grant in: System Settings → Privacy & Security → Full Disk Access"
        )

    # Format response
    response_lines = [
        f"Group Chats ({len(group_list)} found):",
        ""
    ]

    for group in group_list:
        # Resolve participant names where possible
        participant_names = []
        for handle in group["participants"]:
            contact = contacts.get_contact_by_phone(handle)
            if contact:
                participant_names.append(contact.name)
            else:
                # Truncate long handles for display
                display_handle = handle[:20] + "..." if len(handle) > 20 else handle
                participant_names.append(display_handle)

        participants_str = ", ".join(participant_names[:5])  # Limit to 5 names
        if len(participant_names) > 5:
            participants_str += f" +{len(participant_names) - 5} more"

        date = group["last_message_date"][:10] if group["last_message_date"] else "Unknown"
        msg_count = group["message_count"]
        display_name = group.get("display_name") or "Unnamed Group"

        response_lines.append(f"📱 {display_name} ({group['participant_count']} people)")
        response_lines.append(f"   Participants: {participants_str}")
        response_lines.append(f"   Last active: {date} | {msg_count} messages")
        response_lines.append(f"   Group ID: {group['group_id']}")
        response_lines.append("")

    response_lines.append("Use get_group_messages with group_id to read messages from a specific group.")

    return text_response("\n".join(response_lines))


async def handle_get_group_messages(
    arguments: dict,
    messages,
    contacts
) -> list[types.TextContent]:
    """
    Handle get_group_messages tool call (Sprint 3).

    Args:
        arguments: {"group_id": Optional[str], "participant": Optional[str], "limit": Optional[int]}
        messages: MessagesInterface instance
        contacts: ContactsManager instance

    Returns:
        Messages from the specified group
    """
    group_id = arguments.get("group_id")
    participant = arguments.get("participant")

    if not group_id and not participant:
        return text_response(
            "Error: Either group_id or participant must be provided.\n\n"
            "Use list_group_chats to get group IDs."
        )

    # Validate limit
    limit, error = validate_limit(arguments, default=50)
    if error:
        return text_response(f"Validation error: {error}")

    # Get group messages
    message_list = messages.get_group_messages(
        group_id=group_id,
        participant=participant,
        limit=limit
    )

    if not message_list:
        identifier = group_id or participant
        return text_response(
            f"No messages found for group: {identifier}\n\n"
            "Check the group ID or participant, or use list_group_chats to see available groups."
        )

    # Get group info for header
    group_info = message_list[0].get("group_info", {}) if message_list else {}
    display_name = group_info.get("display_name") or group_id or "Group"

    # Format response
    response_lines = [
        f"Messages from {display_name} ({len(message_list)} messages):",
        ""
    ]

    for msg in message_list:
        # Resolve sender
        sender = msg.get("sender_handle", "Unknown")
        if msg.get("is_from_me"):
            sender = "You"
        else:
            contact = contacts.get_contact_by_phone(sender)
            if contact:
                sender = contact.name
            else:
                sender = sender[:15] + "..." if len(sender) > 15 else sender

        date = msg["date"][:16] if msg["date"] else "Unknown"
        text = msg["text"][:100] + "..." if len(msg["text"]) > 100 else msg["text"]

        response_lines.append(f"[{date}] {sender}: {text}")

    return text_response("\n".join(response_lines))

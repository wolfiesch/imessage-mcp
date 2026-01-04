# ============================================================================
# CHANGELOG (recent first, max 5 entries)
# 01/03/2026 - Added pagination support (offset param) to get_recent_messages (Claude)
# 01/03/2026 - Extracted from server.py during MCP refactoring (Claude)
# ============================================================================
"""
Reading Handlers

Handles tools for reading messages:
- get_recent_messages: Get messages with specific contact
- get_all_recent_conversations: Get recent messages from all conversations
- search_messages: Search messages by content/keyword
- get_messages_by_phone: Get messages by phone number
- get_attachments: Get attachments (photos, videos, files)
- get_unread_messages: Get unread messages awaiting response
- get_message_thread: Get messages in a reply thread
- extract_links: Extract URLs shared in conversations
- get_voice_messages: Get voice/audio messages
- get_scheduled_messages: Get pending scheduled messages
"""

import logging
from mcp import types

from utils.validation import (
    validate_non_empty_string,
    validate_positive_int,
    validate_limit,
    MAX_MESSAGE_LIMIT,
    MAX_SEARCH_RESULTS,
)
from utils.responses import text_response, contact_not_found, empty_result

logger = logging.getLogger(__name__)


async def handle_get_recent_messages(
    arguments: dict,
    messages,
    contacts
) -> list[types.TextContent]:
    """
    Handle get_recent_messages tool call.

    Args:
        arguments: {
            "contact_name": str,
            "limit": Optional[int],
            "offset": Optional[int]  # For pagination
        }
        messages: MessagesInterface instance
        contacts: ContactsManager instance

    Returns:
        Recent message history or error

    Pagination example:
        Page 1: {"contact_name": "John", "limit": 100, "offset": 0}
        Page 2: {"contact_name": "John", "limit": 100, "offset": 100}
    """
    # Validate contact_name
    contact_name, error = validate_non_empty_string(
        arguments.get("contact_name"), "contact_name"
    )
    if error:
        return text_response(f"Validation error: {error}")

    # Validate limit
    limit, error = validate_limit(arguments, default=20)
    if error:
        return text_response(f"Validation error: {error}")

    # Validate offset (for pagination)
    offset_raw = arguments.get("offset", 0)
    offset, error = validate_positive_int(offset_raw, "offset", min_val=0, max_val=100000)
    if error:
        return text_response(f"Validation error: {error}")
    offset = offset if offset is not None else 0

    # Look up contact
    contact = contacts.get_contact_by_name(contact_name)
    if not contact:
        return contact_not_found(
            contact_name,
            [c.name for c in contacts.list_contacts()]
        )

    # Get messages with pagination
    message_list = messages.get_recent_messages(contact.phone, limit, offset)

    if not message_list:
        if offset > 0:
            return text_response(
                f"No more messages with {contact.name} after offset {offset}."
            )
        return empty_result(
            "messages",
            f" with {contact.name}",
            "Requires Full Disk Access permission."
        )

    # Format response with pagination info
    response_lines = [
        f"Messages with {contact.name} ({len(message_list)} messages, offset={offset}):",
        ""
    ]

    for msg in message_list:
        direction = "You" if msg["is_from_me"] else contact.name
        date = msg["date"][:19] if msg["date"] else "Unknown date"
        text = msg["text"][:100] + "..." if len(msg["text"]) > 100 else msg["text"]

        response_lines.append(f"[{date}] {direction}: {text}")

    # Add pagination hint if we got a full page
    if len(message_list) == limit:
        next_offset = offset + limit
        response_lines.append("")
        response_lines.append(f"[More messages available - use offset={next_offset} for next page]")

    return text_response("\n".join(response_lines))


async def handle_get_all_recent_conversations(
    arguments: dict,
    messages,
    contacts
) -> list[types.TextContent]:
    """
    Handle get_all_recent_conversations tool call.

    Args:
        arguments: {"limit": Optional[int]}
        messages: MessagesInterface instance
        contacts: ContactsManager instance

    Returns:
        Recent messages from ALL conversations
    """
    # Validate limit
    limit, error = validate_limit(arguments, default=20)
    if error:
        return text_response(f"Validation error: {error}")

    # Get all recent messages
    message_list = messages.get_all_recent_messages(limit)

    if not message_list:
        return empty_result(
            "messages",
            "",
            "Requires Full Disk Access permission."
        )

    # Format response with contact name resolution
    response_lines = [
        f"Recent Messages (all conversations, {len(message_list)} messages):",
        ""
    ]

    for msg in message_list:
        # Resolve sender to contact name if possible
        sender = msg.get("sender_handle", "Unknown")
        if msg.get("is_from_me"):
            sender = "You"
        else:
            contact = contacts.get_contact_by_phone(sender)
            if contact:
                sender = contact.name
            else:
                # Truncate long handles
                sender = sender[:20] + "..." if len(sender) > 20 else sender

        date = msg["date"][:16] if msg["date"] else "Unknown"
        text = msg["text"][:80] + "..." if len(msg["text"]) > 80 else msg["text"]

        response_lines.append(f"[{date}] {sender}: {text}")

    return text_response("\n".join(response_lines))


async def handle_search_messages(
    arguments: dict,
    messages,
    contacts
) -> list[types.TextContent]:
    """
    Handle search_messages tool call.

    Args:
        arguments: {"query": str, "contact_name": Optional[str], "limit": Optional[int]}
        messages: MessagesInterface instance
        contacts: ContactsManager instance

    Returns:
        Matching messages or error
    """
    # Validate query
    query, error = validate_non_empty_string(arguments.get("query"), "query")
    if error:
        return text_response(f"Validation error: {error}")

    contact_name = arguments.get("contact_name")

    # Validate limit
    limit, error = validate_limit(arguments, default=50, max_val=MAX_SEARCH_RESULTS)
    if error:
        return text_response(f"Validation error: {error}")

    # If contact_name provided, look up phone
    phone_filter = None
    if contact_name:
        contact = contacts.get_contact_by_name(contact_name)
        if not contact:
            return contact_not_found(
                contact_name,
                [c.name for c in contacts.list_contacts()]
            )
        phone_filter = contact.phone

    # Search messages
    results = messages.search_messages(query, phone=phone_filter, limit=limit)

    if not results:
        filter_text = f" with {contact_name}" if contact_name else ""
        return text_response(
            f"No messages found matching '{query}'{filter_text}."
        )

    # Format response
    filter_text = f" with {contact_name}" if contact_name else ""
    response_lines = [
        f"Search results for '{query}'{filter_text} ({len(results)} matches):",
        ""
    ]

    for msg in results:
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

        date = msg["date"][:10] if msg["date"] else "Unknown"
        text = msg["text"][:100] + "..." if len(msg["text"]) > 100 else msg["text"]

        response_lines.append(f"[{date}] {sender}: {text}")

    return text_response("\n".join(response_lines))


async def handle_get_messages_by_phone(
    arguments: dict,
    messages,
    contacts
) -> list[types.TextContent]:
    """
    Handle get_messages_by_phone tool call.

    Args:
        arguments: {"phone_number": str, "limit": Optional[int]}
        messages: MessagesInterface instance
        contacts: ContactsManager instance

    Returns:
        Recent messages with the phone number
    """
    # Validate phone_number
    phone, error = validate_non_empty_string(
        arguments.get("phone_number"), "phone_number"
    )
    if error:
        return text_response(f"Validation error: {error}")

    # Validate limit
    limit, error = validate_limit(arguments, default=20)
    if error:
        return text_response(f"Validation error: {error}")

    # Normalize phone number
    normalized_phone = (
        phone.strip()
        .replace(" ", "")
        .replace("-", "")
        .replace("(", "")
        .replace(")", "")
    )

    # Get messages
    message_list = messages.get_recent_messages(normalized_phone, limit)

    if not message_list:
        return empty_result(
            "messages",
            f" with {phone}",
            "Check the phone number format or Full Disk Access permission."
        )

    # Try to find contact name for display
    contact = contacts.get_contact_by_phone(normalized_phone)
    display_name = contact.name if contact else phone

    # Format response
    response_lines = [
        f"Recent messages with {display_name} ({len(message_list)} messages):",
        ""
    ]

    for msg in message_list:
        direction = "You" if msg["is_from_me"] else display_name
        date = msg["date"][:19] if msg["date"] else "Unknown date"
        text = msg["text"][:100] + "..." if len(msg["text"]) > 100 else msg["text"]

        response_lines.append(f"[{date}] {direction}: {text}")

    return text_response("\n".join(response_lines))


async def handle_get_attachments(
    arguments: dict,
    messages,
    contacts
) -> list[types.TextContent]:
    """
    Handle get_attachments tool call (T0 Feature).

    Args:
        arguments: {"contact_name": Optional[str], "mime_type": Optional[str], "limit": Optional[int]}
        messages: MessagesInterface instance
        contacts: ContactsManager instance

    Returns:
        Attachments with file paths and metadata
    """
    contact_name = arguments.get("contact_name")
    mime_type = arguments.get("mime_type")

    # Validate limit
    limit, error = validate_limit(arguments, default=50)
    if error:
        return text_response(f"Validation error: {error}")

    # If contact_name provided, look up phone
    phone_filter = None
    if contact_name:
        contact = contacts.get_contact_by_name(contact_name)
        if not contact:
            return contact_not_found(contact_name)
        phone_filter = contact.phone

    # Get attachments
    attachment_list = messages.get_attachments(
        phone=phone_filter,
        mime_type=mime_type,
        limit=limit
    )

    if not attachment_list:
        filter_text = f" from {contact_name}" if contact_name else ""
        type_text = f" of type {mime_type}" if mime_type else ""
        return text_response(f"No attachments found{filter_text}{type_text}.")

    # Format response
    filter_text = f" from {contact_name}" if contact_name else ""
    response_lines = [
        f"Attachments{filter_text} ({len(attachment_list)} found):",
        ""
    ]

    for att in attachment_list:
        sender = att.get("sender_handle", "unknown")
        if att.get("is_from_me"):
            sender = "You"
        else:
            contact = contacts.get_contact_by_phone(sender)
            if contact:
                sender = contact.name

        date = att["date"][:10] if att["date"] else "Unknown"
        mime = att.get("mime_type", "unknown")
        size_kb = (att.get("total_bytes", 0) or 0) / 1024
        filename = att.get("filename", "unnamed")
        path = att.get("attachment_path", "N/A")

        response_lines.append(f"📎 {filename} ({mime})")
        response_lines.append(f"   From: {sender} | Date: {date} | Size: {size_kb:.1f} KB")
        if path:
            response_lines.append(f"   Path: {path}")
        response_lines.append("")

    return text_response("\n".join(response_lines))


async def handle_get_unread_messages(
    arguments: dict,
    messages,
    contacts
) -> list[types.TextContent]:
    """
    Handle get_unread_messages tool call (T0 Feature).

    Args:
        arguments: {"limit": Optional[int]}
        messages: MessagesInterface instance
        contacts: ContactsManager instance

    Returns:
        Unread messages awaiting response
    """
    # Validate limit
    limit, error = validate_limit(arguments, default=50)
    if error:
        return text_response(f"Validation error: {error}")

    # Get unread messages
    unread_list = messages.get_unread_messages(limit)

    if not unread_list:
        return text_response(
            "No unread messages found.\n\n"
            "All caught up!"
        )

    # Format response
    response_lines = [
        f"Unread Messages ({len(unread_list)} awaiting response):",
        ""
    ]

    for msg in unread_list:
        sender = msg.get("sender_handle", "unknown")
        contact = contacts.get_contact_by_phone(sender)
        sender_name = contact.name if contact else sender[:20]

        date = msg["date"][:16] if msg["date"] else "Unknown"
        age_hours = msg.get("age_hours", 0)
        text = msg["text"][:80] + "..." if len(msg["text"]) > 80 else msg["text"]

        age_str = f"{age_hours}h ago" if age_hours < 24 else f"{age_hours // 24}d ago"

        response_lines.append(f"📩 From {sender_name} ({age_str})")
        response_lines.append(f"   \"{text}\"")
        response_lines.append("")

    return text_response("\n".join(response_lines))


async def handle_get_message_thread(
    arguments: dict,
    messages,
    contacts
) -> list[types.TextContent]:
    """
    Handle get_message_thread tool call (T1 Feature).

    Args:
        arguments: {"message_guid": str, "limit": Optional[int]}
        messages: MessagesInterface instance
        contacts: ContactsManager instance

    Returns:
        Messages in the reply thread
    """
    # Validate message_guid
    message_guid, error = validate_non_empty_string(
        arguments.get("message_guid"), "message_guid"
    )
    if error:
        return text_response(f"Validation error: {error}")

    # Validate limit
    limit, error = validate_limit(arguments, default=50)
    if error:
        return text_response(f"Validation error: {error}")

    # Get thread
    thread_messages = messages.get_message_thread(message_guid, limit)

    if not thread_messages:
        return text_response(
            f"No thread found for message GUID: {message_guid}\n\n"
            "The message may not be part of a reply thread, or the GUID is invalid."
        )

    # Format response
    response_lines = [
        f"Reply Thread ({len(thread_messages)} messages):",
        ""
    ]

    for msg in thread_messages:
        sender = msg.get("sender_handle", "unknown")
        if msg.get("is_from_me"):
            sender = "You"
        else:
            contact = contacts.get_contact_by_phone(sender)
            if contact:
                sender = contact.name

        date = msg["date"][:16] if msg["date"] else "Unknown"
        text = msg["text"][:80] + "..." if len(msg["text"]) > 80 else msg["text"]
        indent = "  " if msg.get("is_reply") else ""

        response_lines.append(f"{indent}[{date}] {sender}: {text}")

    return text_response("\n".join(response_lines))


async def handle_extract_links(
    arguments: dict,
    messages,
    contacts
) -> list[types.TextContent]:
    """
    Handle extract_links tool call (T1 Feature).

    Args:
        arguments: {"contact_name": Optional[str], "days": Optional[int], "limit": Optional[int]}
        messages: MessagesInterface instance
        contacts: ContactsManager instance

    Returns:
        URLs shared in conversations
    """
    contact_name = arguments.get("contact_name")
    days = arguments.get("days")

    # Validate limit
    limit, error = validate_limit(arguments, default=100)
    if error:
        return text_response(f"Validation error: {error}")

    # If contact_name provided, look up phone
    phone_filter = None
    if contact_name:
        contact = contacts.get_contact_by_name(contact_name)
        if not contact:
            return contact_not_found(contact_name)
        phone_filter = contact.phone

    # Extract links
    links = messages.extract_links(phone=phone_filter, days=days, limit=limit)

    if not links:
        filter_text = f" with {contact_name}" if contact_name else ""
        return text_response(f"No links found{filter_text}.")

    # Format response
    filter_text = f" with {contact_name}" if contact_name else ""
    response_lines = [
        f"Shared Links{filter_text} ({len(links)} found):",
        ""
    ]

    for link in links:
        sender = link.get("sender_handle", "unknown")
        if link.get("is_from_me"):
            sender = "You"
        else:
            contact = contacts.get_contact_by_phone(sender)
            if contact:
                sender = contact.name

        date = link["date"][:10] if link["date"] else "Unknown"
        url = link.get("url", "N/A")

        response_lines.append(f"🔗 {url}")
        response_lines.append(f"   Shared by {sender} on {date}")
        response_lines.append("")

    return text_response("\n".join(response_lines))


async def handle_get_voice_messages(
    arguments: dict,
    messages,
    contacts
) -> list[types.TextContent]:
    """
    Handle get_voice_messages tool call (T1 Feature).

    Args:
        arguments: {"contact_name": Optional[str], "limit": Optional[int]}
        messages: MessagesInterface instance
        contacts: ContactsManager instance

    Returns:
        Voice messages with file paths
    """
    contact_name = arguments.get("contact_name")

    # Validate limit
    limit, error = validate_limit(arguments, default=50)
    if error:
        return text_response(f"Validation error: {error}")

    # If contact_name provided, look up phone
    phone_filter = None
    if contact_name:
        contact = contacts.get_contact_by_name(contact_name)
        if not contact:
            return contact_not_found(contact_name)
        phone_filter = contact.phone

    # Get voice messages
    voice_list = messages.get_voice_messages(phone=phone_filter, limit=limit)

    if not voice_list:
        filter_text = f" from {contact_name}" if contact_name else ""
        return text_response(f"No voice messages found{filter_text}.")

    # Format response
    filter_text = f" from {contact_name}" if contact_name else ""
    response_lines = [
        f"Voice Messages{filter_text} ({len(voice_list)} found):",
        ""
    ]

    for vm in voice_list:
        sender = vm.get("sender_handle", "unknown")
        if vm.get("is_from_me"):
            sender = "You"
        else:
            contact = contacts.get_contact_by_phone(sender)
            if contact:
                sender = contact.name

        date = vm["date"][:16] if vm["date"] else "Unknown"
        size_kb = (vm.get("size_bytes", 0) or 0) / 1024
        played = "played" if vm.get("is_played") else "unplayed"
        path = vm.get("attachment_path", "N/A")

        response_lines.append(f"🎵 From {sender} ({date})")
        response_lines.append(f"   Size: {size_kb:.1f} KB | Status: {played}")
        if path:
            response_lines.append(f"   Path: {path}")
        response_lines.append("")

    response_lines.append("Tip: Voice message paths can be passed to transcription services.")

    return text_response("\n".join(response_lines))


async def handle_get_scheduled_messages(
    arguments: dict,
    messages,
    contacts
) -> list[types.TextContent]:
    """
    Handle get_scheduled_messages tool call (T1 Feature).

    Args:
        arguments: {} (no arguments needed)
        messages: MessagesInterface instance
        contacts: ContactsManager instance

    Returns:
        Scheduled messages pending send
    """
    # Get scheduled messages
    scheduled_list = messages.get_scheduled_messages()

    if not scheduled_list:
        return text_response("No scheduled messages found.")

    # Format response
    response_lines = [
        f"Scheduled Messages ({len(scheduled_list)} pending):",
        ""
    ]

    for msg in scheduled_list:
        recipient = msg.get("recipient_handle", "unknown")
        contact = contacts.get_contact_by_phone(recipient)
        recipient_name = contact.name if contact else recipient[:20]

        scheduled_date = msg["scheduled_date"][:16] if msg["scheduled_date"] else "Unknown"
        text = msg["text"][:80] + "..." if len(msg["text"]) > 80 else msg["text"]
        state = msg.get("schedule_state", "pending")

        response_lines.append(f"⏰ To {recipient_name}")
        response_lines.append(f"   Scheduled: {scheduled_date}")
        response_lines.append(f"   Status: {state}")
        response_lines.append(f"   \"{text}\"")
        response_lines.append("")

    return text_response("\n".join(response_lines))


async def handle_list_recent_handles(
    arguments: dict,
    messages,
    contacts
) -> list[types.TextContent]:
    """
    Handle list_recent_handles tool call.

    Lists all unique phone numbers/email handles from recent messages.
    Useful for finding temporary numbers or people not in your contacts.

    Args:
        arguments: {"days": Optional[int], "limit": Optional[int]}
        messages: MessagesInterface instance
        contacts: ContactsManager instance

    Returns:
        List of handles with message counts and known/unknown status
    """
    from utils.validation import validate_days

    # Validate days
    days, error = validate_days(arguments, default=30)
    if error:
        return text_response(f"Validation error: {error}")

    # Validate limit
    limit, error = validate_limit(arguments, default=100)
    if error:
        return text_response(f"Validation error: {error}")

    # Get handles
    handle_list = messages.list_recent_handles(days, limit)

    if not handle_list:
        return empty_result(
            "handles",
            f" in the last {days} days",
            "Requires Full Disk Access permission."
        )

    # Categorize handles as known (in contacts) or unknown
    known_handles = []
    unknown_handles = []
    all_contacts = {c.phone: c.name for c in contacts.list_contacts()}

    for h in handle_list:
        handle = h["handle"]
        # Normalize for comparison (strip country code variations)
        normalized = "".join(c for c in handle if c.isdigit())

        # Check if this handle matches any contact
        contact_name = None
        for phone, name in all_contacts.items():
            phone_digits = "".join(c for c in phone if c.isdigit())
            if normalized.endswith(phone_digits[-10:]) or phone_digits.endswith(normalized[-10:]):
                contact_name = name
                break

        entry = {
            **h,
            "contact_name": contact_name,
            "is_known": contact_name is not None
        }

        if contact_name:
            known_handles.append(entry)
        else:
            unknown_handles.append(entry)

    # Format response
    response_lines = [
        f"Recent handles from last {days} days:",
        f"  Known (in contacts): {len(known_handles)}",
        f"  Unknown: {len(unknown_handles)}",
        ""
    ]

    if unknown_handles:
        response_lines.append("📱 UNKNOWN HANDLES (not in contacts):")
        for h in unknown_handles[:20]:  # Show first 20
            date = h["last_message_date"][:10] if h["last_message_date"] else "Unknown"
            response_lines.append(
                f"  {h['handle']} - {h['message_count']} msgs (last: {date})"
            )
        if len(unknown_handles) > 20:
            response_lines.append(f"  ... and {len(unknown_handles) - 20} more")
        response_lines.append("")

    if known_handles:
        response_lines.append("✅ KNOWN HANDLES (in contacts):")
        for h in known_handles[:20]:
            date = h["last_message_date"][:10] if h["last_message_date"] else "Unknown"
            response_lines.append(
                f"  {h['contact_name']} ({h['handle']}) - {h['message_count']} msgs"
            )
        if len(known_handles) > 20:
            response_lines.append(f"  ... and {len(known_handles) - 20} more")

    return text_response("\n".join(response_lines))


async def handle_search_unknown_senders(
    arguments: dict,
    messages,
    contacts
) -> list[types.TextContent]:
    """
    Handle search_unknown_senders tool call (T2 Feature).

    Find messages from phone numbers/emails not in contacts.json.

    Args:
        arguments: {"days": Optional[int], "limit": Optional[int]}
        messages: MessagesInterface instance
        contacts: ContactsManager instance

    Returns:
        Unknown senders with sample messages
    """
    from utils.validation import validate_days, validate_limit

    # Validate parameters
    days, error = validate_days(arguments, default=30)
    if error:
        return text_response(f"Validation error: {error}")

    limit, error = validate_limit(arguments, default=100)
    if error:
        return text_response(f"Validation error: {error}")

    # Get list of all known phone numbers from contacts
    all_contacts = contacts.list_contacts()
    known_phones = [c.phone for c in all_contacts if c.phone]

    # Search for unknown senders
    unknown_senders = messages.search_unknown_senders(
        known_phones=known_phones,
        days=days,
        limit=limit
    )

    if not unknown_senders:
        return text_response(
            f"No unknown senders found in the last {days} days. "
            f"All recent messages are from contacts in your contact list."
        )

    # Format response
    total_messages = sum(s["message_count"] for s in unknown_senders)
    response_lines = [
        f"Unknown Senders (last {days} days):",
        f"  Found {len(unknown_senders)} unknown senders with {total_messages} total messages",
        ""
    ]

    for sender in unknown_senders:
        handle = sender["handle"]
        msg_count = sender["message_count"]
        last_date = sender["last_message_date"][:10] if sender["last_message_date"] else "Unknown"

        response_lines.append(f"📱 {handle}")
        response_lines.append(f"   Messages: {msg_count} | Last: {last_date}")

        # Show sample messages
        if sender["messages"]:
            response_lines.append("   Recent messages:")
            for msg in sender["messages"][:3]:  # Show up to 3 messages
                direction = "→" if msg["is_from_me"] else "←"
                date = msg["date"][:10] if msg["date"] else "?"
                text = msg["text"][:80]
                if len(msg["text"]) > 80:
                    text += "..."
                response_lines.append(f"     {direction} [{date}] {text}")

        response_lines.append("")

    response_lines.append("💡 Tip: Use add_contact to add any of these to your contacts.")

    return text_response("\n".join(response_lines))

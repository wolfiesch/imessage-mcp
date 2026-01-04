# ============================================================================
# CHANGELOG (recent first, max 5 entries)
# 01/03/2026 - Extracted from server.py during MCP refactoring (Claude)
# ============================================================================
"""
Messaging Handlers

Handles tools for sending iMessages:
- send_message: Send to a contact by name
- send_message_by_phone: Send directly to a phone number
"""

import logging
from mcp import types

from utils.validation import validate_non_empty_string
from utils.responses import text_response, contact_not_found

logger = logging.getLogger(__name__)


async def handle_send_message(
    arguments: dict,
    messages,
    contacts
) -> list[types.TextContent]:
    """
    Handle send_message tool call.

    Args:
        arguments: {"contact_name": str, "message": str}
        messages: MessagesInterface instance
        contacts: ContactsManager instance

    Returns:
        Success or error message
    """
    # Validate contact_name
    contact_name, error = validate_non_empty_string(
        arguments.get("contact_name"), "contact_name"
    )
    if error:
        return text_response(f"Validation error: {error}")

    # Validate message
    message, error = validate_non_empty_string(
        arguments.get("message"), "message"
    )
    if error:
        return text_response(f"Validation error: {error}")

    # Look up contact
    contact = contacts.get_contact_by_name(contact_name)
    if not contact:
        return contact_not_found(
            contact_name,
            [c.name for c in contacts.list_contacts()]
        )

    # Send message
    result = messages.send_message(contact.phone, message)

    if result["success"]:
        response = (
            f"✓ Message sent to {contact.name} ({contact.phone})\n\n"
            f"Message: {message}"
        )
        logger.info(f"Message sent successfully to {contact.name}")
    else:
        response = (
            f"✗ Failed to send message to {contact.name}\n\n"
            f"Error: {result['error']}\n\n"
            f"Troubleshooting:\n"
            f"- Ensure Messages.app is running\n"
            f"- Check AppleScript permissions in System Settings\n"
            f"- Verify phone number format: {contact.phone}"
        )
        logger.error(f"Failed to send message: {result['error']}")

    return text_response(response)


async def handle_send_message_by_phone(
    arguments: dict,
    messages
) -> list[types.TextContent]:
    """
    Handle send_message_by_phone tool call - send to arbitrary phone number.

    Args:
        arguments: {"phone_number": str, "message": str}
        messages: MessagesInterface instance

    Returns:
        Success or error message
    """
    # Validate phone_number
    phone, error = validate_non_empty_string(
        arguments.get("phone_number"), "phone_number"
    )
    if error:
        return text_response(f"Validation error: {error}")

    # Validate message
    message, error = validate_non_empty_string(
        arguments.get("message"), "message"
    )
    if error:
        return text_response(f"Validation error: {error}")

    # Normalize phone number (strip formatting)
    normalized_phone = (
        phone.strip()
        .replace(" ", "")
        .replace("-", "")
        .replace("(", "")
        .replace(")", "")
    )

    # Send message directly to phone number
    result = messages.send_message(normalized_phone, message)

    if result["success"]:
        response = (
            f"✓ Message sent to {phone}\n\n"
            f"Message: {message}"
        )
        logger.info(f"Message sent successfully to {phone}")
    else:
        response = (
            f"✗ Failed to send message to {phone}\n\n"
            f"Error: {result['error']}\n\n"
            f"Troubleshooting:\n"
            f"- Ensure Messages.app is running\n"
            f"- Check AppleScript permissions in System Settings\n"
            f"- Verify phone number format is valid"
        )
        logger.error(f"Failed to send message to {phone}: {result['error']}")

    return text_response(response)

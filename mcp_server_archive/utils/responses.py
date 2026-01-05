# ============================================================================
# CHANGELOG (recent first, max 5 entries)
# 01/03/2026 - Created for MCP server refactoring (Claude)
# ============================================================================
"""
Response formatting utilities for MCP tool handlers.

Provides standardized response builders for common scenarios.
"""

from mcp import types
from typing import Optional


def text_response(text: str) -> list[types.TextContent]:
    """Create a simple text response."""
    return [types.TextContent(type="text", text=text)]


def success_response(message: str, details: Optional[str] = None) -> list[types.TextContent]:
    """
    Create a standardized success response.

    Args:
        message: Primary success message
        details: Optional additional details
    """
    text = f"✓ {message}"
    if details:
        text += f"\n\n{details}"
    return [types.TextContent(type="text", text=text)]


def error_response(error: str, prefix: str = "Error") -> list[types.TextContent]:
    """
    Create a standardized error response.

    Args:
        error: Error message
        prefix: Prefix for the error (default: "Error")
    """
    return [types.TextContent(type="text", text=f"{prefix}: {error}")]


def validation_error(error: str) -> list[types.TextContent]:
    """Create a validation error response."""
    return error_response(error, "Validation error")


def contact_not_found(
    contact_name: str,
    available_contacts: Optional[list[str]] = None
) -> list[types.TextContent]:
    """
    Create a 'contact not found' error response.

    Args:
        contact_name: The name that was searched for
        available_contacts: Optional list of available contact names
    """
    message = (
        f"Contact '{contact_name}' not found. "
        f"Please add to config/contacts.json or check spelling."
    )

    if available_contacts:
        message += f" Available contacts: {', '.join(available_contacts)}"

    return [types.TextContent(type="text", text=message)]


def empty_result(
    item_type: str,
    filter_text: str = "",
    hint: Optional[str] = None
) -> list[types.TextContent]:
    """
    Create an empty result response.

    Args:
        item_type: Type of items being searched (e.g., "messages", "contacts")
        filter_text: Additional filter description (e.g., " with this contact")
        hint: Optional helpful hint (e.g., "Requires Full Disk Access permission.")
    """
    message = f"No {item_type} found{filter_text}."
    if hint:
        message += f"\n\nNote: {hint}"
    return [types.TextContent(type="text", text=message)]


def format_message_list(
    messages_data: list[dict],
    contact_name: Optional[str] = None,
    include_header: bool = True
) -> str:
    """
    Format a list of messages for display.

    Args:
        messages_data: List of message dictionaries with date, direction, text
        contact_name: Optional contact name for the header
        include_header: Whether to include a header line
    """
    if not messages_data:
        return "No messages found."

    lines = []

    if include_header:
        if contact_name:
            lines.append(f"Recent messages with {contact_name}:")
        else:
            lines.append("Recent messages:")
        lines.append("")

    for msg in messages_data:
        direction = msg.get("direction", "")
        date = msg.get("date", "")
        text = msg.get("text", "[message content not available]")
        sender = msg.get("sender", "")

        # Handle different formats
        if direction:
            prefix = "→" if direction == "sent" else "←"
        elif sender:
            prefix = f"← {sender}"
        else:
            prefix = ""

        lines.append(f"[{date}] {prefix} {text}")

    return "\n".join(lines)


def format_contact_list(contacts_data: list) -> str:
    """
    Format a list of contacts for display.

    Args:
        contacts_data: List of contact objects or dicts
    """
    if not contacts_data:
        return "No contacts configured."

    lines = ["Configured contacts:", ""]

    for contact in contacts_data:
        name = getattr(contact, "name", contact.get("name", "Unknown"))
        phone = getattr(contact, "phone", contact.get("phone", "Unknown"))
        rel_type = getattr(contact, "relationship_type", contact.get("relationship_type", ""))

        line = f"  • {name}: {phone}"
        if rel_type and rel_type != "other":
            line += f" ({rel_type})"
        lines.append(line)

    return "\n".join(lines)

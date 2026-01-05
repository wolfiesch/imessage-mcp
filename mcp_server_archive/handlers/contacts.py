# ============================================================================
# CHANGELOG (recent first, max 5 entries)
# 01/03/2026 - Extracted from server.py during MCP refactoring (Claude)
# ============================================================================
"""
Contacts Handlers

Handles tools for managing contacts:
- add_contact: Add a new contact to contacts.json
- list_contacts: List all configured contacts
"""

import logging
from mcp import types

from utils.validation import validate_non_empty_string
from utils.responses import text_response

logger = logging.getLogger(__name__)


async def handle_add_contact(
    arguments: dict,
    contacts
) -> list[types.TextContent]:
    """
    Handle add_contact tool call - add a new contact to contacts.json.

    Args:
        arguments: {"name": str, "phone": str, "relationship_type": str (optional), "notes": str (optional)}
        contacts: ContactsManager instance

    Returns:
        Success or error message
    """
    # Validate name
    name, error = validate_non_empty_string(arguments.get("name"), "name")
    if error:
        return text_response(f"Validation error: {error}")

    # Validate phone
    phone, error = validate_non_empty_string(arguments.get("phone"), "phone")
    if error:
        return text_response(f"Validation error: {error}")

    relationship_type = arguments.get("relationship_type", "other")
    notes = arguments.get("notes", "")

    # Normalize phone number
    normalized_phone = (
        phone.strip()
        .replace(" ", "")
        .replace("-", "")
        .replace("(", "")
        .replace(")", "")
    )

    # Check if contact already exists by phone
    existing = contacts.get_contact_by_phone(normalized_phone)
    if existing:
        return text_response(
            f"Contact with phone {phone} already exists: {existing.name}"
        )

    # Check if contact already exists by name (exact match)
    existing_name = contacts.get_contact_by_name(name)
    if existing_name and existing_name.name.lower() == name.lower():
        return text_response(
            f"Contact with name '{name}' already exists with phone: {existing_name.phone}"
        )

    try:
        new_contact = contacts.add_contact(
            name=name,
            phone=normalized_phone,
            relationship_type=relationship_type,
            notes=notes
        )
        response = (
            f"✓ Contact added successfully\n\n"
            f"Name: {new_contact.name}\n"
            f"Phone: {new_contact.phone}\n"
            f"Type: {new_contact.relationship_type}"
        )
        if notes:
            response += f"\nNotes: {notes}"
        logger.info(f"Contact added: {new_contact.name} ({new_contact.phone})")
        return text_response(response)
    except Exception as e:
        logger.error(f"Failed to add contact {name}: {e}")
        return text_response(f"Failed to add contact: {str(e)}")


async def handle_list_contacts(
    arguments: dict,
    contacts
) -> list[types.TextContent]:
    """
    Handle list_contacts tool call.

    Args:
        arguments: {} (no arguments needed)
        contacts: ContactsManager instance

    Returns:
        List of configured contacts
    """
    contact_list = contacts.list_contacts()

    if not contact_list:
        return text_response(
            "No contacts configured.\n\n"
            "To add contacts:\n"
            "1. Edit config/contacts.json directly, or\n"
            "2. Run: python3 scripts/sync_contacts.py to sync from macOS Contacts"
        )

    # Format response
    response_lines = [
        f"Configured Contacts ({len(contact_list)}):",
        ""
    ]

    for contact in contact_list:
        line = f"  • {contact.name}: {contact.phone}"
        if hasattr(contact, 'relationship_type') and contact.relationship_type != "other":
            line += f" ({contact.relationship_type})"
        response_lines.append(line)

    return text_response("\n".join(response_lines))

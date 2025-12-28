#!/usr/bin/env python3
"""
iMessage MCP Server - Personalized messaging with Life Planner integration.

Sprint 1: Basic send/receive messages via MCP
Sprint 2: Contact sync and fuzzy matching
Sprint 3: Style learning and personalization
Sprint 4: Context integration from Life Planner

Usage:
    python mcp_server/server.py
"""

import sys
import json
import logging
from pathlib import Path
from typing import Optional

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp import types

from src.messages_interface import MessagesInterface
from src.contacts_manager import ContactsManager

# Project root directory (for resolving relative paths)
PROJECT_ROOT = Path(__file__).parent.parent

# Configure logging with absolute path
LOG_DIR = PROJECT_ROOT / "logs"
LOG_DIR.mkdir(exist_ok=True)  # Ensure log directory exists

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_DIR / 'mcp_server.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Load configuration
CONFIG_PATH = PROJECT_ROOT / "config" / "mcp_server.json"
with open(CONFIG_PATH) as f:
    CONFIG = json.load(f)


def resolve_path(path_str: str) -> str:
    """Resolve a config path relative to PROJECT_ROOT or expand ~."""
    path = Path(path_str)
    if path_str.startswith("~"):
        return str(path.expanduser())
    elif path.is_absolute():
        return str(path)
    else:
        return str(PROJECT_ROOT / path)


# Initialize server
app = Server(CONFIG["server_name"])

# Initialize components with resolved paths
messages = MessagesInterface(resolve_path(CONFIG["paths"]["messages_db"]))
contacts = ContactsManager(resolve_path(CONFIG["paths"]["contacts_config"]))


@app.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    """
    List available MCP tools.

    Sprint 1 tools:
    - send_message: Send iMessage to a contact
    - get_recent_messages: Retrieve recent message history
    - list_contacts: Show all configured contacts

    Sprint 2.5 tools:
    - get_all_recent_conversations: Get recent messages from ALL conversations
    - search_messages: Search messages by content/keyword
    - get_messages_by_phone: Get messages by phone number (no contact needed)
    """
    return [
        types.Tool(
            name="send_message",
            description=(
                "Send an iMessage to a contact using their name. "
                "The contact must be configured in contacts.json (Sprint 1). "
                "Auto-logs interaction to life planner database if enabled."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "contact_name": {
                        "type": "string",
                        "description": "Name of the contact (exact or partial match)"
                    },
                    "message": {
                        "type": "string",
                        "description": "Message text to send"
                    }
                },
                "required": ["contact_name", "message"]
            }
        ),
        types.Tool(
            name="get_recent_messages",
            description=(
                "Retrieve recent message history with a contact. "
                "Requires Full Disk Access permission for Messages database."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "contact_name": {
                        "type": "string",
                        "description": "Name of the contact"
                    },
                    "limit": {
                        "type": "number",
                        "description": "Number of recent messages to retrieve (default: 20)",
                        "default": 20
                    }
                },
                "required": ["contact_name"]
            }
        ),
        types.Tool(
            name="list_contacts",
            description="List all configured contacts with their phone numbers",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        ),
        types.Tool(
            name="get_all_recent_conversations",
            description=(
                "Get recent messages from ALL conversations, including people not in your contacts. "
                "Shows phone numbers/handles for unknown senders. "
                "Sprint 2.5 enhancement for discovering conversations."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "number",
                        "description": "Number of recent messages to retrieve (default: 20)",
                        "default": 20
                    }
                },
                "required": []
            }
        ),
        types.Tool(
            name="search_messages",
            description=(
                "Search messages by content/keyword across all conversations or filtered by contact. "
                "Returns matching messages with context snippets. "
                "Sprint 2.5 enhancement for finding specific conversations."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query (keyword or phrase)"
                    },
                    "contact_name": {
                        "type": "string",
                        "description": "Optional: Filter search to specific contact"
                    },
                    "limit": {
                        "type": "number",
                        "description": "Maximum number of results (default: 50)",
                        "default": 50
                    }
                },
                "required": ["query"]
            }
        ),
        types.Tool(
            name="get_messages_by_phone",
            description=(
                "Get messages by phone number directly, without needing contact to be configured. "
                "Useful for unknown numbers or people not in your contacts. "
                "Sprint 2.5 enhancement."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "phone_number": {
                        "type": "string",
                        "description": "Phone number or iMessage handle (e.g., +14155551234 or email)"
                    },
                    "limit": {
                        "type": "number",
                        "description": "Number of recent messages to retrieve (default: 20)",
                        "default": 20
                    }
                },
                "required": ["phone_number"]
            }
        )
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    """
    Handle MCP tool calls.

    Args:
        name: Tool name
        arguments: Tool arguments

    Returns:
        List of TextContent responses
    """
    logger.info(f"Tool called: {name} with args: {arguments}")

    try:
        if name == "send_message":
            return await handle_send_message(arguments)
        elif name == "get_recent_messages":
            return await handle_get_recent_messages(arguments)
        elif name == "list_contacts":
            return await handle_list_contacts(arguments)
        elif name == "get_all_recent_conversations":
            return await handle_get_all_recent_conversations(arguments)
        elif name == "search_messages":
            return await handle_search_messages(arguments)
        elif name == "get_messages_by_phone":
            return await handle_get_messages_by_phone(arguments)
        else:
            raise ValueError(f"Unknown tool: {name}")

    except Exception as e:
        logger.error(f"Error executing tool {name}: {e}", exc_info=True)
        return [
            types.TextContent(
                type="text",
                text=f"Error: {str(e)}"
            )
        ]


async def handle_send_message(arguments: dict) -> list[types.TextContent]:
    """
    Handle send_message tool call.

    Args:
        arguments: {"contact_name": str, "message": str}

    Returns:
        Success or error message
    """
    contact_name = arguments["contact_name"]
    message = arguments["message"]

    # Look up contact
    contact = contacts.get_contact_by_name(contact_name)
    if not contact:
        return [
            types.TextContent(
                type="text",
                text=(
                    f"Contact '{contact_name}' not found. "
                    f"Please add to config/contacts.json or check spelling. "
                    f"Available contacts: {', '.join(c.name for c in contacts.list_contacts())}"
                )
            )
        ]

    # Send message
    result = messages.send_message(contact.phone, message)

    if result["success"]:
        response = (
            f"✓ Message sent to {contact.name} ({contact.phone})\n\n"
            f"Message: {message}"
        )
        logger.info(f"Message sent successfully to {contact.name}")

        # TODO Sprint 2: Log interaction to Life Planner database
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

    return [types.TextContent(type="text", text=response)]


async def handle_get_recent_messages(arguments: dict) -> list[types.TextContent]:
    """
    Handle get_recent_messages tool call.

    Args:
        arguments: {"contact_name": str, "limit": Optional[int]}

    Returns:
        Recent message history or error
    """
    contact_name = arguments["contact_name"]
    limit = arguments.get("limit", 20)

    # Look up contact
    contact = contacts.get_contact_by_name(contact_name)
    if not contact:
        return [
            types.TextContent(
                type="text",
                text=f"Contact '{contact_name}' not found"
            )
        ]

    # Get messages
    message_list = messages.get_recent_messages(contact.phone, limit)

    if not message_list:
        return [
            types.TextContent(
                type="text",
                text=(
                    f"No messages found for {contact.name}.\n\n"
                    f"Note: Requires Full Disk Access permission.\n"
                    f"Grant in: System Settings → Privacy & Security → Full Disk Access"
                )
            )
        ]

    # Format response
    response_lines = [
        f"Recent messages with {contact.name} ({contact.phone}):",
        f"(Showing {len(message_list)} most recent)",
        ""
    ]

    for msg in message_list:
        direction = "You" if msg["is_from_me"] else contact.name
        date = msg["date"][:19] if msg["date"] else "Unknown date"
        text = msg["text"][:100] + "..." if len(msg["text"]) > 100 else msg["text"]

        response_lines.append(f"[{date}] {direction}: {text}")

    return [
        types.TextContent(
            type="text",
            text="\n".join(response_lines)
        )
    ]


async def handle_list_contacts(arguments: dict) -> list[types.TextContent]:
    """
    Handle list_contacts tool call.

    Returns:
        List of all configured contacts
    """
    contact_list = contacts.list_contacts()

    if not contact_list:
        return [
            types.TextContent(
                type="text",
                text=(
                    "No contacts configured.\n\n"
                    "Add contacts to: config/contacts.json\n"
                    "Sprint 2 will add auto-sync from macOS Contacts."
                )
            )
        ]

    response_lines = [
        f"Configured Contacts ({len(contact_list)}):",
        ""
    ]

    for contact in contact_list:
        response_lines.append(
            f"• {contact.name} - {contact.phone} ({contact.relationship_type})"
        )
        if contact.notes:
            response_lines.append(f"  Note: {contact.notes}")

    return [
        types.TextContent(
            type="text",
            text="\n".join(response_lines)
        )
    ]


async def handle_get_all_recent_conversations(arguments: dict) -> list[types.TextContent]:
    """
    Handle get_all_recent_conversations tool call (Sprint 2.5).

    Args:
        arguments: {"limit": Optional[int]}

    Returns:
        Recent messages from all conversations
    """
    limit = arguments.get("limit", 20)

    # Get all recent messages
    message_list = messages.get_all_recent_conversations(limit)

    if not message_list:
        return [
            types.TextContent(
                type="text",
                text=(
                    "No messages found.\n\n"
                    "Note: Requires Full Disk Access permission.\n"
                    "Grant in: System Settings → Privacy & Security → Full Disk Access"
                )
            )
        ]

    # Format response
    response_lines = [
        f"Recent Messages (All Conversations):",
        f"(Showing {len(message_list)} most recent)",
        ""
    ]

    for msg in message_list:
        # Try to find contact name
        phone = msg["phone"]
        contact = contacts.get_contact_by_phone(phone)
        contact_name = contact.name if contact else phone

        direction = "You" if msg["is_from_me"] else contact_name
        date = msg["date"][:19] if msg["date"] else "Unknown date"
        text = msg["text"][:80] + "..." if len(msg["text"]) > 80 else msg["text"]

        response_lines.append(f"[{date}] {direction}: {text}")

    return [
        types.TextContent(
            type="text",
            text="\n".join(response_lines)
        )
    ]


async def handle_search_messages(arguments: dict) -> list[types.TextContent]:
    """
    Handle search_messages tool call (Sprint 2.5).

    Args:
        arguments: {"query": str, "contact_name": Optional[str], "limit": Optional[int]}

    Returns:
        Messages matching search query
    """
    query = arguments["query"]
    contact_name = arguments.get("contact_name")
    limit = arguments.get("limit", 50)

    # If contact_name provided, look up phone
    phone_filter = None
    if contact_name:
        contact = contacts.get_contact_by_name(contact_name)
        if not contact:
            return [
                types.TextContent(
                    type="text",
                    text=f"Contact '{contact_name}' not found"
                )
            ]
        phone_filter = contact.phone

    # Search messages
    message_list = messages.search_messages(query, phone=phone_filter, limit=limit)

    if not message_list:
        filter_text = f" with {contact_name}" if contact_name else ""
        return [
            types.TextContent(
                type="text",
                text=f"No messages found matching '{query}'{filter_text}"
            )
        ]

    # Format response
    filter_text = f" with {contact_name}" if contact_name else " (all conversations)"
    response_lines = [
        f"Search Results for '{query}'{filter_text}:",
        f"(Found {len(message_list)} matches)",
        ""
    ]

    for msg in message_list:
        # Try to find contact name
        phone = msg["phone"]
        contact = contacts.get_contact_by_phone(phone)
        contact_name_display = contact.name if contact else phone

        direction = "You" if msg["is_from_me"] else contact_name_display
        date = msg["date"][:10] if msg["date"] else "Unknown"
        snippet = msg.get("match_snippet", msg["text"][:100])

        response_lines.append(f"[{date}] {direction}: {snippet}")
        response_lines.append("")  # Blank line between results

    return [
        types.TextContent(
            type="text",
            text="\n".join(response_lines)
        )
    ]


async def handle_get_messages_by_phone(arguments: dict) -> list[types.TextContent]:
    """
    Handle get_messages_by_phone tool call (Sprint 2.5).

    Args:
        arguments: {"phone_number": str, "limit": Optional[int]}

    Returns:
        Recent messages with this phone number
    """
    phone_number = arguments["phone_number"]
    limit = arguments.get("limit", 20)

    # Get messages
    message_list = messages.get_recent_messages(phone_number, limit)

    if not message_list:
        return [
            types.TextContent(
                type="text",
                text=(
                    f"No messages found for {phone_number}.\n\n"
                    "Note: Requires Full Disk Access permission.\n"
                    "Grant in: System Settings → Privacy & Security → Full Disk Access"
                )
            )
        ]

    # Try to find contact name
    contact = contacts.get_contact_by_phone(phone_number)
    contact_name = contact.name if contact else "Unknown Contact"

    # Format response
    response_lines = [
        f"Recent messages with {phone_number}",
        f"({contact_name})" if contact else "(Not in contacts)",
        f"(Showing {len(message_list)} most recent)",
        ""
    ]

    for msg in message_list:
        direction = "You" if msg["is_from_me"] else contact_name
        date = msg["date"][:19] if msg["date"] else "Unknown date"
        text = msg["text"][:100] + "..." if len(msg["text"]) > 100 else msg["text"]

        response_lines.append(f"[{date}] {direction}: {text}")

    return [
        types.TextContent(
            type="text",
            text="\n".join(response_lines)
        )
    ]


async def main():
    """Run the MCP server."""
    logger.info("Starting iMessage MCP Server...")
    logger.info(f"Server name: {CONFIG['server_name']}")
    logger.info(f"Version: {CONFIG['version']}")

    # Check permissions
    permissions = messages.check_permissions()
    if not permissions["messages_db_accessible"]:
        logger.warning("Messages database not accessible - get_recent_messages will not work")
        logger.warning("Grant Full Disk Access in System Settings")

    # Log loaded contacts
    logger.info(f"Loaded {len(contacts.list_contacts())} contacts")

    # Run server
    async with stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            app.create_initialization_options()
        )


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())

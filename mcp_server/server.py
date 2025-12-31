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

# RAG imports (lazy loaded to avoid startup cost if not using RAG)
_retriever = None
_unified_retriever = None

def get_retriever():
    """Lazy-load the MessageRetriever to avoid startup cost."""
    global _retriever
    if _retriever is None:
        try:
            from src.rag.retriever import MessageRetriever
            _retriever = MessageRetriever(
                persist_directory=str(PROJECT_ROOT / "data" / "chroma"),
                contacts_config=str(PROJECT_ROOT / "config" / "contacts.json"),
            )
            logger.info("RAG retriever initialized")
        except ImportError as e:
            logger.warning(f"RAG dependencies not installed: {e}")
            raise
    return _retriever


def get_unified_retriever():
    """Lazy-load the UnifiedRetriever for multi-source RAG."""
    global _unified_retriever
    if _unified_retriever is None:
        try:
            from src.rag.unified import UnifiedRetriever
            _unified_retriever = UnifiedRetriever(
                persist_directory=str(PROJECT_ROOT / "data" / "chroma"),
            )
            logger.info("Unified RAG retriever initialized")
        except ImportError as e:
            logger.warning(f"Unified RAG dependencies not installed: {e}")
            raise
    return _unified_retriever

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

# Validation constants
MAX_MESSAGE_LIMIT = 500  # Maximum messages to retrieve
MAX_SEARCH_RESULTS = 500  # Maximum search results
MIN_LIMIT = 1  # Minimum limit value


def validate_positive_int(value, name: str, min_val: int = MIN_LIMIT, max_val: int = MAX_MESSAGE_LIMIT) -> tuple[int | None, str | None]:
    """
    Validate that a value is a positive integer within bounds.

    Args:
        value: Value to validate
        name: Parameter name for error messages
        min_val: Minimum allowed value
        max_val: Maximum allowed value

    Returns:
        Tuple of (validated_value, error_message). If valid, error_message is None.
    """
    if value is None:
        return None, None

    try:
        int_value = int(value)
    except (TypeError, ValueError):
        return None, f"Invalid {name}: must be an integer, got {type(value).__name__}"

    if int_value < min_val:
        return None, f"Invalid {name}: must be at least {min_val}, got {int_value}"

    if int_value > max_val:
        return None, f"Invalid {name}: must be at most {max_val}, got {int_value}"

    return int_value, None


def validate_non_empty_string(value, name: str) -> tuple[str | None, str | None]:
    """
    Validate that a value is a non-empty string.

    Args:
        value: Value to validate
        name: Parameter name for error messages

    Returns:
        Tuple of (validated_value, error_message). If valid, error_message is None.
    """
    if value is None:
        return None, f"Missing required parameter: {name}"

    if not isinstance(value, str):
        return None, f"Invalid {name}: must be a string, got {type(value).__name__}"

    stripped = value.strip()
    if not stripped:
        return None, f"Invalid {name}: cannot be empty"

    return stripped, None


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
        ),
        types.Tool(
            name="list_group_chats",
            description=(
                "List all group chat conversations with participant information. "
                "Returns group ID, participants list, participant count, and message count. "
                "Use the group_id from results with get_group_messages to read group messages. "
                "Sprint 3 enhancement for group chat support."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "number",
                        "description": "Maximum number of group chats to return (default: 50)",
                        "default": 50
                    }
                },
                "required": []
            }
        ),
        types.Tool(
            name="get_group_messages",
            description=(
                "Get messages from a specific group chat. "
                "Identify groups by group_id (from list_group_chats) or by participant phone/email. "
                "Returns messages with sender attribution for each message. "
                "Sprint 3 enhancement for group chat support."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "group_id": {
                        "type": "string",
                        "description": "The group identifier (from list_group_chats results)"
                    },
                    "participant": {
                        "type": "string",
                        "description": "Phone/email to filter groups containing this participant (alternative to group_id)"
                    },
                    "limit": {
                        "type": "number",
                        "description": "Maximum number of messages to return (default: 50)",
                        "default": 50
                    }
                },
                "required": []
            }
        ),
        # RAG Tools (Sprint 4)
        types.Tool(
            name="index_messages",
            description=(
                "Index messages for semantic search (RAG). "
                "Creates embeddings of conversation chunks for fast semantic retrieval. "
                "Run this before using ask_messages. Can index a specific contact or recent messages from all contacts. "
                "Use 'all_history=true' to index complete 4-year message history. "
                "Requires OpenAI API key (OPENAI_API_KEY env var) or local embeddings."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "contact_name": {
                        "type": "string",
                        "description": "Optional: Index messages with this specific contact only"
                    },
                    "days": {
                        "type": "number",
                        "description": "Number of days of history to index (default: 30, max: 1460 for ~4 years)",
                        "default": 30
                    },
                    "all_history": {
                        "type": "boolean",
                        "description": "Set to true to index ALL message history (may take several minutes)",
                        "default": False
                    }
                },
                "required": []
            }
        ),
        types.Tool(
            name="ask_messages",
            description=(
                "Semantic search across indexed iMessage conversations. "
                "Uses AI embeddings to find relevant conversations based on meaning, not just keywords. "
                "Example: 'What restaurant did Sarah recommend?' finds discussions about restaurants with Sarah. "
                "Run index_messages first to build the search index."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "description": "Natural language question or search query"
                    },
                    "contact_name": {
                        "type": "string",
                        "description": "Optional: Only search conversations with this contact"
                    },
                    "limit": {
                        "type": "number",
                        "description": "Maximum number of relevant conversations to return (default: 5)",
                        "default": 5
                    }
                },
                "required": ["question"]
            }
        ),
        types.Tool(
            name="rag_stats",
            description=(
                "Get statistics about the indexed message database. "
                "Shows how many conversations are indexed, which contacts, date range, etc."
            ),
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        ),
        # Unified RAG Tools (Multi-Source Knowledge Base)
        types.Tool(
            name="index_knowledge",
            description=(
                "Index content from multiple sources for unified semantic search. "
                "Sources: 'superwhisper' (voice transcriptions), 'notes' (markdown documents), "
                "'gmail' (emails - requires pre-fetched data), 'slack' (messages - requires pre-fetched data), "
                "'calendar' (events - requires pre-fetched data). "
                "Use source='local' to index both SuperWhisper and Notes at once."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "source": {
                        "type": "string",
                        "description": "Source to index: 'superwhisper', 'notes', 'local' (both), 'gmail', 'slack', 'calendar'",
                        "enum": ["superwhisper", "notes", "local", "gmail", "slack", "calendar"]
                    },
                    "days": {
                        "type": "number",
                        "description": "Number of days of history to index (default: 30)",
                        "default": 30
                    },
                    "limit": {
                        "type": "number",
                        "description": "Maximum items to index (default: no limit)"
                    }
                },
                "required": ["source"]
            }
        ),
        types.Tool(
            name="search_knowledge",
            description=(
                "Semantic search across all indexed sources (SuperWhisper, Notes, Gmail, Slack, Calendar). "
                "Finds relevant content based on meaning, not just keywords. "
                "Can filter by specific sources. Run index_knowledge first to build the search index."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Natural language search query"
                    },
                    "sources": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional: Filter to specific sources (e.g., ['superwhisper', 'notes'])"
                    },
                    "days": {
                        "type": "number",
                        "description": "Optional: Only search content from last N days"
                    },
                    "limit": {
                        "type": "number",
                        "description": "Maximum results to return (default: 10)",
                        "default": 10
                    }
                },
                "required": ["query"]
            }
        ),
        types.Tool(
            name="knowledge_stats",
            description=(
                "Get statistics about the unified knowledge base. "
                "Shows indexed content by source, date ranges, and total chunks."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "source": {
                        "type": "string",
                        "description": "Optional: Get stats for specific source only"
                    }
                },
                "required": []
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
        elif name == "list_group_chats":
            return await handle_list_group_chats(arguments)
        elif name == "get_group_messages":
            return await handle_get_group_messages(arguments)
        # RAG tools
        elif name == "index_messages":
            return await handle_index_messages(arguments)
        elif name == "ask_messages":
            return await handle_ask_messages(arguments)
        elif name == "rag_stats":
            return await handle_rag_stats(arguments)
        # Unified RAG tools
        elif name == "index_knowledge":
            return await handle_index_knowledge(arguments)
        elif name == "search_knowledge":
            return await handle_search_knowledge(arguments)
        elif name == "knowledge_stats":
            return await handle_knowledge_stats(arguments)
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
    # Validate contact_name
    contact_name, error = validate_non_empty_string(arguments.get("contact_name"), "contact_name")
    if error:
        return [types.TextContent(type="text", text=f"Validation error: {error}")]

    # Validate message
    message, error = validate_non_empty_string(arguments.get("message"), "message")
    if error:
        return [types.TextContent(type="text", text=f"Validation error: {error}")]

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
    # Validate contact_name
    contact_name, error = validate_non_empty_string(arguments.get("contact_name"), "contact_name")
    if error:
        return [types.TextContent(type="text", text=f"Validation error: {error}")]

    # Validate limit
    limit_raw = arguments.get("limit", 20)
    limit, error = validate_positive_int(limit_raw, "limit", max_val=MAX_MESSAGE_LIMIT)
    if error:
        return [types.TextContent(type="text", text=f"Validation error: {error}")]
    if limit is None:
        limit = 20

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
    # Validate limit
    limit_raw = arguments.get("limit", 20)
    limit, error = validate_positive_int(limit_raw, "limit", max_val=MAX_MESSAGE_LIMIT)
    if error:
        return [types.TextContent(type="text", text=f"Validation error: {error}")]
    if limit is None:
        limit = 20

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
        # Check if this is a group chat
        is_group = msg.get("is_group_chat", False)

        if is_group:
            # For group chats, show sender and group indicator
            sender_handle = msg.get("sender_handle", msg["phone"])
            if msg["is_from_me"]:
                sender_name = "You"
            else:
                sender_contact = contacts.get_contact_by_phone(sender_handle)
                sender_name = sender_contact.name if sender_contact else sender_handle[:15]

            direction = f"[GROUP] {sender_name}"
        else:
            # For 1:1 chats, use existing logic
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
    # Validate query
    query, error = validate_non_empty_string(arguments.get("query"), "query")
    if error:
        return [types.TextContent(type="text", text=f"Validation error: {error}")]

    contact_name = arguments.get("contact_name")

    # Validate limit
    limit_raw = arguments.get("limit", 50)
    limit, error = validate_positive_int(limit_raw, "limit", max_val=MAX_SEARCH_RESULTS)
    if error:
        return [types.TextContent(type="text", text=f"Validation error: {error}")]
    if limit is None:
        limit = 50

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
        # Check if this is a group chat
        is_group = msg.get("is_group_chat", False)

        if is_group:
            # For group chats, show sender and group indicator
            phone = msg["phone"]
            if msg["is_from_me"]:
                sender_name = "You"
            else:
                sender_contact = contacts.get_contact_by_phone(phone)
                sender_name = sender_contact.name if sender_contact else phone[:15]
            direction = f"[GROUP] {sender_name}"
        else:
            # For 1:1 chats, use existing logic
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
    # Validate phone_number
    phone_number, error = validate_non_empty_string(arguments.get("phone_number"), "phone_number")
    if error:
        return [types.TextContent(type="text", text=f"Validation error: {error}")]

    # Validate limit
    limit_raw = arguments.get("limit", 20)
    limit, error = validate_positive_int(limit_raw, "limit", max_val=MAX_MESSAGE_LIMIT)
    if error:
        return [types.TextContent(type="text", text=f"Validation error: {error}")]
    if limit is None:
        limit = 20

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


async def handle_list_group_chats(arguments: dict) -> list[types.TextContent]:
    """
    Handle list_group_chats tool call (Sprint 3).

    Args:
        arguments: {"limit": Optional[int]}

    Returns:
        List of group conversations with participant info
    """
    # Validate limit
    limit_raw = arguments.get("limit", 50)
    limit, error = validate_positive_int(limit_raw, "limit", max_val=MAX_MESSAGE_LIMIT)
    if error:
        return [types.TextContent(type="text", text=f"Validation error: {error}")]
    if limit is None:
        limit = 50

    # Get group chats
    group_list = messages.list_group_chats(limit)

    if not group_list:
        return [
            types.TextContent(
                type="text",
                text=(
                    "No group chats found.\n\n"
                    "Note: Requires Full Disk Access permission.\n"
                    "Grant in: System Settings → Privacy & Security → Full Disk Access"
                )
            )
        ]

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

    return [
        types.TextContent(
            type="text",
            text="\n".join(response_lines)
        )
    ]


async def handle_index_messages(arguments: dict) -> list[types.TextContent]:
    """
    Handle index_messages tool call (RAG Sprint 4).

    Indexes messages for semantic search.

    Args:
        arguments: {"contact_name": Optional[str], "days": Optional[int], "all_history": Optional[bool]}

    Returns:
        Status message about indexing
    """
    contact_name = arguments.get("contact_name")
    all_history = arguments.get("all_history", False)

    # Validate days (allow up to 1460 = 4 years)
    days_raw = arguments.get("days", 30)
    days, error = validate_positive_int(days_raw, "days", min_val=1, max_val=1460)
    if error:
        return [types.TextContent(type="text", text=f"Validation error: {error}")]
    if days is None:
        days = 30

    try:
        retriever = get_retriever()

        # Full history indexing
        if all_history and not contact_name:
            chunks_added = retriever.index_all_history()

            stats = retriever.get_stats()
            contacts_indexed = stats.get("contacts", [])

            return [
                types.TextContent(
                    type="text",
                    text=(
                        f"✓ Indexed COMPLETE message history\n\n"
                        f"• {chunks_added} new conversation chunks created\n"
                        f"• Total chunks: {stats.get('chunk_count', 0)}\n"
                        f"• Contacts indexed: {len(contacts_indexed)}\n"
                        f"• Date range: ALL TIME\n\n"
                        f"You can now use ask_messages to search these conversations."
                    )
                )
            ]

        if contact_name:
            # Index specific contact
            contact = contacts.get_contact_by_name(contact_name)
            if not contact:
                return [
                    types.TextContent(
                        type="text",
                        text=(
                            f"Contact '{contact_name}' not found. "
                            f"Available contacts: {', '.join(c.name for c in contacts.list_contacts()[:5])}..."
                        )
                    )
                ]

            chunks_added = retriever.index_contact(contact.name, days=days)

            return [
                types.TextContent(
                    type="text",
                    text=(
                        f"✓ Indexed messages with {contact.name}\n\n"
                        f"• {chunks_added} conversation chunks created\n"
                        f"• Date range: last {days} days\n\n"
                        f"You can now use ask_messages to search these conversations."
                    )
                )
            ]
        else:
            # Index all recent messages
            chunks_added = retriever.index_recent_messages(days=days)

            stats = retriever.get_stats()
            contacts_indexed = stats.get("contacts", [])

            return [
                types.TextContent(
                    type="text",
                    text=(
                        f"✓ Indexed recent messages\n\n"
                        f"• {chunks_added} new conversation chunks created\n"
                        f"• Total chunks: {stats.get('chunk_count', 0)}\n"
                        f"• Contacts indexed: {len(contacts_indexed)}\n"
                        f"• Date range: last {days} days\n\n"
                        f"You can now use ask_messages to search these conversations."
                    )
                )
            ]

    except ImportError as e:
        return [
            types.TextContent(
                type="text",
                text=(
                    f"RAG dependencies not installed.\n\n"
                    f"Run: pip install chromadb openai\n\n"
                    f"Error: {e}"
                )
            )
        ]
    except ValueError as e:
        return [
            types.TextContent(
                type="text",
                text=(
                    f"Configuration error: {e}\n\n"
                    f"Make sure OPENAI_API_KEY environment variable is set, "
                    f"or configure local embeddings."
                )
            )
        ]
    except Exception as e:
        logger.error(f"Error indexing messages: {e}", exc_info=True)
        return [
            types.TextContent(
                type="text",
                text=f"Error indexing messages: {e}"
            )
        ]


async def handle_ask_messages(arguments: dict) -> list[types.TextContent]:
    """
    Handle ask_messages tool call (RAG Sprint 4).

    Semantic search across indexed conversations.

    Args:
        arguments: {"question": str, "contact_name": Optional[str], "limit": Optional[int]}

    Returns:
        Relevant conversation context
    """
    # Validate question
    question, error = validate_non_empty_string(arguments.get("question"), "question")
    if error:
        return [types.TextContent(type="text", text=f"Validation error: {error}")]

    contact_name = arguments.get("contact_name")

    # Validate limit
    limit_raw = arguments.get("limit", 5)
    limit, error = validate_positive_int(limit_raw, "limit", min_val=1, max_val=20)
    if error:
        return [types.TextContent(type="text", text=f"Validation error: {error}")]
    if limit is None:
        limit = 5

    try:
        retriever = get_retriever()

        # Check if index is empty
        stats = retriever.get_stats()
        if stats.get("chunk_count", 0) == 0:
            return [
                types.TextContent(
                    type="text",
                    text=(
                        "No messages have been indexed yet.\n\n"
                        "Run index_messages first to create the search index:\n"
                        "• index_messages with days=30 (indexes all recent messages)\n"
                        "• index_messages with contact_name=\"John\" (indexes specific contact)"
                    )
                )
            ]

        # Perform semantic search
        context, results = retriever.ask(
            question=question,
            limit=limit,
            contact=contact_name,
        )

        if not results:
            filter_text = f" with {contact_name}" if contact_name else ""
            return [
                types.TextContent(
                    type="text",
                    text=f"No relevant conversations found{filter_text} for: \"{question}\""
                )
            ]

        return [
            types.TextContent(
                type="text",
                text=context
            )
        ]

    except ImportError as e:
        return [
            types.TextContent(
                type="text",
                text=(
                    f"RAG dependencies not installed.\n\n"
                    f"Run: pip install chromadb openai\n\n"
                    f"Error: {e}"
                )
            )
        ]
    except Exception as e:
        logger.error(f"Error searching messages: {e}", exc_info=True)
        return [
            types.TextContent(
                type="text",
                text=f"Error searching messages: {e}"
            )
        ]


async def handle_rag_stats(arguments: dict) -> list[types.TextContent]:
    """
    Handle rag_stats tool call (RAG Sprint 4).

    Returns statistics about the indexed message database.

    Args:
        arguments: {} (no arguments needed)

    Returns:
        Statistics about indexed data
    """
    try:
        retriever = get_retriever()
        stats = retriever.get_stats()

        if stats.get("chunk_count", 0) == 0:
            return [
                types.TextContent(
                    type="text",
                    text=(
                        "📊 iMessage RAG Statistics\n\n"
                        "No messages indexed yet.\n\n"
                        "Run index_messages to start building the search index."
                    )
                )
            ]

        contacts_list = stats.get("contacts", [])
        contacts_display = ", ".join(contacts_list[:10])
        if len(contacts_list) > 10:
            contacts_display += f" +{len(contacts_list) - 10} more"

        return [
            types.TextContent(
                type="text",
                text=(
                    f"📊 iMessage RAG Statistics\n\n"
                    f"• Indexed chunks: {stats.get('chunk_count', 0)}\n"
                    f"• Contacts: {stats.get('contact_count', 0)}\n"
                    f"• Oldest message: {stats.get('oldest_chunk', 'N/A')[:10] if stats.get('oldest_chunk') else 'N/A'}\n"
                    f"• Newest message: {stats.get('newest_chunk', 'N/A')[:10] if stats.get('newest_chunk') else 'N/A'}\n"
                    f"• Storage: {stats.get('persist_directory', 'N/A')}\n\n"
                    f"Contacts indexed:\n{contacts_display}"
                )
            )
        ]

    except ImportError as e:
        return [
            types.TextContent(
                type="text",
                text=(
                    f"RAG dependencies not installed.\n\n"
                    f"Run: pip install chromadb openai\n\n"
                    f"Error: {e}"
                )
            )
        ]
    except Exception as e:
        logger.error(f"Error getting RAG stats: {e}", exc_info=True)
        return [
            types.TextContent(
                type="text",
                text=f"Error getting RAG stats: {e}"
            )
        ]


async def handle_get_group_messages(arguments: dict) -> list[types.TextContent]:
    """
    Handle get_group_messages tool call (Sprint 3).

    Args:
        arguments: {"group_id": Optional[str], "participant": Optional[str], "limit": Optional[int]}

    Returns:
        Messages from the specified group chat
    """
    group_id = arguments.get("group_id")
    participant = arguments.get("participant")

    # Validate limit
    limit_raw = arguments.get("limit", 50)
    limit, error = validate_positive_int(limit_raw, "limit", max_val=MAX_MESSAGE_LIMIT)
    if error:
        return [types.TextContent(type="text", text=f"Validation error: {error}")]
    if limit is None:
        limit = 50

    # Validate that at least one of group_id or participant is provided
    if not group_id and not participant:
        return [
            types.TextContent(
                type="text",
                text=(
                    "Error: Either group_id or participant must be provided.\n\n"
                    "Use list_group_chats first to find group IDs, or provide a "
                    "participant phone/email to find groups containing that person."
                )
            )
        ]

    # Get group messages
    message_list = messages.get_group_messages(
        group_id=group_id,
        participant_filter=participant,
        limit=limit
    )

    if not message_list:
        filter_type = f"group_id={group_id}" if group_id else f"participant={participant}"
        return [
            types.TextContent(
                type="text",
                text=(
                    f"No group messages found for {filter_type}.\n\n"
                    "Note: Requires Full Disk Access permission.\n"
                    "Grant in: System Settings → Privacy & Security → Full Disk Access"
                )
            )
        ]

    # Get participant info from first message
    first_msg = message_list[0]
    group_participants = first_msg.get("group_participants", [])
    display_name = first_msg.get("display_name") or "Unnamed Group"

    # Resolve participant names
    participant_names = []
    for handle in group_participants:
        contact = contacts.get_contact_by_phone(handle)
        if contact:
            participant_names.append(contact.name)
        else:
            display_handle = handle[:15] + "..." if len(handle) > 15 else handle
            participant_names.append(display_handle)

    participants_str = ", ".join(participant_names[:5])
    if len(participant_names) > 5:
        participants_str += f" +{len(participant_names) - 5} more"

    # Format response
    response_lines = [
        f"📱 {display_name} ({len(message_list)} messages)",
        f"Participants: {participants_str}",
        ""
    ]

    for msg in message_list:
        # Resolve sender name
        sender_handle = msg.get("sender_handle", "unknown")
        if msg["is_from_me"]:
            sender_name = "You"
        else:
            sender_contact = contacts.get_contact_by_phone(sender_handle)
            sender_name = sender_contact.name if sender_contact else sender_handle[:15]

        date = msg["date"][:19] if msg["date"] else "Unknown date"
        text = msg["text"][:100] + "..." if len(msg["text"]) > 100 else msg["text"]

        response_lines.append(f"[{date}] {sender_name}: {text}")

    return [
        types.TextContent(
            type="text",
            text="\n".join(response_lines)
        )
    ]


# ============================================================================
# Unified RAG Handlers (Multi-Source Knowledge Base)
# ============================================================================


async def handle_index_knowledge(arguments: dict) -> list[types.TextContent]:
    """
    Handle index_knowledge tool call for unified multi-source RAG.
    """
    source = arguments.get("source", "").lower()
    days = arguments.get("days", 30)
    limit = arguments.get("limit")

    if not source:
        return [
            types.TextContent(
                type="text",
                text="Error: 'source' is required. Options: superwhisper, notes, local, gmail, slack, calendar"
            )
        ]

    # Validate days
    if days:
        validated, error = validate_positive_int(days, "days", min_val=1, max_val=1460)
        if error:
            return [types.TextContent(type="text", text=f"Error: {error}")]
        days = validated

    # Validate limit
    if limit:
        validated, error = validate_positive_int(limit, "limit", min_val=1, max_val=10000)
        if error:
            return [types.TextContent(type="text", text=f"Error: {error}")]
        limit = validated

    try:
        retriever = get_unified_retriever()

        if source == "superwhisper":
            result = retriever.index_superwhisper(days=days, limit=limit)
            return [
                types.TextContent(
                    type="text",
                    text=(
                        f"SuperWhisper indexing complete!\n"
                        f"- Transcriptions found: {result.get('chunks_found', 0)}\n"
                        f"- Transcriptions indexed: {result.get('chunks_indexed', 0)}\n"
                        f"- Duration: {result.get('duration_seconds', 0):.1f}s\n\n"
                        f"Use search_knowledge to search your voice transcriptions."
                    )
                )
            ]

        elif source == "notes":
            result = retriever.index_notes(days=days, limit=limit)
            return [
                types.TextContent(
                    type="text",
                    text=(
                        f"Notes indexing complete!\n"
                        f"- Document sections found: {result.get('chunks_found', 0)}\n"
                        f"- Sections indexed: {result.get('chunks_indexed', 0)}\n"
                        f"- Duration: {result.get('duration_seconds', 0):.1f}s\n\n"
                        f"Use search_knowledge to search your notes."
                    )
                )
            ]

        elif source == "local":
            result = retriever.index_local_sources(days=days)
            by_source = result.get("by_source", {})
            return [
                types.TextContent(
                    type="text",
                    text=(
                        f"Local sources indexing complete!\n\n"
                        f"SuperWhisper:\n"
                        f"  - Found: {by_source.get('superwhisper', {}).get('chunks_found', 0)}\n"
                        f"  - Indexed: {by_source.get('superwhisper', {}).get('chunks_indexed', 0)}\n\n"
                        f"Notes:\n"
                        f"  - Found: {by_source.get('notes', {}).get('chunks_found', 0)}\n"
                        f"  - Indexed: {by_source.get('notes', {}).get('chunks_indexed', 0)}\n\n"
                        f"Total chunks indexed: {result.get('total_chunks_indexed', 0)}\n\n"
                        f"Use search_knowledge to search across all sources."
                    )
                )
            ]

        elif source in ("gmail", "slack", "calendar"):
            return [
                types.TextContent(
                    type="text",
                    text=(
                        f"Indexing {source} requires pre-fetched data.\n\n"
                        f"For {source}, first fetch data using the appropriate MCP tools, "
                        f"then pass the data to the indexer programmatically.\n\n"
                        f"For local sources (superwhisper, notes), use index_knowledge directly."
                    )
                )
            ]

        else:
            return [
                types.TextContent(
                    type="text",
                    text=f"Unknown source: {source}. Options: superwhisper, notes, local, gmail, slack, calendar"
                )
            ]

    except ImportError as e:
        return [
            types.TextContent(
                type="text",
                text=f"Error: RAG dependencies not installed. {str(e)}"
            )
        ]
    except Exception as e:
        logger.error(f"Error in index_knowledge: {e}", exc_info=True)
        return [
            types.TextContent(
                type="text",
                text=f"Error indexing {source}: {str(e)}"
            )
        ]


async def handle_search_knowledge(arguments: dict) -> list[types.TextContent]:
    """
    Handle search_knowledge tool call for unified semantic search.
    """
    query = arguments.get("query", "").strip()
    sources = arguments.get("sources")
    days = arguments.get("days")
    limit = arguments.get("limit", 10)

    if not query:
        return [
            types.TextContent(
                type="text",
                text="Error: 'query' is required."
            )
        ]

    # Validate limit
    if limit:
        validated, error = validate_positive_int(limit, "limit", min_val=1, max_val=50)
        if error:
            return [types.TextContent(type="text", text=f"Error: {error}")]
        limit = validated

    # Validate days
    if days:
        validated, error = validate_positive_int(days, "days", min_val=1, max_val=1460)
        if error:
            return [types.TextContent(type="text", text=f"Error: {error}")]
        days = validated

    try:
        retriever = get_unified_retriever()

        # Check if anything is indexed
        stats = retriever.get_stats()
        if stats.get("total_chunks", 0) == 0:
            return [
                types.TextContent(
                    type="text",
                    text=(
                        "No content has been indexed yet.\n\n"
                        "Run index_knowledge first to build the search index:\n"
                        "• index_knowledge with source='superwhisper' (voice transcriptions)\n"
                        "• index_knowledge with source='notes' (markdown documents)\n"
                        "• index_knowledge with source='local' (both)"
                    )
                )
            ]

        # Perform search
        context = retriever.ask(
            question=query,
            sources=sources,
            limit=limit,
            days=days,
        )

        return [
            types.TextContent(
                type="text",
                text=context
            )
        ]

    except ImportError as e:
        return [
            types.TextContent(
                type="text",
                text=f"Error: RAG dependencies not installed. {str(e)}"
            )
        ]
    except Exception as e:
        logger.error(f"Error in search_knowledge: {e}", exc_info=True)
        return [
            types.TextContent(
                type="text",
                text=f"Error searching: {str(e)}"
            )
        ]


async def handle_knowledge_stats(arguments: dict) -> list[types.TextContent]:
    """
    Handle knowledge_stats tool call.
    """
    source = arguments.get("source")

    try:
        retriever = get_unified_retriever()
        stats = retriever.get_stats(source=source)

        if stats.get("total_chunks", 0) == 0:
            return [
                types.TextContent(
                    type="text",
                    text=(
                        "Knowledge base is empty.\n\n"
                        "Run index_knowledge to start building the search index:\n"
                        "• index_knowledge with source='superwhisper'\n"
                        "• index_knowledge with source='notes'\n"
                        "• index_knowledge with source='local' (both)"
                    )
                )
            ]

        # Format stats
        lines = [
            "Knowledge Base Statistics",
            "=" * 40,
            f"Total chunks indexed: {stats.get('total_chunks', 0)}",
            f"Unique participants: {stats.get('unique_participants', 0)}",
            f"Unique tags: {stats.get('unique_tags', 0)}",
            "",
            "By Source:",
        ]

        by_source = stats.get("by_source", {})
        for src, info in sorted(by_source.items()):
            count = info.get("chunk_count", 0)
            if count > 0:
                oldest = info.get("oldest", "N/A")
                newest = info.get("newest", "N/A")
                lines.append(f"  {src}: {count} chunks")
                lines.append(f"    Range: {oldest[:10] if oldest else 'N/A'} to {newest[:10] if newest else 'N/A'}")

        if stats.get("oldest_chunk") and stats.get("newest_chunk"):
            lines.append("")
            lines.append(f"Overall date range: {stats['oldest_chunk'][:10]} to {stats['newest_chunk'][:10]}")

        return [
            types.TextContent(
                type="text",
                text="\n".join(lines)
            )
        ]

    except ImportError as e:
        return [
            types.TextContent(
                type="text",
                text=f"Error: RAG dependencies not installed. {str(e)}"
            )
        ]
    except Exception as e:
        logger.error(f"Error in knowledge_stats: {e}", exc_info=True)
        return [
            types.TextContent(
                type="text",
                text=f"Error getting stats: {str(e)}"
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

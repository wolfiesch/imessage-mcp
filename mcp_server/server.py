#!/usr/bin/env python3
# ============================================================================
# CHANGELOG (recent first, max 5 entries)
# 01/03/2026 - Major refactoring: extracted handlers to modules, added tool registry (Claude)
# ============================================================================
"""
iMessage MCP Server - Personalized messaging with Life Planner integration.

Refactored architecture with extracted utilities and handler modules.

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

# Add parent directory to path for imports from src/
sys.path.insert(0, str(Path(__file__).parent.parent))
# Add mcp_server directory to path for handler imports
sys.path.insert(0, str(Path(__file__).parent))

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp import types

from src.messages_interface import MessagesInterface
from src.contacts_manager import ContactsManager

# Import configuration (from mcp_server/)
from config import (
    CONFIG,
    PROJECT_ROOT,
    resolve_path,
    get_chroma_path,
    get_contacts_config_path,
    logger,
)

# Import handlers (from mcp_server/handlers/)
from handlers import messaging, contacts, reading, groups, rag, analytics

# Import response utilities (from mcp_server/utils/)
from utils.responses import text_response

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
                persist_directory=get_chroma_path(),
                contacts_config=get_contacts_config_path(),
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
                persist_directory=get_chroma_path(),
            )
            logger.info("Unified RAG retriever initialized")
        except ImportError as e:
            logger.warning(f"Unified RAG dependencies not installed: {e}")
            raise
    return _unified_retriever


# Initialize server
app = Server(CONFIG["server_name"])

# Initialize components with resolved paths
messages = MessagesInterface(resolve_path(CONFIG["paths"]["messages_db"]))
contacts_mgr = ContactsManager(resolve_path(CONFIG["paths"]["contacts_config"]))

logger.info(f"MCP server initialized: {CONFIG['server_name']}")


# =============================================================================
# TOOL DEFINITIONS
# =============================================================================

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
            name="send_message_by_phone",
            description=(
                "Send an iMessage directly to a phone number or iMessage handle, "
                "without requiring a contact entry. Use for one-off messages to numbers not in contacts."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "phone_number": {
                        "type": "string",
                        "description": "Phone number (e.g., +14155551234) or iMessage handle (e.g., email@icloud.com)"
                    },
                    "message": {
                        "type": "string",
                        "description": "Message text to send"
                    }
                },
                "required": ["phone_number", "message"]
            }
        ),
        types.Tool(
            name="add_contact",
            description=(
                "Add a new contact to the contacts list. "
                "The contact will be saved to contacts.json and available for future messaging."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Contact name (e.g., 'Dora Housing Guild')"
                    },
                    "phone": {
                        "type": "string",
                        "description": "Phone number (e.g., +18503066993)"
                    },
                    "relationship_type": {
                        "type": "string",
                        "description": "Relationship type (default: 'other'). Options: friend, family, colleague, professional, other"
                    },
                    "notes": {
                        "type": "string",
                        "description": "Optional notes about the contact"
                    }
                },
                "required": ["name", "phone"]
            }
        ),
        types.Tool(
            name="get_recent_messages",
            description=(
                "Retrieve recent message history with a contact. "
                "Supports pagination via offset parameter for full history retrieval. "
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
                        "description": "Number of messages to retrieve (default: 20, max: 500)",
                        "default": 20
                    },
                    "offset": {
                        "type": "number",
                        "description": "Number of messages to skip for pagination (default: 0)",
                        "default": 0
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
                "Sources: 'imessage' (text conversations), 'superwhisper' (voice transcriptions), 'notes' (markdown documents), "
                "'gmail' (emails - requires pre-fetched data), 'slack' (messages - requires pre-fetched data), "
                "'calendar' (events - requires pre-fetched data). "
                "Use source='local' to index both SuperWhisper and Notes at once."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "source": {
                        "type": "string",
                        "description": "Source to index: 'imessage', 'superwhisper', 'notes', 'local' (both), 'gmail', 'slack', 'calendar'",
                        "enum": ["imessage", "superwhisper", "notes", "local", "gmail", "slack", "calendar"]
                    },
                    "days": {
                        "type": "number",
                        "description": "Number of days of history to index (default: 30)",
                        "default": 30
                    },
                    "limit": {
                        "type": "number",
                        "description": "Maximum items to index (default: no limit)"
                    },
                    "contact_name": {
                        "type": "string",
                        "description": "For iMessage: Optional contact name to index only that conversation"
                    },
                    "incremental": {
                        "type": "boolean",
                        "description": "For iMessage: If true, only index new messages since last run (default: true)",
                        "default": True
                    }
                },
                "required": ["source"]
            }
        ),
        types.Tool(
            name="search_knowledge",
            description=(
                "Semantic search across all indexed sources (iMessage, SuperWhisper, Notes, Gmail, Slack, Calendar). "
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
        ),
        types.Tool(
            name="migrate_rag_data",
            description=(
                "One-time migration: copy old RAG collection to new unified collection. "
                "Migrates data from 'imessage_chunks' to 'unified_imessage_chunks'. "
                "Safe to run multiple times (idempotent). "
                "Required before deleting old RAG system code."
            ),
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        ),
        # ===== T0 FEATURES =====
        types.Tool(
            name="get_attachments",
            description=(
                "Get attachments (photos, videos, files) from messages. "
                "Filter by contact or MIME type (e.g., 'image/', 'video/', 'application/pdf'). "
                "Returns file paths, sizes, and metadata. Sprint 4 T0 feature."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "contact_name": {
                        "type": "string",
                        "description": "Optional: Filter attachments by contact name"
                    },
                    "mime_type": {
                        "type": "string",
                        "description": "Optional: Filter by MIME type prefix (e.g., 'image/', 'video/')"
                    },
                    "limit": {
                        "type": "number",
                        "description": "Maximum attachments to return (default: 50)",
                        "default": 50
                    }
                },
                "required": []
            }
        ),
        types.Tool(
            name="get_unread_messages",
            description=(
                "Get unread messages that are awaiting response. "
                "Shows messages you haven't read yet with age information. "
                "Useful for finding messages that need attention. Sprint 4 T0 feature."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "number",
                        "description": "Maximum unread messages to return (default: 50)",
                        "default": 50
                    }
                },
                "required": []
            }
        ),
        types.Tool(
            name="get_reactions",
            description=(
                "Get reactions/tapbacks from messages. "
                "See who reacted to which messages with love, like, laugh, etc. "
                "Shows the original message that was reacted to. Sprint 4 T0 feature."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "contact_name": {
                        "type": "string",
                        "description": "Optional: Filter reactions by contact"
                    },
                    "limit": {
                        "type": "number",
                        "description": "Maximum reactions to return (default: 100)",
                        "default": 100
                    }
                },
                "required": []
            }
        ),
        types.Tool(
            name="get_conversation_analytics",
            description=(
                "Get analytics about messaging patterns. "
                "Shows total messages, sent/received ratio, busiest times, top contacts, etc. "
                "Can analyze all conversations or filter by specific contact. Sprint 4 T0 feature."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "contact_name": {
                        "type": "string",
                        "description": "Optional: Analyze only messages with this contact"
                    },
                    "days": {
                        "type": "number",
                        "description": "Number of days to analyze (default: 30)",
                        "default": 30
                    }
                },
                "required": []
            }
        ),
        # ===== T1 FEATURES =====
        types.Tool(
            name="get_message_thread",
            description=(
                "Get messages in a reply thread. "
                "Follow inline reply chains to see the full context. "
                "Provide a message GUID to get all messages in that thread. Sprint 4 T1 feature."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "message_guid": {
                        "type": "string",
                        "description": "GUID of any message in the thread"
                    },
                    "limit": {
                        "type": "number",
                        "description": "Maximum messages to return (default: 50)",
                        "default": 50
                    }
                },
                "required": ["message_guid"]
            }
        ),
        types.Tool(
            name="extract_links",
            description=(
                "Extract URLs shared in conversations. "
                "Find all links that have been shared with context about who shared them. "
                "Filter by contact or time period. Sprint 4 T1 feature."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "contact_name": {
                        "type": "string",
                        "description": "Optional: Filter links by contact"
                    },
                    "days": {
                        "type": "number",
                        "description": "Optional: Only links from the last N days"
                    },
                    "limit": {
                        "type": "number",
                        "description": "Maximum links to return (default: 100)",
                        "default": 100
                    }
                },
                "required": []
            }
        ),
        types.Tool(
            name="get_voice_messages",
            description=(
                "Get voice/audio messages with file paths. "
                "Useful for finding audio messages that could be transcribed. "
                "Returns file paths that can be passed to transcription services. Sprint 4 T1 feature."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "contact_name": {
                        "type": "string",
                        "description": "Optional: Filter voice messages by contact"
                    },
                    "limit": {
                        "type": "number",
                        "description": "Maximum voice messages to return (default: 50)",
                        "default": 50
                    }
                },
                "required": []
            }
        ),
        types.Tool(
            name="get_scheduled_messages",
            description=(
                "Get scheduled messages that are pending send. "
                "View messages queued for future delivery. Read-only. "
                "Note: Scheduled messages are created through Messages app, not programmatically. Sprint 4 T1 feature."
            ),
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        ),
        types.Tool(
            name="list_recent_handles",
            description=(
                "List all unique phone numbers and email handles from recent messages. "
                "Shows which are in your contacts vs unknown. "
                "Useful for finding temporary numbers or people not in contacts."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "days": {
                        "type": "number",
                        "description": "Number of days to look back (default: 30)",
                        "default": 30
                    },
                    "limit": {
                        "type": "number",
                        "description": "Maximum handles to return (default: 100)",
                        "default": 100
                    }
                },
                "required": []
            }
        ),
        types.Tool(
            name="search_unknown_senders",
            description=(
                "Find messages from phone numbers not in your contacts. "
                "Identifies unknown senders with sample messages. "
                "Useful for finding temporary numbers, business contacts, or people to add."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "days": {
                        "type": "number",
                        "description": "Number of days to look back (default: 30)",
                        "default": 30
                    },
                    "limit": {
                        "type": "number",
                        "description": "Maximum messages to return (default: 100)",
                        "default": 100
                    }
                },
                "required": []
            }
        ),
        # ===== T2 FEATURES =====
        types.Tool(
            name="get_conversation_for_summary",
            description=(
                "Get conversation data formatted for AI summarization. "
                "Returns formatted dialogue, key stats, detected topics, and metadata. "
                "Pass the conversation_text to Claude to generate a summary. Sprint 4 T2 feature."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "contact_name": {
                        "type": "string",
                        "description": "Name of the contact whose conversation to summarize"
                    },
                    "days": {
                        "type": "number",
                        "description": "Optional: Limit to last N days of conversation"
                    },
                    "limit": {
                        "type": "number",
                        "description": "Maximum messages to include (default: 200)",
                        "default": 200
                    }
                },
                "required": ["contact_name"]
            }
        ),
        types.Tool(
            name="detect_follow_up_needed",
            description=(
                "Smart reminders - detect conversations needing follow-up. "
                "Finds: unanswered questions, pending promises you made, things you're waiting on, "
                "stale conversations, and time-sensitive messages. Sprint 4 T2 feature."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "days": {
                        "type": "number",
                        "description": "Look back this many days (default: 7)",
                        "default": 7
                    },
                    "min_stale_days": {
                        "type": "number",
                        "description": "Flag conversations stale after this many days (default: 3)",
                        "default": 3
                    },
                    "limit": {
                        "type": "number",
                        "description": "Maximum items per category (default: 50)",
                        "default": 50
                    }
                },
                "required": []
            }
        )
    ]


# =============================================================================
# TOOL DISPATCHER WITH REGISTRY PATTERN
# =============================================================================

# Tool registry: Maps tool names to their handlers and required dependencies
# Dependency types:
#   "messages_contacts" - needs messages and contacts
#   "messages_only" - needs only messages
#   "contacts_only" - needs only contacts
#   "rag" - needs RAG retrievers and messages/contacts
#   "analytics" - needs messages and contacts for analytics

TOOL_REGISTRY = {
    # Messaging handlers
    "send_message": (messaging.handle_send_message, "messages_contacts"),
    "send_message_by_phone": (messaging.handle_send_message_by_phone, "messages_only"),

    # Contacts handlers
    "add_contact": (contacts.handle_add_contact, "contacts_only"),
    "list_contacts": (contacts.handle_list_contacts, "contacts_only"),

    # Reading handlers
    "get_recent_messages": (reading.handle_get_recent_messages, "messages_contacts"),
    "get_all_recent_conversations": (reading.handle_get_all_recent_conversations, "messages_contacts"),
    "search_messages": (reading.handle_search_messages, "messages_contacts"),
    "get_messages_by_phone": (reading.handle_get_messages_by_phone, "messages_contacts"),
    "get_attachments": (reading.handle_get_attachments, "messages_contacts"),
    "get_unread_messages": (reading.handle_get_unread_messages, "messages_contacts"),
    "get_message_thread": (reading.handle_get_message_thread, "messages_contacts"),
    "extract_links": (reading.handle_extract_links, "messages_contacts"),
    "get_voice_messages": (reading.handle_get_voice_messages, "messages_contacts"),
    "get_scheduled_messages": (reading.handle_get_scheduled_messages, "messages_contacts"),
    "list_recent_handles": (reading.handle_list_recent_handles, "messages_contacts"),
    "search_unknown_senders": (reading.handle_search_unknown_senders, "messages_contacts"),

    # Groups handlers
    "list_group_chats": (groups.handle_list_group_chats, "messages_contacts"),
    "get_group_messages": (groups.handle_get_group_messages, "messages_contacts"),

    # RAG handlers
    "index_messages": (rag.handle_index_messages, "rag"),
    "ask_messages": (rag.handle_ask_messages, "rag"),
    "rag_stats": (rag.handle_rag_stats, "rag"),
    "index_knowledge": (rag.handle_index_knowledge, "rag"),
    "search_knowledge": (rag.handle_search_knowledge, "rag"),
    "knowledge_stats": (rag.handle_knowledge_stats, "rag"),
    "migrate_rag_data": (rag.handle_migrate_rag_data, "rag"),

    # Analytics handlers
    "get_reactions": (analytics.handle_get_reactions, "messages_contacts"),
    "get_conversation_analytics": (analytics.handle_get_conversation_analytics, "messages_contacts"),
    "get_conversation_for_summary": (analytics.handle_get_conversation_for_summary, "messages_contacts"),
    "detect_follow_up_needed": (analytics.handle_detect_follow_up_needed, "messages_contacts"),
}


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    """
    Handle MCP tool calls using the tool registry pattern.

    Args:
        name: Tool name
        arguments: Tool arguments

    Returns:
        List of TextContent responses
    """
    logger.info(f"Tool called: {name} with args: {arguments}")

    try:
        # Look up handler in registry
        if name not in TOOL_REGISTRY:
            raise ValueError(f"Unknown tool: {name}")

        handler, dep_type = TOOL_REGISTRY[name]

        # Call handler with appropriate dependencies
        if dep_type == "messages_contacts":
            return await handler(arguments, messages, contacts_mgr)
        elif dep_type == "messages_only":
            return await handler(arguments, messages)
        elif dep_type == "contacts_only":
            return await handler(arguments, contacts_mgr)
        elif dep_type == "rag":
            return await handler(
                arguments,
                get_retriever,
                get_unified_retriever,
                messages,
                contacts_mgr
            )
        else:
            raise ValueError(f"Unknown dependency type: {dep_type}")

    except Exception as e:
        logger.error(f"Error executing tool {name}: {e}", exc_info=True)
        return text_response(f"Error: {str(e)}")


# =============================================================================
# MAIN ENTRY POINT
# =============================================================================

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
    logger.info(f"Loaded {len(contacts_mgr.list_contacts())} contacts")

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

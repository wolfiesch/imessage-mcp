# ============================================================================
# CHANGELOG (recent first, max 5 entries)
# 01/03/2026 - Created handlers package for MCP server refactoring (Claude)
# ============================================================================
"""
MCP Tool Handlers Package

Organized by domain:
- messaging: send_message, send_message_by_phone
- contacts: add_contact, list_contacts
- reading: get_recent_messages, search_messages, get_attachments, etc.
- groups: list_group_chats, get_group_messages
- rag: index_knowledge, search_knowledge, etc.
- analytics: get_conversation_analytics, detect_follow_up_needed
"""

from . import messaging
from . import contacts
from . import reading
from . import groups
from . import rag
from . import analytics

__all__ = [
    "messaging",
    "contacts",
    "reading",
    "groups",
    "rag",
    "analytics",
]

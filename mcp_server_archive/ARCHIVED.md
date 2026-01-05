# MCP Server Archive

**Archived:** 01/04/2026
**Reason:** Migrated to Gateway CLI architecture for 19x faster performance

## Why Archived?

The MCP server has been replaced by the Gateway CLI (`gateway/imessage_client.py`) which provides:

- **19x faster execution** (40ms vs 763ms per operation)
- **80% fewer tokens** in Claude Code sessions
- **Simpler architecture** (no MCP framework dependency)
- **Same reliability** (uses identical `MessagesInterface` code)

## What Was Here

The MCP server provided 42 tools for iMessage operations:
- Messaging: `send_message`, `send_message_by_phone`
- Reading: 12 tools for messages, search, attachments, etc.
- Groups: `list_group_chats`, `get_group_messages`
- RAG: 7 tools for semantic search and knowledge base
- Analytics: 4 tools for conversation insights

All functionality is now available via the Gateway CLI with identical or better performance.

## How to Restore (if needed)

1. Move this directory back:
   ```bash
   mv mcp_server_archive mcp_server
   ```

2. Re-register with Claude Code:
   ```bash
   claude mcp add -t stdio imessage-life-planner -- python3 /path/to/mcp_server/server.py
   ```

3. Reinstall MCP dependency:
   ```bash
   pip install mcp>=1.0.0
   ```

## Gateway CLI Equivalent Commands

| MCP Tool | Gateway CLI Command |
|----------|-------------------|
| `send_message` | `send <contact> <message>` |
| `send_message_by_phone` | `send-by-phone <phone> <message>` |
| `get_recent_messages` | `messages <contact>` |
| `search_messages` | `find <contact> --query <text>` |
| `get_unread_messages` | `unread` |
| `index_knowledge` | `index --source=<source>` |
| `search_knowledge` | `search <query>` |
| `knowledge_stats` | `stats` |

Full command list: `python3 gateway/imessage_client.py --help`

## Files in Archive

- `server.py` - Main MCP server (940 lines)
- `config.py` - Configuration and path resolution
- `handlers/` - Tool handlers by domain
  - `messaging.py` - Send message handlers
  - `reading.py` - Message reading handlers
  - `contacts.py` - Contact management
  - `groups.py` - Group chat handlers
  - `rag.py` - RAG/semantic search handlers
  - `analytics.py` - Analytics handlers
- `utils/` - Shared utilities
- `server_old_backup.py` - Legacy backup (can be deleted)

## Dependencies (no longer needed in main project)

```
mcp>=1.0.0  # MCP Python SDK
```

This dependency has been commented out in `requirements.txt`.

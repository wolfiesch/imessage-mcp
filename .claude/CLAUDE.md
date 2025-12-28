# CLAUDE.md

This file provides guidance to Claude Code when working with this repository.

## Project Overview

iMessage MCP server for macOS. Send and read iMessages through Claude with contact intelligence and fuzzy name matching.

## Build & Test Commands

```bash
# Run all tests
pytest tests/ -v

# Run specific test file
pytest tests/test_contacts_sync.py -v

# With coverage
pytest --cov=src tests/

# Sync contacts from macOS Contacts app
python3 scripts/sync_contacts.py

# Test MCP protocol directly
python3 scripts/test_mcp_protocol.py

# Start MCP server manually (for debugging)
python3 mcp_server/server.py

# Verify MCP server registration
claude mcp list
```

## Architecture

### MCP Server Flow

```
Claude Code ──(JSON-RPC/stdio)──> mcp_server/server.py
                                        │
                                        ├── src/contacts_manager.py
                                        │       └── Loads contacts from config/contacts.json
                                        │
                                        ├── src/messages_interface.py
                                        │       ├── AppleScript → Messages.app (send)
                                        │       └── SQLite → ~/Library/Messages/chat.db (read)
                                        │
                                        └── src/contacts_sync.py
                                                └── PyObjC → macOS Contacts.app
```

### Available MCP Tools

| Tool | Description |
|------|-------------|
| `send_message` | Send iMessage by contact name |
| `get_recent_messages` | Get messages with specific contact |
| `list_contacts` | List configured contacts |
| `get_all_recent_conversations` | Get recent messages across ALL contacts |
| `search_messages` | Full-text search across messages |
| `get_messages_by_phone` | Get messages by phone number (no contact needed) |

### Path Resolution (Critical)

MCP servers are started from arbitrary working directories. All paths in `server.py` use:

```python
PROJECT_ROOT = Path(__file__).parent.parent
CONFIG_PATH = PROJECT_ROOT / "config" / "mcp_server.json"
```

Always use absolute paths resolved from `PROJECT_ROOT`, never relative paths.

### Import Pattern

The server uses `sys.path` insertion to enable imports from `src/`:

```python
sys.path.insert(0, str(Path(__file__).parent.parent))
from src.messages_interface import MessagesInterface
```

This is necessary because MCP servers run as standalone processes, not as installed packages.

### macOS Messages Database

Messages are stored in `~/Library/Messages/chat.db` (requires Full Disk Access):

- **text** column: Plain text (older messages)
- **attributedBody** column: Binary blob (macOS Ventura+)

The `extract_text_from_blob()` function in `messages_interface.py` handles parsing both formats.

### Contact Resolution

`ContactsManager` provides name → phone lookup:
1. Exact match (case-insensitive)
2. Partial match (contains)
3. Fuzzy matching with fuzzywuzzy (threshold 0.85)

Phone normalization: `+1 (415) 555-1234` → `14155551234`

## Key Files

| File | Purpose |
|------|---------|
| `mcp_server/server.py` | MCP server entry point, tool handlers |
| `src/messages_interface.py` | AppleScript send + chat.db read |
| `src/contacts_manager.py` | Contact lookup from JSON config |
| `src/contacts_sync.py` | macOS Contacts sync + fuzzy matching |
| `config/contacts.json` | Contact data (gitignored - use sync script) |
| `config/mcp_server.json` | Server configuration |

## Claude Code Skill

This project includes a skill at `.claude/skills/imessage-texting/SKILL.md` that provides:
- Natural language message sending ("text John saying I'm late")
- Conversation lookup and search
- Message drafting guidelines to match your style

The skill wraps the MCP tools with guidance for common workflows.

## Troubleshooting

**MCP tools not appearing:**
```bash
# Check server is registered
claude mcp list

# Re-register if needed
claude mcp add -t stdio imessage-mcp -- python3 /path/to/mcp_server/server.py
```

**"Contact not found":**
```bash
# Sync contacts from macOS
python3 scripts/sync_contacts.py
```

**Messages showing `[message content not available]`:**
- Check Full Disk Access in System Settings
- Some messages are attachment-only (no text content)

## Dependencies

Core: `mcp>=1.0.0`, `fuzzywuzzy`, `python-Levenshtein`, `pyobjc-framework-Contacts`

Install: `pip install -r requirements.txt`

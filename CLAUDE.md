# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

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

The `extract_text_from_blob()` function in `messages_interface.py` handles parsing both formats using:
1. `parse_attributed_body()` - Parses NSKeyedArchiver bplist format
2. Streamtyped format parsing - Finds NSString markers and extracts text
3. Fallback regex extraction for edge cases

**Cocoa Timestamps**: Messages use nanoseconds since 2001-01-01 (Cocoa epoch). Convert with:
```python
from datetime import datetime, timedelta
cocoa_epoch = datetime(2001, 1, 1)
date = cocoa_epoch + timedelta(seconds=date_cocoa / 1_000_000_000)
```

### Contact Resolution

`ContactsManager` provides name → phone lookup:
1. Exact match (case-insensitive)
2. Partial match (contains)
3. Fuzzy matching with fuzzywuzzy (threshold 0.85)

Phone normalization: `+1 (415) 555-1234` → `14155551234`

### Fuzzy Matching Strategy

`FuzzyNameMatcher` in `contacts_sync.py` uses multiple fuzzywuzzy strategies:
- `token_sort_ratio`: Handles word order ("John Doe" vs "Doe John")
- `token_set_ratio`: Handles partial matches ("John Michael Doe" vs "John Doe")
- `partial_ratio`: Substring matches ("John" vs "John Doe")
- `ratio`: Basic Levenshtein distance

Returns best score normalized to 0-1.

## Key Files

| File | Purpose |
|------|---------|
| `mcp_server/server.py` | MCP server entry point, tool handlers |
| `src/messages_interface.py` | AppleScript send + chat.db read |
| `src/contacts_manager.py` | Contact lookup from JSON config |
| `src/contacts_sync.py` | macOS Contacts sync + fuzzy matching |
| `config/contacts.json` | Contact data (gitignored - use sync script) |
| `config/mcp_server.json` | Server configuration |

## Troubleshooting

**MCP tools not appearing:**
```bash
# Check server is registered
claude mcp list

# Re-register if needed
claude mcp add -t stdio imessage-mcp -- python3 /path/to/mcp_server/server.py

# Check logs
tail -f logs/mcp_server.log
```

**"Contact not found":**
```bash
# Sync contacts from macOS
python3 scripts/sync_contacts.py
```

**Messages showing `[message content not available]`:**
- Check Full Disk Access in System Settings → Privacy & Security
- Some messages are attachment-only (no text content)
- Verify database access: `ls ~/Library/Messages/chat.db`

**AppleScript errors sending messages:**
- Ensure Messages.app is running
- Check Automation permissions in System Settings
- Verify phone number format is valid

## Dependencies

Core: `mcp>=1.0.0`, `fuzzywuzzy`, `python-Levenshtein`, `pyobjc-framework-Contacts`

Install: `pip install -r requirements.txt`

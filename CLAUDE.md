# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with this repository.

## Project Overview

iMessage Gateway CLI for macOS. Send and read iMessages through Claude Code with contact intelligence, fuzzy name matching, and semantic search (RAG).

**Architecture: Gateway CLI (MCP-Free)**
- 19x faster than MCP-based alternatives (40ms vs 763ms per operation)
- Direct Python CLI execution via Bash tool calls
- No MCP framework dependency

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

# Run performance benchmarks
python3 -m Texting.benchmarks.run_benchmarks
```

## Architecture

### Gateway CLI Flow

```
Claude Code ──(Bash tool)──> gateway/imessage_client.py
                                    │
                                    ├── src/contacts_manager.py
                                    │       └── Loads contacts from config/contacts.json
                                    │
                                    ├── src/messages_interface.py
                                    │       ├── AppleScript → Messages.app (send)
                                    │       └── SQLite → ~/Library/Messages/chat.db (read)
                                    │
                                    └── src/rag/unified/
                                            ├── retriever.py    # UnifiedRetriever facade
                                            ├── imessage_indexer.py  # Incremental iMessage indexing
                                            └── index_state.py  # Watermark tracking
```

### Available Commands (27 total)

| Category | Commands |
|----------|----------|
| **Messaging (3)** | `send`, `send-by-phone`, `add-contact` |
| **Reading (12)** | `messages`, `find`, `recent`, `unread`, `handles`, `unknown`, `attachments`, `voice`, `links`, `thread`, `scheduled`, `summary` |
| **Groups (2)** | `groups`, `group-messages` |
| **Analytics (3)** | `analytics`, `followup`, `reactions` |
| **Contacts (1)** | `contacts` |
| **RAG (6)** | `index`, `search`, `ask`, `stats`, `clear`, `sources` |

### Key Command Examples

```bash
# Send message to contact
python3 gateway/imessage_client.py send "John" "Hello!"

# Send to phone number directly
python3 gateway/imessage_client.py send-by-phone "+14155551234" "Hi!"

# Find messages with keyword search
python3 gateway/imessage_client.py find "John" --query "meeting" --json

# Semantic search (RAG)
python3 gateway/imessage_client.py search "dinner plans with Sarah" --json

# Index iMessages for semantic search
python3 gateway/imessage_client.py index --source=imessage --days 30
```

### Path Resolution (Critical)

All paths in the Gateway CLI use:

```python
SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent
```

Always use absolute paths resolved from `PROJECT_ROOT`, never relative paths.

### Import Pattern

The CLI uses `sys.path` insertion to enable imports from `src/`:

```python
sys.path.insert(0, str(Path(__file__).parent.parent))
from src.messages_interface import MessagesInterface
```

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
| `gateway/imessage_client.py` | Gateway CLI entry point (27 commands) |
| `src/messages_interface.py` | AppleScript send + chat.db read |
| `src/contacts_manager.py` | Contact lookup from JSON config |
| `src/contacts_sync.py` | macOS Contacts sync + fuzzy matching |
| `src/rag/unified/retriever.py` | UnifiedRetriever facade for RAG |
| `src/rag/unified/imessage_indexer.py` | Incremental iMessage indexing |
| `config/contacts.json` | Contact data (gitignored - use sync script) |
| `skills/imessage-gateway/SKILL.md` | Claude Code skill definition |

## RAG System

The unified RAG system supports semantic search across multiple sources:

### Sources
- **imessage**: iMessage conversations
- **superwhisper**: Voice note transcriptions
- **notes**: Markdown documents
- **local**: Both superwhisper + notes
- **gmail/slack/calendar**: Via Rube integration (pre-fetched data)

### Incremental Indexing

Uses `IndexState` watermarking for efficient updates:
- Tracks last indexed timestamp per source
- Second run with no new content: <1s (vs 35s full re-index)
- `--full` flag forces complete re-index

### Commands

```bash
# Index specific source
python3 gateway/imessage_client.py index --source=imessage --days 30

# Semantic search
python3 gateway/imessage_client.py search "query" --json

# AI-formatted context
python3 gateway/imessage_client.py ask "What did John say about the project?"

# Knowledge base stats
python3 gateway/imessage_client.py stats --json
```

## Claude Code Skill

This project includes a skill at `skills/imessage-gateway/SKILL.md` with command mappings for natural language access.

## Troubleshooting

**Commands not working:**
```bash
# Verify CLI works
python3 gateway/imessage_client.py --help

# Check Python path
which python3
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

Core: `chromadb>=0.4.0`, `openai>=1.0.0`, `fuzzywuzzy`, `python-Levenshtein`, `pyobjc-framework-Contacts`

Install: `pip install -r requirements.txt`

## MCP Server (Archived)

The MCP server has been archived to `mcp_server_archive/`. See `mcp_server_archive/ARCHIVED.md` for restoration if needed.

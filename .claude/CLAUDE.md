# CLAUDE.md

This file provides guidance to Claude Code when working with this repository.

## Project Overview

iMessage Gateway CLI for macOS. Send and read iMessages through Claude Code with contact intelligence, fuzzy name matching, and semantic search.

**Architecture: Gateway CLI (MCP-Free)**
- 19x faster than MCP alternatives (40ms vs 763ms)
- Direct Python CLI via Bash tool calls
- 27 commands across messaging, reading, groups, analytics, and RAG

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

# Verify CLI
python3 gateway/imessage_client.py --help
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
                                            └── UnifiedRetriever for semantic search
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

### Path Resolution (Critical)

All paths use absolute resolution from script location:

```python
SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent
```

### macOS Messages Database

Messages are stored in `~/Library/Messages/chat.db` (requires Full Disk Access):

- **text** column: Plain text (older messages)
- **attributedBody** column: Binary blob (macOS Ventura+)

### Contact Resolution

`ContactsManager` provides name → phone lookup:
1. Exact match (case-insensitive)
2. Partial match (contains)
3. Fuzzy matching with fuzzywuzzy (threshold 0.85)

## Key Files

| File | Purpose |
|------|---------|
| `gateway/imessage_client.py` | Gateway CLI entry point (27 commands) |
| `src/messages_interface.py` | AppleScript send + chat.db read |
| `src/contacts_manager.py` | Contact lookup from JSON config |
| `src/rag/unified/retriever.py` | UnifiedRetriever for semantic search |
| `config/contacts.json` | Contact data (gitignored) |
| `skills/imessage-gateway/SKILL.md` | Claude Code skill definition |

## Claude Code Skill

Use `skills/imessage-gateway/SKILL.md` for natural language command mapping.

## Troubleshooting

**"Contact not found":**
```bash
python3 scripts/sync_contacts.py
```

**Messages showing `[message content not available]`:**
- Check Full Disk Access in System Settings
- Some messages are attachment-only

## Dependencies

Core: `chromadb`, `openai`, `fuzzywuzzy`, `python-Levenshtein`, `pyobjc-framework-Contacts`

Install: `pip install -r requirements.txt`

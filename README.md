# iMessage MCP Server

A personalized iMessage MCP (Model Context Protocol) server that lets Claude send and read iMessages on macOS.

## Features

- **Send Messages**: Send iMessages using natural language ("Text John saying I'm running late")
- **Read Messages**: Retrieve recent message history with any contact
- **Smart Contact Lookup**: Find contacts by name with fuzzy matching
- **Cross-Conversation Search**: Search messages across all contacts
- **macOS Contacts Sync**: Auto-sync contacts from your macOS Contacts app

## Requirements

- **macOS** (required - iMessage is macOS only)
- **Python 3.9+**
- **Claude Code** or **Claude Desktop** (MCP client)
- **Full Disk Access** permission (for reading message history)

## Quick Start

### 1. Clone and Install

```bash
git clone https://github.com/yourusername/imessage-mcp.git
cd imessage-mcp

# Install dependencies
pip install -r requirements.txt
```

### 2. Set Up Contacts

```bash
# Option A: Sync from macOS Contacts (recommended)
python3 scripts/sync_contacts.py

# Option B: Manual setup
cp config/contacts.example.json config/contacts.json
# Edit config/contacts.json with your contacts
```

### 3. Grant Permissions

1. **Full Disk Access** (for reading messages):
   - System Settings → Privacy & Security → Full Disk Access
   - Add Terminal.app or your Python interpreter

2. **Automation** (for sending messages):
   - Will be requested automatically on first send

### 4. Register with Claude Code

```bash
# Using Claude Code CLI
claude mcp add -t stdio imessage-mcp -- python3 /path/to/imessage-mcp/mcp_server/server.py

# Then restart Claude Code
```

### 5. Test It Out

In Claude Code, try:
```
List my contacts
```
```
Show my recent messages with John
```
```
Send a message to Jane saying "Hey, are you free for coffee tomorrow?"
```

## Available MCP Tools

| Tool | Description |
|------|-------------|
| `list_contacts` | List all configured contacts |
| `send_message` | Send an iMessage to a contact by name |
| `get_recent_messages` | Get recent messages with a specific contact |
| `get_all_recent_conversations` | Get recent messages across all contacts |
| `search_messages` | Full-text search across all messages |
| `get_messages_by_phone` | Get messages by phone number directly |

## Project Structure

```
imessage-mcp/
├── mcp_server/
│   └── server.py          # MCP server entry point
├── src/
│   ├── messages_interface.py  # iMessage send/read
│   ├── contacts_manager.py    # Contact lookup
│   └── contacts_sync.py       # macOS Contacts sync
├── config/
│   ├── contacts.json          # Your contacts (gitignored)
│   └── contacts.example.json  # Example template
├── scripts/
│   ├── sync_contacts.py       # Sync from macOS Contacts
│   ├── test_mcp_protocol.py   # Test MCP protocol
│   └── test_mcp_tools.py      # Test tool functionality
└── tests/                     # Unit tests
```

## Configuration

### Contact Format

Contacts are stored in `config/contacts.json`:

```json
{
  "contacts": [
    {
      "name": "John Doe",
      "phone": "14155551234",
      "relationship_type": "friend",
      "notes": "Optional notes"
    }
  ]
}
```

Phone numbers can be in any format - they're normalized automatically.

### Server Config

Optional settings in `config/mcp_server.json`:

```json
{
  "logging": {
    "level": "INFO"
  },
  "contacts_sync": {
    "fuzzy_match_threshold": 0.85
  }
}
```

## Troubleshooting

### "Contact not found"
- Run `python3 scripts/sync_contacts.py` to sync contacts
- Check `config/contacts.json` exists and has contacts
- Try partial names (e.g., "John" instead of "John Doe")

### "Permission denied" reading messages
- Grant Full Disk Access to Terminal/Python
- Restart Terminal after granting permission
- Verify: `ls ~/Library/Messages/chat.db`

### Messages show "[message content not available]"
- Some older messages use a different format
- Attachment-only messages don't have text content
- This is normal for some message types

### MCP server not appearing in Claude Code
- Verify registration: `claude mcp list`
- Check Python path: `which python3`
- Restart Claude Code after adding the server

## How It Works

1. **Sending**: Uses AppleScript to control Messages.app
2. **Reading**: Directly queries `~/Library/Messages/chat.db` (SQLite)
3. **Contacts**: Syncs from macOS Contacts via PyObjC framework

## Claude Code Skill (Optional)

This repo includes a Claude Code skill at `.claude/skills/imessage-texting/` with usage examples for each MCP tool.

To use it, clone this repo - Claude Code will automatically pick up the skill from the `.claude/skills/` directory.

## Unified RAG System (Semantic Search)

The server includes a unified RAG (Retrieval-Augmented Generation) system for semantic search across multiple data sources.

### Features

- **Multi-source search**: Search across iMessage, SuperWhisper transcriptions, Notes, Gmail, Slack, and Calendar
- **Incremental indexing**: Only index new messages since last run (35s → <1s for no-op)
- **Unified interface**: Single search interface across all sources

### Available Tools

| Tool | Description |
|------|-------------|
| `index_knowledge` | Index content from sources (imessage, superwhisper, notes, gmail, slack, calendar) |
| `search_knowledge` | Semantic search across indexed sources |
| `knowledge_stats` | Get statistics about indexed content |

### Migration from Old RAG System

If you were using the old RAG system (`ask_messages`, `index_messages`), migrate to the new unified system:

#### 1. Index with new system

```python
# New: Incremental mode (default) - only indexes new messages
index_knowledge(source="imessage", incremental=True)

# Or force full re-index if needed
index_knowledge(source="imessage", incremental=False)
```

#### 2. Migrate old data (optional)

If you have existing indexed data in the old system:

```python
# One-time migration: copies old collection to new
migrate_rag_data()
```

#### 3. Use new search

```python
# Old way (deprecated)
ask_messages(question="What did John say about the meeting?")

# New way (recommended)
search_knowledge(
    query="What did John say about the meeting?",
    sources=["imessage"]
)
```

#### 4. Verify and clean up

After migration:
1. Test search with `search_knowledge(sources=["imessage"])`
2. Verify results are correct
3. Old RAG tools (`ask_messages`, `index_messages`) are deprecated but still functional

### Performance

- **Incremental indexing**: Second index run with no new messages: <1s (vs 35s full re-index)
- **Baseline metrics**: See `benchmarks/results/indexing_baseline.json`
- **Benchmark suite**: Run `python3 -m Texting.benchmarks.run_benchmarks`

## Development

```bash
# Run tests
pytest tests/ -v

# Run specific test suite
pytest tests/test_migration.py -v

# Run performance benchmarks
python3 -m Texting.benchmarks.run_benchmarks

# Test MCP protocol manually
python3 scripts/test_mcp_protocol.py

# Test tools
python3 scripts/test_mcp_tools.py

# Audit old RAG usage
python3 scripts/audit_old_rag.py
```

## Privacy & Security

- All data stays local on your Mac
- No cloud services or external APIs
- Contacts file is gitignored by default
- Message history accessed read-only

## License

MIT License - see [LICENSE](LICENSE) for details.

## Contributing

Contributions welcome! Please open an issue or PR.

---

*Built for use with [Claude Code](https://claude.ai/code) and [Claude Desktop](https://claude.ai/download)*

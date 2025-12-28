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

## Development

```bash
# Run tests
pytest tests/ -v

# Test MCP protocol manually
python3 scripts/test_mcp_protocol.py

# Test tools
python3 scripts/test_mcp_tools.py
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

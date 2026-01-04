---
description: Search, send, and manage iMessages directly from Claude Code
---

# iMessage Gateway

Access your Messages.db without MCP server overhead. macOS only.

## Quick Commands

```bash
# Search messages with a contact
python3 gateway/imessage_client.py search "John" --limit 20

# Send a message
python3 gateway/imessage_client.py send "John" "Running late!"

# Check unread messages
python3 gateway/imessage_client.py unread

# Find messages needing follow-up
python3 gateway/imessage_client.py followup --days 7
```

## Available Commands

| Command | Description |
|---------|-------------|
| `search <contact>` | Search messages with fuzzy contact matching |
| `messages <contact>` | Get conversation with a contact |
| `send <contact> <message>` | Send text via AppleScript |
| `unread` | Check unread messages |
| `recent` | Recent conversations |
| `followup` | Find messages needing reply |
| `contacts` | List all contacts |
| `analytics` | Conversation statistics |

## Requirements

- macOS (Messages.app integration)
- Python 3.9+
- Full Disk Access for Terminal (System Settings → Privacy → Full Disk Access)
- Contacts synced to `config/contacts.json`

## Why Gateway Pattern?

MCP servers load into every Claude Code session (~1-2s startup + context tokens).

Gateway pattern: standalone Python CLI, invoked via Bash only when needed.

**Zero overhead until you actually use it.**

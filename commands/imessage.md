---
description: Search, send, and manage iMessages directly from Claude Code
---

# iMessage Gateway

Access your Messages.db without MCP server overhead. macOS only.

## Quick Commands

```bash
# Search messages with a contact
python3 ${CLAUDE_PLUGIN_ROOT}/gateway/imessage_client.py search "John" --limit 20

# Send a message
python3 ${CLAUDE_PLUGIN_ROOT}/gateway/imessage_client.py send "John" "Running late!"

# Check unread messages
python3 ${CLAUDE_PLUGIN_ROOT}/gateway/imessage_client.py unread

# Find messages needing follow-up
python3 ${CLAUDE_PLUGIN_ROOT}/gateway/imessage_client.py followup --days 7
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
| `groups` | List group chats |
| `group-messages` | Read group messages |
| `attachments` | Get photos/videos/files |
| `voice` | Get voice messages |
| `links` | Extract shared URLs |
| `reactions` | Get tapbacks/emoji reactions |

## Requirements

- macOS (Messages.app integration)
- Python 3.9+
- Full Disk Access for Terminal (System Settings -> Privacy -> Full Disk Access)
- Contacts synced to `${CLAUDE_PLUGIN_ROOT}/config/contacts.json`

## Setup After Installation

```bash
# Sync contacts from macOS Contacts.app
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/sync_contacts.py

# Install dependencies
pip install -r ${CLAUDE_PLUGIN_ROOT}/requirements.txt
```

## Why Gateway Pattern?

MCP servers load into every Claude Code session (~763ms startup + context tokens).

Gateway pattern: standalone Python CLI, invoked via Bash only when needed.

**19x faster. Zero overhead until you actually use it.**

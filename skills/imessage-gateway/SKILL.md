---
name: imessage-gateway
description: On-demand iMessage access without MCP overhead. Use when user wants to search messages, check conversations, send texts, or find follow-ups on macOS.
version: 1.0.0
---

# iMessage Gateway (Zero MCP Overhead)

Standalone CLI for iMessage operations. No MCP server required - queries Messages.db directly via Python.

## When to Use

**Trigger on DIRECT communication intent:**
- "Check messages with [name]"
- "What did [name] say about..."
- "Text [name]..."
- "Who needs a reply?"
- "Search my messages for..."

**Require action verbs:** check, search, text, message, find

## Quick Reference

| Command | Purpose | Example |
|---------|---------|---------|
| `search` | Find messages with contact | `search "John" --query "meeting"` |
| `messages` | Get conversation with contact | `messages "John" --limit 20` |
| `recent` | Recent conversations | `recent --limit 10` |
| `unread` | Unread messages | `unread` |
| `send` | Send a message | `send "John" "Running late!"` |
| `contacts` | List all contacts | `contacts` |
| `followup` | Find messages needing reply | `followup --days 7` |
| `analytics` | Conversation stats | `analytics "Sarah" --days 30` |

## Usage

All commands use the gateway CLI:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/gateway/imessage_client.py <command> [args]
```

### Search Messages

```bash
# All messages with John
python3 ${CLAUDE_PLUGIN_ROOT}/gateway/imessage_client.py search "John"

# Messages containing "meeting"
python3 ${CLAUDE_PLUGIN_ROOT}/gateway/imessage_client.py search "John" --query "meeting"

# Last 50 messages
python3 ${CLAUDE_PLUGIN_ROOT}/gateway/imessage_client.py search "John" --limit 50
```

### Get Conversation

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/gateway/imessage_client.py messages "John" --limit 10
python3 ${CLAUDE_PLUGIN_ROOT}/gateway/imessage_client.py messages "John" --json
```

### Check Unread

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/gateway/imessage_client.py unread
```

### Send Message

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/gateway/imessage_client.py send "John" "Running late!"
python3 ${CLAUDE_PLUGIN_ROOT}/gateway/imessage_client.py send "Mom" "Happy birthday!"
```

### Find Follow-ups

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/gateway/imessage_client.py followup --days 7 --stale 2
```

### Analytics

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/gateway/imessage_client.py analytics "Sarah" --days 30
python3 ${CLAUDE_PLUGIN_ROOT}/gateway/imessage_client.py analytics --days 7  # All contacts
```

## Contact Resolution

Contact names are fuzzy-matched from `${CLAUDE_PLUGIN_ROOT}/config/contacts.json`:

- "John" -> "John Doe" (first match)
- "ang" -> "Angus Smith" (partial match)
- Case insensitive

## Output Formats

The following commands support `--json` for structured output: `messages`, `recent`, `unread`, `contacts`, `analytics`, `followup`.

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/gateway/imessage_client.py messages "John" --json | jq '.[] | .text'
```

## Benefits Over MCP

| Aspect | MCP Server | Gateway Script |
|--------|------------|----------------|
| Startup overhead | ~763ms | ~40ms |
| Context tokens | ~3k tokens | ~0 (Bash only) |
| Always running | Yes | No |
| Complexity | Higher | Simple CLI |

**19x faster execution with 80% fewer tokens.**

## Requirements

- macOS (Messages.app integration)
- Python 3.9+
- Full Disk Access permission for Terminal
- Contacts synced to `${CLAUDE_PLUGIN_ROOT}/config/contacts.json`

## Setup After Installation

```bash
# Sync contacts from macOS Contacts.app
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/sync_contacts.py

# Install dependencies
pip install -r ${CLAUDE_PLUGIN_ROOT}/requirements.txt
```

## Troubleshooting

**"Contact not found"**
- Run `contacts` command to list available names
- Contacts loaded from `${CLAUDE_PLUGIN_ROOT}/config/contacts.json`

**"Could not import modules"**
- Ensure dependencies are installed: `pip install -r ${CLAUDE_PLUGIN_ROOT}/requirements.txt`

**No messages shown**
- Check Full Disk Access for Terminal
- Messages.db location: `~/Library/Messages/chat.db`

---

**Platform:** macOS only
**Token Cost:** ~0 (Bash execution only)

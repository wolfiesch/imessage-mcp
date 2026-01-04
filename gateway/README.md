# iMessage Gateway CLI

Standalone CLI for iMessage operations without running the MCP server. Zero overhead, on-demand access.

## Why Use This?

| Aspect | MCP Server | Gateway CLI |
|--------|------------|-------------|
| Startup overhead | ~1-2s every session | 0 (on-demand) |
| Always running | Yes | No |
| Integration | Claude Code MCP | Any shell/script |

## Quick Start

```bash
# From repo root
python3 gateway/imessage_client.py search "John" --limit 10
python3 gateway/imessage_client.py unread
python3 gateway/imessage_client.py send "Mom" "Happy birthday!"
```

### Go Implementation (experimental)

Prefer Go? A lightweight Go version of the gateway lives in `gateway/go` with zero external dependencies (uses the `sqlite3` CLI and AppleScript).

```bash
cd gateway/go
go build -o imessage-gateway

# Example commands (from repo root or any directory)
./gateway/go/imessage-gateway search "John" --limit 20
./gateway/go/imessage-gateway recent --json --db ~/Library/Messages/chat.db
./gateway/go/imessage-gateway send "Mom" "On my way!"
```

## Commands

| Command | Description | Example |
|---------|-------------|---------|
| `search` | Search messages with contact | `search "John" --query "meeting"` |
| `messages` | Get conversation with contact | `messages "John" --limit 20` |
| `recent` | Recent conversations | `recent --limit 10` |
| `unread` | Unread messages | `unread` |
| `send` | Send a message | `send "John" "On my way!"` |
| `contacts` | List all contacts | `contacts --json` |
| `analytics` | Conversation stats | `analytics "Sarah" --days 30` |
| `followup` | Find messages needing reply | `followup --days 7` |

## Usage Examples

### Search Messages

```bash
# All messages with Angus
python3 gateway/imessage_client.py search "Angus"

# Messages containing "SF"
python3 gateway/imessage_client.py search "Angus" --query "SF"

# Last 50 messages
python3 gateway/imessage_client.py search "Angus" --limit 50
```

### Get Conversation

```bash
python3 gateway/imessage_client.py messages "John" --limit 10
python3 gateway/imessage_client.py messages "John" --json  # JSON output
```

### Check Unread

```bash
python3 gateway/imessage_client.py unread
```

### Send Message

```bash
python3 gateway/imessage_client.py send "John" "Running late!"
python3 gateway/imessage_client.py send "Mom" "Happy birthday!"
```

### Find Follow-ups Needed

```bash
python3 gateway/imessage_client.py followup --days 7 --stale 2
```

## Contact Resolution

Contact names are fuzzy-matched from `config/contacts.json`:

- "John" → "John Doe" (first match)
- "ang" → "Angus Smith" (partial match)
- Case insensitive

## JSON Output

All commands support `--json` for structured output:

```bash
python3 gateway/imessage_client.py messages "John" --json | jq '.[] | .text'
```

## Claude Code Integration

Add to your skill file to use from Claude Code:

```bash
# In your SKILL.md, use Bash commands like:
python3 ~/path/to/imessage-mcp/gateway/imessage_client.py search "Contact" --limit 20
```

## Requirements

- macOS (Messages.app integration)
- Python 3.9+
- Full Disk Access for Terminal (System Settings → Privacy → Full Disk Access)
- Contacts synced to `config/contacts.json`

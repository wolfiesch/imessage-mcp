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

## C++ Gateway (Experimental)

Prefer a native binary? Build the C++ version located in `gateway/cpp`:

```bash
cd gateway/cpp
cmake -B build -S .
cmake --build build

# Usage
./build/imessage_gateway contacts
./build/imessage_gateway messages "John" --limit 10 --json
./build/imessage_gateway send "Mom" "Hello from C++!"
```

The C++ gateway mirrors the Python commands (search, messages, recent, unread, send, contacts, analytics, followup) and reads the same `config/contacts.json` for contact resolution. It queries `~/Library/Messages/chat.db` directly and uses `osascript` for sending.

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

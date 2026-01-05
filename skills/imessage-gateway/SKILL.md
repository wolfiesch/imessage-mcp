---
name: imessage-gateway
description: Complete iMessage CLI with semantic search. The only interface needed for iMessage on macOS. 19x faster than MCP.
version: 4.0.0
---

# EXECUTE IMMEDIATELY

**ARGUMENTS:** {{ARGUMENTS}}

When arguments are provided, execute via Bash NOW. Add `--json` flag for data retrieval commands:

```bash
python3 ${SKILL_PATH}/../../gateway/imessage_client.py {{ARGUMENTS}}
```

If no arguments provided, show the Reference section below.

## Command Mapping (use FIRST match)

### Messaging & Reading

| User says | Execute |
|-----------|---------|
| `recent <N>` | `recent --limit <N> --json` (default: 50) |
| `find <contact> [for "<query>"]` | `find "<contact>" [--query "<query>"] --limit 50 --json` |
| `messages <name>` / `from <name>` | `messages "<name>" --limit 20 --json` |
| `unread` | `unread --json` |
| `send <name> <message>` | `send "<name>" "<message>"` (no --json) |
| `send-by-phone <phone> <message>` | `send-by-phone "<phone>" "<message>"` |

### Groups & Media

| User says | Execute |
|-----------|---------|
| `groups` | `groups --json` |
| `attachments [<contact>]` | `attachments ["<contact>"] --json` |
| `voice [<contact>]` | `voice ["<contact>"] --json` |
| `links [<days>]` | `links --days <N> --json` (default: 30) |

### Analytics & Discovery

| User says | Execute |
|-----------|---------|
| `analytics [<contact>] [<days>]` | `analytics ["<contact>"] --days <N> --json` (default: 30) |
| `followup [<days>]` | `followup --days <N> --json` (default: 7) |
| `contacts` | `contacts --json` |
| `handles [<days>]` | `handles --days <N> --json` (default: 30) |
| `unknown [<days>]` | `unknown --days <N> --json` (default: 7) |
| `summary <name> [<days>]` | `summary "<name>" --days <N> --json` (default: 7) |

### Semantic Search (RAG)

| User says | Execute |
|-----------|---------|
| `search "<query>"` | `search "<query>" --json` |
| `ask "<question>"` | `ask "<question>" --json` |
| `index [<source>]` | `index --source=<source> --json` (imessage, superwhisper, notes, local) |
| `stats` | `stats --json` |
| `sources` | `sources --json` |
| `clear [<source>]` | `clear [--source=<source>] --force --json` |

---

## Reference (shown when no arguments provided)

### Performance

| Operation | Gateway CLI | Old MCP | Speedup |
|-----------|-------------|---------|---------|
| List contacts | 40ms | ~763ms | **19x** |
| Find messages | 43ms | ~763ms | **18x** |
| Unread messages | 44ms | ~763ms | **17x** |
| Groups | 61ms | ~763ms | **12x** |
| Analytics | 129ms | ~850ms | **7x** |
| Semantic search | 150ms | ~900ms | **6x** |

### All Commands (27 total)

**Messaging (3)**
- `send <contact> <message>` - Send to contact
- `send-by-phone <phone> <message>` - Send to phone number
- `add-contact <name> <phone>` - Add contact

**Reading (12)**
- `messages`, `find`, `recent`, `unread`, `handles`, `unknown`
- `attachments`, `voice`, `links`, `thread`, `scheduled`, `summary`

**Groups (2)**
- `groups`, `group-messages`

**Analytics (3)**
- `analytics`, `followup`, `reactions`

**Contacts (1)**
- `contacts`

**Semantic Search/RAG (6)**
- `index` - Index content for semantic search
- `search` - Semantic search across indexed content
- `ask` - Get AI-formatted context
- `stats` - Knowledge base statistics
- `sources` - List available/indexed sources
- `clear` - Clear indexed data

### Full Command Examples

```bash
# Recent messages
python3 ${SKILL_PATH}/../../gateway/imessage_client.py recent --limit 50 --json

# Find messages with contact (keyword search)
python3 ${SKILL_PATH}/../../gateway/imessage_client.py find "John" --query "meeting" --limit 50 --json

# Messages from contact
python3 ${SKILL_PATH}/../../gateway/imessage_client.py messages "Ever" --limit 20 --json

# Unread messages
python3 ${SKILL_PATH}/../../gateway/imessage_client.py unread --json

# Send message
python3 ${SKILL_PATH}/../../gateway/imessage_client.py send "Sarah" "Running late!"

# Send directly to phone number
python3 ${SKILL_PATH}/../../gateway/imessage_client.py send-by-phone +14155551234 "Hi there!"

# Analytics for specific contact
python3 ${SKILL_PATH}/../../gateway/imessage_client.py analytics "John" --days 30 --json

# Follow-ups needed
python3 ${SKILL_PATH}/../../gateway/imessage_client.py followup --days 7 --json

# List groups
python3 ${SKILL_PATH}/../../gateway/imessage_client.py groups --json

# Semantic search (RAG)
python3 ${SKILL_PATH}/../../gateway/imessage_client.py search "dinner plans with Sarah" --json

# Index iMessages for semantic search
python3 ${SKILL_PATH}/../../gateway/imessage_client.py index --source=imessage --days 30

# Index all local sources (SuperWhisper + Notes)
python3 ${SKILL_PATH}/../../gateway/imessage_client.py index --source=local

# Ask a question (AI-formatted context)
python3 ${SKILL_PATH}/../../gateway/imessage_client.py ask "What restaurant did Sarah recommend?"

# Knowledge base stats
python3 ${SKILL_PATH}/../../gateway/imessage_client.py stats --json

# List available sources
python3 ${SKILL_PATH}/../../gateway/imessage_client.py sources --json
```

### Contact Resolution

Names are fuzzy-matched from `config/contacts.json`:
- "John" → "John Doe" (first match)
- "ang" → "Angus Smith" (partial)
- Case insensitive

### Requirements

- macOS with Messages.app
- Python 3.9+
- Full Disk Access for Terminal
- Contacts synced via `scripts/sync_contacts.py`
- For RAG: OpenAI API key (OPENAI_API_KEY) or local embeddings

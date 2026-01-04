---
name: imessage-gateway
description: High-performance iMessage CLI (19x faster than MCP). Use for messaging operations on macOS.
version: 3.1.0
---

# EXECUTE IMMEDIATELY

**ARGUMENTS:** {{ARGUMENTS}}

When arguments are provided, execute via Bash NOW - do not just return this doc:

```bash
python3 ${SKILL_PATH}/../../gateway/imessage_client.py {{ARGUMENTS}} --json
```

## Command Mapping (use FIRST match)

| User says | Execute |
|-----------|---------|
| `recent [N]` | `recent --limit N` (default 50) |
| `search "query"` | `search "query" --limit 50` |
| `messages "name"` / `from "name"` | `messages "name" --limit 20` |
| `unread` | `unread` |
| `send "name" "msg"` | `send "name" "msg"` |
| `analytics [days]` | `analytics --days N` (default 30) |
| `followup [days]` | `followup --days N` (default 7) |
| `groups` | `groups` |
| `contacts` | `contacts` |
| `attachments` | `attachments --json` |
| `voice` | `voice --json` |
| `links [days]` | `links --days N` (default 30) |
| `handles [days]` | `handles --days N` (default 30) |
| `unknown [days]` | `unknown --days N` (default 7) |
| `summary "name" [days]` | `summary "name" --days N` (default 7) |

**`--days` compatibility:**
- Works with: `analytics`, `followup`, `links`, `handles`, `unknown`, `summary`
- Does NOT work with: `recent`, `search`, `messages`, `unread`, `groups`

---

## Reference (only if no args provided)

### Performance

| Operation | Gateway CLI | MCP Tool | Speedup |
|-----------|-------------|----------|---------|
| List contacts | 40ms | ~763ms | **19x** |
| Search messages | 43ms | ~763ms | **18x** |
| Unread messages | 44ms | ~763ms | **17x** |
| Groups | 61ms | ~763ms | **12x** |
| Analytics | 129ms | ~850ms | **7x** |

### Full Command Examples

```bash
# Recent messages
python3 ${SKILL_PATH}/../../gateway/imessage_client.py recent --limit 50 --json

# Search messages
python3 ${SKILL_PATH}/../../gateway/imessage_client.py search "dinner" --limit 50 --json

# Messages from contact
python3 ${SKILL_PATH}/../../gateway/imessage_client.py messages "Ever" --limit 20 --json

# Unread messages
python3 ${SKILL_PATH}/../../gateway/imessage_client.py unread --json

# Send message
python3 ${SKILL_PATH}/../../gateway/imessage_client.py send "Sarah" "Running late!"

# Analytics
python3 ${SKILL_PATH}/../../gateway/imessage_client.py analytics --days 30 --json

# Follow-ups needed
python3 ${SKILL_PATH}/../../gateway/imessage_client.py followup --days 7 --json

# List groups
python3 ${SKILL_PATH}/../../gateway/imessage_client.py groups --json

# Contacts
python3 ${SKILL_PATH}/../../gateway/imessage_client.py contacts --json
```

### When to Use MCP Instead

Use MCP tools (`imessage-texting` skill) only for:
- RAG/semantic search: `index_knowledge`, `search_knowledge`, `ask_messages`
- Features not in gateway CLI

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

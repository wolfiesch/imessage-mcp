---
name: imessage-texting
description: Send and read iMessages through Claude. Use when the user wants to text someone, check messages, search conversations, view group chats, or analyze messaging patterns on macOS.
version: 1.2.0
---

# iMessage Texting Skill

Send and read iMessages using the `imessage-mcp` MCP server.

## Available Tools

### Core Messaging

| Tool | Description |
|------|-------------|
| `list_contacts` | List all configured contacts |
| `send_message` | Send iMessage by contact name |
| `get_recent_messages` | Get messages with a specific contact |
| `get_all_recent_conversations` | Get recent messages across all contacts |
| `search_messages` | Full-text search across messages |
| `get_messages_by_phone` | Get messages by phone number |

### Group Chats

| Tool | Description |
|------|-------------|
| `list_group_chats` | List all group chat conversations with participants |
| `get_group_messages` | Get messages from a specific group chat |

### T0 Features (Quick Access)

| Tool | Description |
|------|-------------|
| `get_attachments` | Get photos, videos, files from messages |
| `get_unread_messages` | Get unread messages awaiting response |
| `get_reactions` | Get tapbacks/reactions (love, like, laugh, etc.) |
| `get_conversation_analytics` | Message patterns, frequency, top contacts |

### T1 Features (Advanced)

| Tool | Description |
|------|-------------|
| `get_message_thread` | Follow reply chains and inline replies |
| `extract_links` | Get URLs shared in conversations |
| `get_voice_messages` | Get voice/audio messages with file paths |
| `get_scheduled_messages` | View queued/scheduled messages (read-only) |

## Usage Examples

### Core Messaging

**Send a message:**
```
Tool: send_message
Arguments: { "contact_name": "John", "message": "Running late!" }
```

**Check recent messages:**
```
Tool: get_recent_messages
Arguments: { "contact_name": "Sarah", "limit": 10 }
```

**Search conversations:**
```
Tool: search_messages
Arguments: { "query": "dinner" }
```

**Get all recent conversations:**
```
Tool: get_all_recent_conversations
Arguments: { "limit": 20 }
```

**Message by phone number:**
```
Tool: get_messages_by_phone
Arguments: { "phone_number": "+14155551234" }
```

### Group Chats

**List all group chats:**
```
Tool: list_group_chats
Arguments: { "limit": 10 }
```
Returns group names, participants, message counts, and group IDs.

**Read messages from a group:**
```
Tool: get_group_messages
Arguments: { "group_id": "chat152668864985555509", "limit": 50 }
```

**Find groups by participant:**
```
Tool: get_group_messages
Arguments: { "participant": "+14155551234", "limit": 20 }
```

### Attachments & Media

**Get all image attachments:**
```
Tool: get_attachments
Arguments: { "mime_type": "image/", "limit": 20 }
```

**Get attachments from specific contact:**
```
Tool: get_attachments
Arguments: { "contact_name": "John", "limit": 10 }
```

**Get voice messages:**
```
Tool: get_voice_messages
Arguments: { "limit": 20 }
```
Returns file paths that can be passed to transcription services.

### Inbox Management

**Check unread messages:**
```
Tool: get_unread_messages
Arguments: { "limit": 50 }
```
Shows messages awaiting response with age (days old).

**View scheduled messages:**
```
Tool: get_scheduled_messages
Arguments: {}
```

### Reactions & Engagement

**Get all reactions:**
```
Tool: get_reactions
Arguments: { "limit": 50 }
```

**Get reactions with specific contact:**
```
Tool: get_reactions
Arguments: { "contact_name": "Sarah", "limit": 20 }
```
Shows who reacted (love/like/laugh/etc.) to which messages.

### Analytics & Insights

**Get messaging analytics for all contacts:**
```
Tool: get_conversation_analytics
Arguments: { "days": 30 }
```
Returns total messages, sent/received, busiest times, top contacts.

**Analyze specific relationship:**
```
Tool: get_conversation_analytics
Arguments: { "contact_name": "John", "days": 90 }
```

### Links & Threading

**Extract shared links:**
```
Tool: extract_links
Arguments: { "days": 7, "limit": 50 }
```

**Follow a reply thread:**
```
Tool: get_message_thread
Arguments: { "message_guid": "p:0/...", "limit": 20 }
```

## Contact Lookup

The server supports flexible matching:
- Exact: "John Doe"
- Partial: "John"
- Case insensitive: "john doe"
- Fuzzy: handles typos (85% threshold)

If contact not found, run `python3 scripts/sync_contacts.py` to sync from macOS Contacts.

## Troubleshooting

| Error | Solution |
|-------|----------|
| "Contact not found" | Sync contacts or add to `config/contacts.json` |
| "Permission denied" | Grant Full Disk Access in System Settings |
| MCP tools not visible | Run `claude mcp list` to verify registration |
| No attachments/voice found | Check Full Disk Access for Messages.app |

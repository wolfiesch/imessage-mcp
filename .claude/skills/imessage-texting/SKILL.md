---
name: imessage-texting
description: Send and read iMessages through Claude. Use when the user wants to text someone, check messages, search conversations, or view group chats on macOS.
version: 1.1.0
---

# iMessage Texting Skill

Send and read iMessages using the `imessage-mcp` MCP server.

## Available Tools

| Tool | Description |
|------|-------------|
| `list_contacts` | List all configured contacts |
| `send_message` | Send iMessage by contact name |
| `get_recent_messages` | Get messages with a specific contact |
| `get_all_recent_conversations` | Get recent messages across all contacts |
| `search_messages` | Full-text search across messages |
| `get_messages_by_phone` | Get messages by phone number |
| `list_group_chats` | List all group chat conversations |
| `get_group_messages` | Get messages from a specific group chat |

## Usage Examples

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

## Group Chat Examples

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
Use the group_id from list_group_chats results.

**Find groups by participant:**
```
Tool: get_group_messages
Arguments: { "participant": "+14155551234", "limit": 20 }
```
Returns messages from all groups containing this participant.

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

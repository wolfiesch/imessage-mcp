---
name: imessage-texting
description: Send and read iMessages through Claude. Use when the user wants to text someone, check recent messages, search conversations, or manage their iMessage contacts on macOS.
version: 1.0.0
---

# iMessage Texting Skill

Send and read iMessages directly through Claude using the local MCP server. This skill wraps the `imessage-life-planner` MCP server tools.

## When to Use This Skill

- User wants to send a text message to someone
- User wants to check their recent messages/texts
- User wants to search their message history
- User asks about conversations with specific contacts
- User wants to see who they've been texting recently

## Available MCP Tools

The following tools are available via the `mcp__imessage-life-planner__*` namespace:

| Tool | Description |
|------|-------------|
| `list_contacts` | List all configured contacts |
| `send_message` | Send an iMessage to a contact by name |
| `get_recent_messages` | Get recent messages with a specific contact |
| `get_all_recent_conversations` | Get recent messages across ALL contacts |
| `search_messages` | Full-text search across all messages |
| `get_messages_by_phone` | Get messages by phone number (no contact needed) |

## Workflows

### 1. Send a Message

**User says:** "Text John saying I'm running late"

```
Step 1: Find contact
Tool: mcp__imessage-life-planner__list_contacts
→ Verify contact exists and get their info

Step 2: Send message
Tool: mcp__imessage-life-planner__send_message
Arguments: { "contact_name": "John", "message": "Hey! Running late, be there in 10" }
→ Confirm message sent
```

**Always confirm before sending:** Show the user the message you're about to send and ask for confirmation.

### 2. Check Recent Messages

**User says:** "What did Sarah text me?"

```
Tool: mcp__imessage-life-planner__get_recent_messages
Arguments: { "contact_name": "Sarah", "limit": 10 }
→ Display recent conversation
```

### 3. Search Conversations

**User says:** "Did anyone text me about dinner this week?"

```
Tool: mcp__imessage-life-planner__search_messages
Arguments: { "query": "dinner", "days_back": 7 }
→ Show matching messages across all contacts
```

### 4. Check All Recent Conversations

**User says:** "Show me my recent texts" or "Who texted me today?"

```
Tool: mcp__imessage-life-planner__get_all_recent_conversations
Arguments: { "limit": 5, "messages_per_contact": 3 }
→ Show recent messages across all active conversations
```

### 5. Message Unknown Number

**User says:** "Check messages from 415-555-1234"

```
Tool: mcp__imessage-life-planner__get_messages_by_phone
Arguments: { "phone_number": "+14155551234" }
→ Get messages without needing a contact entry
```

## Contact Resolution

The MCP server supports flexible contact lookup:
- **Exact name:** "John Doe"
- **Partial name:** "John" (matches first John found)
- **Case insensitive:** "john doe" works
- **Fuzzy matching:** Handles typos with 85% similarity threshold

If a contact isn't found, suggest:
1. Run `python3 scripts/sync_contacts.py` to sync from macOS Contacts
2. Or add them to `config/contacts.json`

## Message Drafting Guidelines

When composing messages for users:

1. **Match their style** - Keep it casual unless they indicate otherwise
2. **Be concise** - Texts should be natural, not essay-length
3. **No AI formality** - Avoid phrases like "I hope this message finds you well"
4. **Confirm first** - Always show the draft and get approval before sending

**Good examples:**
- "Running 10 mins late!"
- "Hey, you free for coffee tomorrow?"
- "Thanks for the info!"

**Avoid:**
- "Dear John, I wanted to reach out regarding..."
- "I hope this message finds you well. I am writing to inform you..."

## Error Handling

| Error | Likely Cause | Solution |
|-------|--------------|----------|
| "Contact not found" | Name not in contacts | Sync contacts or add manually |
| "Message content not available" | Old message format | Normal for some messages |
| "Permission denied" | Full Disk Access needed | Grant in System Settings |
| MCP tools not visible | Server not registered | Run `claude mcp list` to verify |

## Sync Contacts

If contacts are missing or outdated:

```bash
# Sync from macOS Contacts app
python3 scripts/sync_contacts.py
```

Then restart Claude Code to reload the MCP server.

## Privacy Note

- All data stays local on your Mac
- Messages are read from ~/Library/Messages/chat.db
- Messages are sent via AppleScript to Messages.app
- No cloud services or external APIs are used

---

*This skill requires the imessage-life-planner MCP server to be running.*

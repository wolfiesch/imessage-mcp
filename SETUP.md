# Setup Guide - iMessage MCP Server

This guide will help you set up the iMessage MCP server for use with Claude Code.

## Prerequisites

- macOS (required for iMessage)
- Python 3.9 or higher
- iMessage configured and working
- Claude Code installed

## Step 1: Install Dependencies

```bash
cd /path/to/imessage-mcp

# Install Python dependencies
pip install -r requirements.txt
```

## Step 2: Configure Contacts

For Sprint 1, contacts are manually configured in a JSON file.
(Sprint 2 will add automatic sync from macOS Contacts)

Edit `config/contacts.json`:

```json
{
  "contacts": [
    {
      "name": "John Doe",
      "phone": "+14155551234",
      "relationship_type": "friend",
      "notes": "Optional notes about this contact"
    },
    {
      "name": "Jane Smith",
      "phone": "4155555678",
      "relationship_type": "colleague",
      "notes": ""
    }
  ]
}
```

**Phone number format:**
- Include country code (e.g., `+1` for US)
- Or just 10 digits (will be matched flexibly)
- Examples: `+14155551234`, `4155551234`, `(415) 555-1234`

## Step 3: Grant macOS Permissions

### Full Disk Access (for reading message history)

1. Open **System Settings** → **Privacy & Security** → **Full Disk Access**
2. Click the **+** button
3. Add one of:
   - **Terminal.app** (if running from terminal)
   - **Python interpreter** (e.g., `/usr/local/bin/python3`)
   - **Claude Code** (if available)
4. Restart Terminal after granting permission

### AppleScript Permissions (for sending messages)

- Will be requested automatically on first message send
- Grant permission when prompted

## Step 4: Register MCP Server with Claude Code

Add the following to your Claude Code MCP configuration:

**File:** `~/.claude/mcp_settings.json`

```json
{
  "mcpServers": {
    "imessage-mcp": {
      "command": "python3",
      "args": [
        "/path/to/imessage-mcp/mcp_server/server.py"
      ],
      "env": {}
    }
  }
}
```

**Using Claude Code CLI (recommended):**

```bash
# Register the MCP server using the CLI
claude mcp add -t stdio imessage-mcp -- python3 /path/to/imessage-mcp/mcp_server/server.py
```

## Step 5: Test the Server

### Manual Test (without Claude Code)

You can test the server is working:

```bash
cd /path/to/imessage-mcp

# This will start the server and wait for input
python3 mcp_server/server.py
```

Look for log output indicating server started successfully.

### Test with Claude Code

1. **Restart Claude Code** to load the new MCP server
2. In Claude Code, ask:
   ```
   List my contacts
   ```
3. You should see the contacts from your `config/contacts.json`

4. Try sending a test message:
   ```
   Send a test message to [Contact Name] saying "Testing iMessage MCP!"
   ```

## Troubleshooting

### "Contact not found"

**Problem:** Claude says contact doesn't exist

**Solutions:**
- Check spelling matches exactly what's in `config/contacts.json`
- Use partial names (e.g., "John" instead of "John Doe")
- Run: `List my contacts` to see all available contacts

### "Permission denied" accessing Messages database

**Problem:** Can't read message history

**Solutions:**
- Grant Full Disk Access (see Step 3)
- Restart Terminal/Claude Code after granting permission
- Verify path exists: `ls ~/Library/Messages/chat.db`

### "AppleScript error" when sending

**Problem:** Message fails to send

**Solutions:**
- Ensure Messages.app is running
- Grant AppleScript automation permission when prompted
- Try sending a test message manually in Messages.app first
- Check phone number format in contacts.json

### MCP server not showing up in Claude Code

**Problem:** Tools not available

**Solutions:**
- Verify `mcp_settings.json` path is correct
- Check Python path: `which python` or `which python3`
- Update the `command` in mcp_settings.json to match your Python
- Restart Claude Code completely
- Check logs: `tail -f logs/mcp_server.log`

### Messages app automation not working

**Problem:** AppleScript can't control Messages

**Solutions:**
- System Settings → Privacy & Security → Automation
- Enable Terminal.app or Python to control Messages.app
- Make sure you're sending to a valid iMessage contact

## Verification Checklist

- [ ] Dependencies installed (`pip install -r requirements.txt`)
- [ ] At least one contact configured in `config/contacts.json`
- [ ] Full Disk Access granted
- [ ] MCP server registered in `~/.claude/mcp_settings.json`
- [ ] Claude Code restarted
- [ ] Can list contacts via Claude Code
- [ ] Can send test message successfully

## Next Steps

Once Sprint 1 is working:

- **Sprint 2:** Automatic contact sync from macOS Contacts
- **Sprint 3:** Learn your texting style from message history
- **Sprint 4:** Context-aware message drafting using life planner data

## Getting Help

Check the logs for detailed error messages:

```bash
tail -f logs/mcp_server.log
```

Common log locations:
- MCP Server: `logs/mcp_server.log`
- Claude Code: Check Claude Code's log output

---

*Updated: 12/12/2025*

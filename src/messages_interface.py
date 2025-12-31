"""
macOS Messages integration for iMessage MCP server.

Provides interface to send messages via AppleScript and read message history
from the Messages database (chat.db).

Sprint 1: Basic AppleScript sending
Sprint 1.5: Message history reading with attributedBody parsing (macOS Ventura+)
"""

import subprocess
import sqlite3
import logging
import plistlib
import re
from pathlib import Path
from typing import Optional, List, Dict, Tuple
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


def escape_applescript_string(s: str) -> str:
    r"""
    Escape a string for safe use in AppleScript.

    AppleScript strings use backslash escapes, so we must:
    1. Escape backslashes first (\ -> \\)
    2. Then escape double quotes (" -> \")

    This prevents injection attacks where user data could break out of
    the quoted string context in AppleScript commands.

    Args:
        s: The string to escape

    Returns:
        Escaped string safe for AppleScript double-quoted strings
    """
    if s is None:
        return ""
    # Escape backslashes first, then quotes
    return s.replace('\\', '\\\\').replace('"', '\\"')


def is_group_chat_identifier(chat_identifier: Optional[str]) -> bool:
    """
    Check if a chat_identifier indicates a group chat.

    Group chat identifiers in macOS Messages typically:
    - Start with 'chat' followed by numbers (e.g., 'chat152668864985555509')
    - Or contain multiple handles separated by commas

    Args:
        chat_identifier: The chat identifier from cache_roomnames or chat table

    Returns:
        True if this is a group chat identifier, False otherwise
    """
    if not chat_identifier:
        return False

    # Group chats have identifiers like 'chat123456789'
    if chat_identifier.startswith('chat') and chat_identifier[4:].isdigit():
        return True

    # Or contain multiple comma-separated handles
    if ',' in chat_identifier:
        return True

    return False


def parse_attributed_body(blob: bytes) -> Optional[str]:
    """
    Parse the attributedBody column from macOS Messages database.

    macOS Ventura+ stores message content as a binary plist containing
    an NSKeyedArchiver-encoded NSAttributedString.

    Args:
        blob: Raw bytes from the attributedBody column

    Returns:
        Extracted text string or None if parsing fails
    """
    if not blob:
        return None

    try:
        # attributedBody can be either:
        # 1. bplist (NSKeyedArchiver) format - newer
        # 2. streamtyped format - used in macOS Messages
        # This function only handles bplist format
        bplist_start = blob.find(b'bplist')
        if bplist_start == -1:
            # Not a bplist format - let caller try other methods
            return None

        # Extract the bplist portion
        plist_data = blob[bplist_start:]

        # Parse the binary plist
        plist = plistlib.loads(plist_data)

        # NSKeyedArchiver format has $objects array containing the data
        if isinstance(plist, dict) and '$objects' in plist:
            objects = plist['$objects']

            # The text is usually stored as an NSString in the objects array
            # Look for the longest string that isn't a class name
            text_candidates = []
            for obj in objects:
                if isinstance(obj, str):
                    # Skip class names and metadata
                    if not obj.startswith('NS') and not obj.startswith('$') and len(obj) > 0:
                        text_candidates.append(obj)
                elif isinstance(obj, dict):
                    # Sometimes text is in NS.string key
                    if 'NS.string' in obj:
                        text_candidates.append(obj['NS.string'])
                    elif 'NS.bytes' in obj:
                        # Try to decode bytes
                        try:
                            text_candidates.append(obj['NS.bytes'].decode('utf-8'))
                        except (UnicodeDecodeError, AttributeError):
                            pass

            # Return the first substantial text found
            for text in text_candidates:
                if text and len(text.strip()) > 0:
                    return text.strip()

        # Fallback: try to find readable text in plist
        if isinstance(plist, dict):
            for key, value in plist.items():
                if isinstance(value, str) and len(value) > 0 and not value.startswith('NS'):
                    return value

        return None

    except Exception as e:
        logger.debug(f"Failed to parse attributedBody: {e}")
        return None


def extract_text_from_blob(blob: bytes) -> Optional[str]:
    """
    Extract readable text from a binary blob (attributedBody format).

    macOS Messages uses a "streamtyped" format where:
    - Header: streamtyped + class hierarchy
    - After "NSString" marker: 5 control bytes + length byte + actual text
    - Text ends before control sequences (0x86, 0x84, etc.)

    Args:
        blob: Raw bytes from attributedBody column

    Returns:
        Extracted text or None
    """
    if not blob:
        return None

    # Method 1: Try parsing as bplist (NSKeyedArchiver format)
    result = parse_attributed_body(blob)
    if result:
        return result

    # Method 2: Parse streamtyped format (macOS Messages format)
    try:
        # Find the NSString marker followed by control bytes and +
        # Pattern: NSString + 5 bytes including \x01\x94\x84\x01+ + length_byte + text
        nsstring_idx = blob.find(b'NSString')
        if nsstring_idx != -1:
            # Look for the '+' marker which precedes the text
            plus_idx = blob.find(b'+', nsstring_idx)
            if plus_idx != -1 and plus_idx < nsstring_idx + 20:
                # Skip the '+' and the length byte
                text_start = plus_idx + 2

                # Find where the text ends (before control chars like \x86\x84)
                text_end = text_start
                while text_end < len(blob):
                    byte = blob[text_end]
                    # Stop at control sequences (0x86, 0x84 commonly end the text)
                    if byte in (0x86, 0x84, 0x00):
                        break
                    text_end += 1

                if text_end > text_start:
                    text_bytes = blob[text_start:text_end]
                    try:
                        text = text_bytes.decode('utf-8')
                        if text.strip():
                            return text.strip()
                    except UnicodeDecodeError:
                        # Try with error handling
                        text = text_bytes.decode('utf-8', errors='ignore')
                        if text.strip():
                            return text.strip()

        # Method 3: Try NSMutableString (for reactions/edits)
        nsmutstring_idx = blob.find(b'NSMutableString')
        if nsmutstring_idx == -1:
            nsmutstring_idx = blob.find(b'NSString')
        if nsmutstring_idx != -1:
            # Similar pattern for mutable strings
            plus_idx = blob.find(b'+', nsmutstring_idx)
            if plus_idx != -1:
                text_start = plus_idx + 2
                text_end = text_start
                while text_end < len(blob) and blob[text_end] not in (0x86, 0x84, 0x00, 0x69):
                    # 0x69 = 'i' which often marks end
                    if text_end + 1 < len(blob) and blob[text_end] == ord('i') and blob[text_end + 1] in (0x49, 0x4e):
                        break
                    text_end += 1

                if text_end > text_start:
                    text_bytes = blob[text_start:text_end]
                    text = text_bytes.decode('utf-8', errors='ignore')
                    if text.strip():
                        return text.strip()

        # Method 4: Fallback - find longest readable sequence
        text = blob.decode('utf-8', errors='ignore')
        # Find substantial printable runs that aren't class names
        printable_runs = re.findall(r'[^\x00-\x1f\x7f-\x9f]{3,}', text)
        for run in printable_runs:
            # Skip metadata strings
            skip_patterns = ['NSString', 'NSObject', 'NSMutable', 'NSDictionary',
                           'NSAttributed', 'streamtyped', '__kIM', 'NSNumber', 'NSValue']
            if not any(p in run for p in skip_patterns):
                # Clean up any remaining artifacts
                cleaned = run.strip('+').strip()
                if cleaned and len(cleaned) >= 2:
                    return cleaned

    except Exception as e:
        logger.debug(f"Error extracting text from blob: {e}")

    return None


class MessagesInterface:
    """Interface to macOS Messages app."""

    def __init__(self, messages_db_path: str = "~/Library/Messages/chat.db"):
        """
        Initialize Messages interface.

        Args:
            messages_db_path: Path to Messages database (default: standard location)
        """
        self.messages_db_path = Path(messages_db_path).expanduser()
        logger.info(f"Initialized MessagesInterface with DB: {self.messages_db_path}")

    def send_message(self, phone: str, message: str) -> dict:
        """
        Send an iMessage using AppleScript.

        Args:
            phone: Phone number or iMessage handle (email)
            message: Message text to send

        Returns:
            dict: {"success": bool, "error": Optional[str]}

        Example:
            result = interface.send_message("+14155551234", "Hello!")
        """
        logger.info(f"Sending message to {phone}")

        # Escape user data for safe AppleScript string interpolation
        # This prevents injection attacks where special characters in
        # contact names or messages could break out of the quoted context
        escaped_message = escape_applescript_string(message)
        escaped_phone = escape_applescript_string(phone)

        # AppleScript to send message
        # Uses Messages.app automation
        script = f'''
        tell application "Messages"
            set targetService to 1st account whose service type = iMessage
            set targetBuddy to participant "{escaped_phone}" of targetService
            send "{escaped_message}" to targetBuddy
        end tell
        '''

        try:
            # Execute AppleScript
            result = subprocess.run(
                ['osascript', '-e', script],
                capture_output=True,
                text=True,
                timeout=10
            )

            if result.returncode == 0:
                logger.info(f"Message sent successfully to {phone}")
                return {"success": True, "error": None}
            else:
                error_msg = result.stderr.strip()
                logger.error(f"Failed to send message: {error_msg}")
                return {"success": False, "error": error_msg}

        except subprocess.TimeoutExpired:
            logger.error("AppleScript timeout - Messages.app may not be running")
            return {
                "success": False,
                "error": "Timeout - ensure Messages.app is running"
            }
        except Exception as e:
            logger.error(f"Exception sending message: {e}")
            return {"success": False, "error": str(e)}

    def get_recent_messages(
        self,
        phone: str,
        limit: int = 20
    ) -> List[Dict]:
        """
        Retrieve recent messages with a contact from Messages database.

        Args:
            phone: Phone number or iMessage handle
            limit: Number of recent messages to retrieve

        Returns:
            List[Dict]: List of message dicts with keys:
                - text: Message content
                - date: Timestamp
                - is_from_me: Boolean (sent vs received)

        Note:
            Requires Full Disk Access permission for ~/Library/Messages/chat.db
            Includes attributedBody parsing for macOS Ventura+
        """
        logger.info(f"Retrieving recent messages for {phone}")

        if not self.messages_db_path.exists():
            logger.error(f"Messages database not found: {self.messages_db_path}")
            return []

        try:
            # Connect to Messages database (read-only)
            conn = sqlite3.connect(f"file:{self.messages_db_path}?mode=ro", uri=True)
            cursor = conn.cursor()

            # Query messages for this contact
            # Include attributedBody for macOS Ventura+ message parsing
            query = """
                SELECT
                    message.text,
                    message.attributedBody,
                    message.date,
                    message.is_from_me,
                    message.cache_roomnames
                FROM message
                JOIN handle ON message.handle_id = handle.ROWID
                WHERE handle.id LIKE ?
                ORDER BY message.date DESC
                LIMIT ?
            """

            # macOS Messages uses time since 2001-01-01 (Cocoa reference date)
            cursor.execute(query, (f"%{phone}%", limit))
            rows = cursor.fetchall()

            messages = []
            for row in rows:
                text, attributed_body, date_cocoa, is_from_me, cache_roomnames = row

                # Try to get text content:
                # 1. Use text column if available (older messages)
                # 2. Parse attributedBody for macOS Ventura+ messages
                message_text = text
                if not message_text and attributed_body:
                    message_text = extract_text_from_blob(attributed_body)

                # Convert Cocoa timestamp to Python datetime
                # Cocoa epoch: 2001-01-01 00:00:00 UTC
                if date_cocoa:
                    cocoa_epoch = datetime(2001, 1, 1)
                    date = cocoa_epoch + timedelta(seconds=date_cocoa / 1_000_000_000)
                else:
                    date = None

                # Check if this is a group chat
                is_group_chat = is_group_chat_identifier(cache_roomnames)

                messages.append({
                    "text": message_text or "[message content not available]",
                    "date": date.isoformat() if date else None,
                    "is_from_me": bool(is_from_me),
                    "is_group_chat": is_group_chat,
                    "group_id": cache_roomnames if is_group_chat else None
                })

            conn.close()
            logger.info(f"Retrieved {len(messages)} messages")
            return messages

        except sqlite3.Error as e:
            logger.error(f"Database error: {e}")
            return []
        except Exception as e:
            logger.error(f"Error retrieving messages: {e}")
            return []

    def check_permissions(self) -> dict:
        """
        Check if required permissions are granted.

        Returns:
            dict: {"messages_db_accessible": bool, "applescript_ready": bool}
        """
        permissions = {
            "messages_db_accessible": self.messages_db_path.exists(),
            "applescript_ready": True  # Will fail on first send if not granted
        }

        if not permissions["messages_db_accessible"]:
            logger.warning(
                "Messages database not accessible. "
                "Grant Full Disk Access: System Settings → Privacy & Security"
            )

        return permissions

    def get_all_recent_conversations(self, limit: int = 20) -> List[Dict]:
        """
        Get recent messages from ALL conversations (not filtered by contact).

        Sprint 2.5: Returns recent messages across all contacts, including
        unknown numbers and people not in your contacts.

        Args:
            limit: Number of recent messages to retrieve

        Returns:
            List[Dict]: List of message dicts with keys:
                - text: Message content
                - date: Timestamp
                - is_from_me: Boolean (sent vs received)
                - phone: Phone number or handle of sender/recipient
                - contact_name: Contact name if available, otherwise phone/handle

        Example:
            messages = interface.get_all_recent_conversations(limit=50)
        """
        logger.info(f"Retrieving {limit} most recent messages from all conversations")

        if not self.messages_db_path.exists():
            logger.error(f"Messages database not found: {self.messages_db_path}")
            return []

        try:
            conn = sqlite3.connect(f"file:{self.messages_db_path}?mode=ro", uri=True)
            cursor = conn.cursor()

            # Query recent messages across all conversations
            query = """
                SELECT
                    message.text,
                    message.attributedBody,
                    message.date,
                    message.is_from_me,
                    handle.id,
                    message.cache_roomnames
                FROM message
                LEFT JOIN handle ON message.handle_id = handle.ROWID
                ORDER BY message.date DESC
                LIMIT ?
            """

            cursor.execute(query, (limit,))
            rows = cursor.fetchall()

            messages = []
            for row in rows:
                text, attributed_body, date_cocoa, is_from_me, handle_id, cache_roomnames = row

                # Extract message text
                message_text = text
                if not message_text and attributed_body:
                    message_text = extract_text_from_blob(attributed_body)

                # Convert timestamp
                if date_cocoa:
                    cocoa_epoch = datetime(2001, 1, 1)
                    date = cocoa_epoch + timedelta(seconds=date_cocoa / 1_000_000_000)
                else:
                    date = None

                # Check if this is a group chat
                is_group_chat = is_group_chat_identifier(cache_roomnames)

                messages.append({
                    "text": message_text or "[message content not available]",
                    "date": date.isoformat() if date else None,
                    "is_from_me": bool(is_from_me),
                    "phone": handle_id or "unknown",
                    "contact_name": None,  # Will be populated by MCP tool if contact exists
                    "is_group_chat": is_group_chat,
                    "group_id": cache_roomnames if is_group_chat else None,
                    "sender_handle": handle_id  # For group chats, identifies who sent this message
                })

            conn.close()
            logger.info(f"Retrieved {len(messages)} messages from all conversations")
            return messages

        except sqlite3.Error as e:
            logger.error(f"Database error: {e}")
            return []
        except Exception as e:
            logger.error(f"Error retrieving messages: {e}")
            return []

    def search_messages(
        self,
        query: str,
        phone: Optional[str] = None,
        limit: int = 50
    ) -> List[Dict]:
        """
        Search messages by content/keyword.

        Sprint 2.5: Full-text search across all messages or filtered by contact.

        Args:
            query: Search query (keyword or phrase)
            phone: Optional phone number to filter by specific contact
            limit: Maximum number of results

        Returns:
            List[Dict]: List of matching message dicts with keys:
                - text: Message content
                - date: Timestamp
                - is_from_me: Boolean
                - phone: Phone number or handle
                - match_snippet: Text snippet showing the match

        Example:
            # Search all messages
            results = interface.search_messages("dinner plans")

            # Search messages with specific contact
            results = interface.search_messages("dinner", phone="+14155551234")
        """
        logger.info(f"Searching messages for query: '{query}'" +
                   (f" (contact: {phone})" if phone else " (all contacts)"))

        if not self.messages_db_path.exists():
            logger.error(f"Messages database not found: {self.messages_db_path}")
            return []

        try:
            conn = sqlite3.connect(f"file:{self.messages_db_path}?mode=ro", uri=True)
            cursor = conn.cursor()

            # Build query based on whether we're filtering by phone
            if phone:
                sql_query = """
                    SELECT
                        message.text,
                        message.attributedBody,
                        message.date,
                        message.is_from_me,
                        handle.id,
                        message.cache_roomnames
                    FROM message
                    JOIN handle ON message.handle_id = handle.ROWID
                    WHERE (message.text LIKE ? OR message.attributedBody IS NOT NULL)
                        AND handle.id LIKE ?
                    ORDER BY message.date DESC
                    LIMIT ?
                """
                cursor.execute(sql_query, (f"%{query}%", f"%{phone}%", limit))
            else:
                sql_query = """
                    SELECT
                        message.text,
                        message.attributedBody,
                        message.date,
                        message.is_from_me,
                        handle.id,
                        message.cache_roomnames
                    FROM message
                    LEFT JOIN handle ON message.handle_id = handle.ROWID
                    WHERE message.text LIKE ? OR message.attributedBody IS NOT NULL
                    ORDER BY message.date DESC
                    LIMIT ?
                """
                cursor.execute(sql_query, (f"%{query}%", limit))

            rows = cursor.fetchall()

            messages = []
            for row in rows:
                text, attributed_body, date_cocoa, is_from_me, handle_id, cache_roomnames = row

                # Extract message text
                message_text = text
                if not message_text and attributed_body:
                    message_text = extract_text_from_blob(attributed_body)

                # Skip if no text content (attachments only, etc.)
                if not message_text:
                    continue

                # Check if query matches (for attributedBody messages)
                if query.lower() not in message_text.lower():
                    continue

                # Convert timestamp
                if date_cocoa:
                    cocoa_epoch = datetime(2001, 1, 1)
                    date = cocoa_epoch + timedelta(seconds=date_cocoa / 1_000_000_000)
                else:
                    date = None

                # Create match snippet (show context around match)
                match_snippet = self._create_snippet(message_text, query)

                # Check if this is a group chat
                is_group_chat = is_group_chat_identifier(cache_roomnames)

                messages.append({
                    "text": message_text,
                    "date": date.isoformat() if date else None,
                    "is_from_me": bool(is_from_me),
                    "phone": handle_id or "unknown",
                    "match_snippet": match_snippet,
                    "is_group_chat": is_group_chat,
                    "group_id": cache_roomnames if is_group_chat else None
                })

            conn.close()
            logger.info(f"Found {len(messages)} messages matching '{query}'")
            return messages

        except sqlite3.Error as e:
            logger.error(f"Database error: {e}")
            return []
        except Exception as e:
            logger.error(f"Error searching messages: {e}")
            return []

    def list_group_chats(self, limit: int = 50) -> List[Dict]:
        """
        List all group chats with participant information.

        Sprint 3: Discovers group conversations from the Messages database
        by querying the chat table and joining with chat_handle_join for participants.

        Args:
            limit: Maximum number of group chats to return

        Returns:
            List[Dict]: List of group chat dicts with keys:
                - group_id: Unique identifier for the group (chat_identifier)
                - display_name: The group name if set
                - participants: List of participant handles
                - participant_count: Number of participants
                - last_message_date: Timestamp of most recent message
                - message_count: Approximate number of messages in group

        Example:
            groups = interface.list_group_chats()
        """
        logger.info(f"Listing group chats (limit: {limit})")

        if not self.messages_db_path.exists():
            logger.error(f"Messages database not found: {self.messages_db_path}")
            return []

        try:
            conn = sqlite3.connect(f"file:{self.messages_db_path}?mode=ro", uri=True)
            cursor = conn.cursor()

            # Query group chats from chat table
            # Group chats have chat_identifier starting with 'chat' followed by numbers
            # or have display_name set
            query = """
                SELECT
                    c.ROWID,
                    c.chat_identifier,
                    c.display_name,
                    (SELECT MAX(m.date) FROM message m
                     JOIN chat_message_join cmj ON m.ROWID = cmj.message_id
                     WHERE cmj.chat_id = c.ROWID) as last_date,
                    (SELECT COUNT(*) FROM chat_message_join cmj
                     WHERE cmj.chat_id = c.ROWID) as msg_count
                FROM chat c
                WHERE c.chat_identifier LIKE 'chat%'
                    OR c.display_name IS NOT NULL AND c.display_name != ''
                ORDER BY last_date DESC
                LIMIT ?
            """

            cursor.execute(query, (limit,))
            chat_rows = cursor.fetchall()

            groups = []
            for row in chat_rows:
                chat_rowid, chat_identifier, display_name, last_date_cocoa, msg_count = row

                # Get participants for this chat
                cursor.execute("""
                    SELECT h.id
                    FROM handle h
                    JOIN chat_handle_join chj ON h.ROWID = chj.handle_id
                    WHERE chj.chat_id = ?
                """, (chat_rowid,))
                participants = [p[0] for p in cursor.fetchall()]

                # Only include if it has multiple participants (group chat)
                if len(participants) < 2:
                    continue

                # Convert Cocoa timestamp
                if last_date_cocoa:
                    cocoa_epoch = datetime(2001, 1, 1)
                    last_date = cocoa_epoch + timedelta(seconds=last_date_cocoa / 1_000_000_000)
                else:
                    last_date = None

                groups.append({
                    "group_id": chat_identifier,
                    "display_name": display_name,
                    "participants": participants,
                    "participant_count": len(participants),
                    "last_message_date": last_date.isoformat() if last_date else None,
                    "message_count": msg_count or 0
                })

            conn.close()
            logger.info(f"Found {len(groups)} group chats")
            return groups

        except sqlite3.Error as e:
            logger.error(f"Database error: {e}")
            return []
        except Exception as e:
            logger.error(f"Error listing group chats: {e}")
            return []

    def get_group_messages(
        self,
        group_id: Optional[str] = None,
        participant_filter: Optional[str] = None,
        limit: int = 50
    ) -> List[Dict]:
        """
        Get messages from a specific group chat.

        Sprint 3: Retrieves messages from a group conversation, identified
        by group_id (chat_identifier) or by matching a participant.

        Args:
            group_id: The group identifier (chat_identifier value from list_group_chats)
            participant_filter: Optional phone/email to filter groups containing this participant
            limit: Maximum number of messages to return

        Returns:
            List[Dict]: List of message dicts with keys:
                - text: Message content
                - date: Timestamp
                - is_from_me: Boolean (sent vs received)
                - sender_handle: Phone/email of message sender
                - group_id: The group identifier
                - display_name: The group name if set
                - group_participants: List of all group participants

        Example:
            # Get messages by group ID
            messages = interface.get_group_messages(group_id="chat152668864985555509")

            # Get messages from any group containing this participant
            messages = interface.get_group_messages(participant_filter="+15551234567")
        """
        logger.info(f"Getting group messages (group_id: {group_id}, participant: {participant_filter})")

        if not group_id and not participant_filter:
            logger.error("Either group_id or participant_filter must be provided")
            return []

        if not self.messages_db_path.exists():
            logger.error(f"Messages database not found: {self.messages_db_path}")
            return []

        try:
            conn = sqlite3.connect(f"file:{self.messages_db_path}?mode=ro", uri=True)
            cursor = conn.cursor()

            # First, find the chat(s) that match
            if group_id:
                cursor.execute("""
                    SELECT c.ROWID, c.chat_identifier, c.display_name
                    FROM chat c
                    WHERE c.chat_identifier = ?
                """, (group_id,))
            else:
                # Find groups containing this participant
                cursor.execute("""
                    SELECT DISTINCT c.ROWID, c.chat_identifier, c.display_name
                    FROM chat c
                    JOIN chat_handle_join chj ON c.ROWID = chj.chat_id
                    JOIN handle h ON chj.handle_id = h.ROWID
                    WHERE h.id LIKE ?
                        AND (c.chat_identifier LIKE 'chat%' OR c.display_name IS NOT NULL)
                """, (f"%{participant_filter}%",))

            chats = cursor.fetchall()

            if not chats:
                conn.close()
                return []

            # Get messages from all matching chats
            messages = []
            for chat_rowid, chat_identifier, display_name in chats:
                # Get participants for this chat
                cursor.execute("""
                    SELECT h.id
                    FROM handle h
                    JOIN chat_handle_join chj ON h.ROWID = chj.handle_id
                    WHERE chj.chat_id = ?
                """, (chat_rowid,))
                participants = [p[0] for p in cursor.fetchall()]

                # Get messages
                cursor.execute("""
                    SELECT
                        m.text,
                        m.attributedBody,
                        m.date,
                        m.is_from_me,
                        h.id as sender_handle
                    FROM message m
                    JOIN chat_message_join cmj ON m.ROWID = cmj.message_id
                    LEFT JOIN handle h ON m.handle_id = h.ROWID
                    WHERE cmj.chat_id = ?
                    ORDER BY m.date DESC
                    LIMIT ?
                """, (chat_rowid, limit))

                for row in cursor.fetchall():
                    text, attributed_body, date_cocoa, is_from_me, sender_handle = row

                    # Extract message text
                    message_text = text
                    if not message_text and attributed_body:
                        message_text = extract_text_from_blob(attributed_body)

                    # Convert timestamp
                    if date_cocoa:
                        cocoa_epoch = datetime(2001, 1, 1)
                        date = cocoa_epoch + timedelta(seconds=date_cocoa / 1_000_000_000)
                    else:
                        date = None

                    messages.append({
                        "text": message_text or "[message content not available]",
                        "date": date.isoformat() if date else None,
                        "is_from_me": bool(is_from_me),
                        "sender_handle": sender_handle or "unknown",
                        "group_id": chat_identifier,
                        "display_name": display_name,
                        "group_participants": participants
                    })

            # Sort by date (newest first)
            messages.sort(key=lambda m: m["date"] or "", reverse=True)
            messages = messages[:limit]

            conn.close()
            logger.info(f"Retrieved {len(messages)} group messages")
            return messages

        except sqlite3.Error as e:
            logger.error(f"Database error: {e}")
            return []
        except Exception as e:
            logger.error(f"Error retrieving group messages: {e}")
            return []

    def _create_snippet(self, text: str, query: str, context_chars: int = 50) -> str:
        """
        Create a text snippet showing the search query in context.

        Args:
            text: Full message text
            query: Search query
            context_chars: Characters to show before/after match

        Returns:
            Snippet with query highlighted
        """
        try:
            # Find query in text (case-insensitive)
            text_lower = text.lower()
            query_lower = query.lower()
            match_pos = text_lower.find(query_lower)

            if match_pos == -1:
                # No match (shouldn't happen), return start of text
                return text[:100] + "..." if len(text) > 100 else text

            # Calculate snippet bounds
            start = max(0, match_pos - context_chars)
            end = min(len(text), match_pos + len(query) + context_chars)

            # Extract snippet
            snippet = text[start:end]

            # Add ellipsis if truncated
            if start > 0:
                snippet = "..." + snippet
            if end < len(text):
                snippet = snippet + "..."

            return snippet

        except Exception as e:
            logger.debug(f"Error creating snippet: {e}")
            return text[:100]

    # ===== T0 FEATURES =====

    # Reaction type mappings for iMessage tapbacks
    REACTION_TYPES = {
        2000: "love",      # ❤️
        2001: "like",      # 👍
        2002: "dislike",   # 👎
        2003: "laugh",     # 😂
        2004: "emphasis",  # ‼️
        2005: "question",  # ❓
        # 3000-3005 are removal of these reactions
        3000: "remove_love",
        3001: "remove_like",
        3002: "remove_dislike",
        3003: "remove_laugh",
        3004: "remove_emphasis",
        3005: "remove_question",
    }

    def get_attachments(
        self,
        phone: Optional[str] = None,
        mime_type_filter: Optional[str] = None,
        limit: int = 50
    ) -> List[Dict]:
        """
        Get attachments from messages, optionally filtered by contact or type.

        T0 Feature: Access photos, videos, files, and other attachments.

        Args:
            phone: Optional phone number to filter by contact
            mime_type_filter: Filter by MIME type (e.g., "image/", "video/", "application/pdf")
            limit: Maximum number of attachments to return

        Returns:
            List[Dict]: Attachment information including:
                - attachment_id: Unique ID
                - filename: Full path to the attachment file
                - mime_type: MIME type (e.g., "image/jpeg")
                - uti: Uniform Type Identifier
                - total_bytes: File size in bytes
                - is_outgoing: True if sent, False if received
                - transfer_name: Display filename
                - created_date: When attachment was created
                - message_date: When the message was sent
                - sender_handle: Who sent it
                - is_sticker: Whether this is a sticker

        Example:
            # Get all image attachments
            images = interface.get_attachments(mime_type_filter="image/")

            # Get attachments from specific contact
            files = interface.get_attachments(phone="+14155551234")
        """
        logger.info(f"Getting attachments (phone: {phone}, type: {mime_type_filter})")

        if not self.messages_db_path.exists():
            logger.error(f"Messages database not found: {self.messages_db_path}")
            return []

        try:
            conn = sqlite3.connect(f"file:{self.messages_db_path}?mode=ro", uri=True)
            cursor = conn.cursor()

            # Build query with optional filters
            query = """
                SELECT
                    a.ROWID as attachment_id,
                    a.filename,
                    a.mime_type,
                    a.uti,
                    a.total_bytes,
                    a.is_outgoing,
                    a.transfer_name,
                    a.created_date,
                    a.is_sticker,
                    m.date as message_date,
                    m.is_from_me,
                    h.id as sender_handle
                FROM attachment a
                JOIN message_attachment_join maj ON a.ROWID = maj.attachment_id
                JOIN message m ON maj.message_id = m.ROWID
                LEFT JOIN handle h ON m.handle_id = h.ROWID
                WHERE 1=1
            """
            params = []

            if phone:
                query += " AND h.id LIKE ?"
                params.append(f"%{phone}%")

            if mime_type_filter:
                query += " AND a.mime_type LIKE ?"
                params.append(f"{mime_type_filter}%")

            query += " ORDER BY m.date DESC LIMIT ?"
            params.append(limit)

            cursor.execute(query, params)
            rows = cursor.fetchall()

            attachments = []
            for row in rows:
                (attachment_id, filename, mime_type, uti, total_bytes, is_outgoing,
                 transfer_name, created_date_cocoa, is_sticker, message_date_cocoa,
                 is_from_me, sender_handle) = row

                # Convert Cocoa timestamps
                message_date = None
                if message_date_cocoa:
                    cocoa_epoch = datetime(2001, 1, 1)
                    message_date = cocoa_epoch + timedelta(seconds=message_date_cocoa / 1_000_000_000)

                created_date = None
                if created_date_cocoa:
                    cocoa_epoch = datetime(2001, 1, 1)
                    created_date = cocoa_epoch + timedelta(seconds=created_date_cocoa / 1_000_000_000)

                attachments.append({
                    "attachment_id": attachment_id,
                    "filename": filename,
                    "mime_type": mime_type,
                    "uti": uti,
                    "total_bytes": total_bytes,
                    "is_outgoing": bool(is_outgoing),
                    "transfer_name": transfer_name,
                    "created_date": created_date.isoformat() if created_date else None,
                    "message_date": message_date.isoformat() if message_date else None,
                    "sender_handle": sender_handle or "unknown",
                    "is_from_me": bool(is_from_me),
                    "is_sticker": bool(is_sticker)
                })

            conn.close()
            logger.info(f"Found {len(attachments)} attachments")
            return attachments

        except sqlite3.Error as e:
            logger.error(f"Database error: {e}")
            return []
        except Exception as e:
            logger.error(f"Error getting attachments: {e}")
            return []

    def get_unread_messages(self, limit: int = 50) -> List[Dict]:
        """
        Get unread messages that are awaiting response.

        T0 Feature: Surface messages that need attention.

        Args:
            limit: Maximum number of unread messages to return

        Returns:
            List[Dict]: List of unread message dicts with keys:
                - text: Message content
                - date: Timestamp
                - phone: Sender's phone/handle
                - is_group_chat: Whether from a group
                - group_id: Group identifier if applicable
                - days_old: How many days since the message

        Example:
            unread = interface.get_unread_messages()
            for msg in unread:
                print(f"From {msg['phone']}: {msg['text'][:50]}... ({msg['days_old']} days old)")
        """
        logger.info(f"Getting unread messages (limit: {limit})")

        if not self.messages_db_path.exists():
            logger.error(f"Messages database not found: {self.messages_db_path}")
            return []

        try:
            conn = sqlite3.connect(f"file:{self.messages_db_path}?mode=ro", uri=True)
            cursor = conn.cursor()

            # Query for unread incoming messages
            # is_read = 0, is_from_me = 0, is_finished = 1
            query = """
                SELECT
                    m.text,
                    m.attributedBody,
                    m.date,
                    h.id as sender_handle,
                    m.cache_roomnames,
                    c.display_name
                FROM message m
                LEFT JOIN handle h ON m.handle_id = h.ROWID
                LEFT JOIN chat_message_join cmj ON m.ROWID = cmj.message_id
                LEFT JOIN chat c ON cmj.chat_id = c.ROWID
                WHERE m.is_read = 0
                    AND m.is_from_me = 0
                    AND m.is_finished = 1
                    AND m.is_system_message = 0
                    AND m.item_type = 0
                ORDER BY m.date DESC
                LIMIT ?
            """

            cursor.execute(query, (limit,))
            rows = cursor.fetchall()

            now = datetime.now()
            messages = []
            for row in rows:
                text, attributed_body, date_cocoa, sender_handle, cache_roomnames, display_name = row

                # Extract message text
                message_text = text
                if not message_text and attributed_body:
                    message_text = extract_text_from_blob(attributed_body)

                # Convert timestamp
                if date_cocoa:
                    cocoa_epoch = datetime(2001, 1, 1)
                    date = cocoa_epoch + timedelta(seconds=date_cocoa / 1_000_000_000)
                    days_old = (now - date).days
                else:
                    date = None
                    days_old = 0

                # Check if group chat
                is_group_chat = is_group_chat_identifier(cache_roomnames)

                messages.append({
                    "text": message_text or "[message content not available]",
                    "date": date.isoformat() if date else None,
                    "phone": sender_handle or "unknown",
                    "is_group_chat": is_group_chat,
                    "group_id": cache_roomnames if is_group_chat else None,
                    "group_name": display_name if is_group_chat else None,
                    "days_old": days_old
                })

            conn.close()
            logger.info(f"Found {len(messages)} unread messages")
            return messages

        except sqlite3.Error as e:
            logger.error(f"Database error: {e}")
            return []
        except Exception as e:
            logger.error(f"Error getting unread messages: {e}")
            return []

    def get_reactions(
        self,
        phone: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict]:
        """
        Get reactions/tapbacks from messages.

        T0 Feature: See who reacted to what messages with which emoji.

        Args:
            phone: Optional filter by contact
            limit: Maximum number of reactions to return

        Returns:
            List[Dict]: Reaction information including:
                - reaction_type: Type of reaction (love, like, dislike, laugh, emphasis, question)
                - reaction_emoji: Associated emoji if custom
                - reactor_handle: Who added the reaction
                - original_message_guid: GUID of the message reacted to
                - original_message_preview: Preview of the original message
                - date: When the reaction was added
                - is_removal: Whether this removes a prior reaction

        Example:
            reactions = interface.get_reactions()
            for r in reactions:
                print(f"{r['reactor_handle']} {r['reaction_type']}d: {r['original_message_preview']}")
        """
        logger.info(f"Getting reactions (phone: {phone})")

        if not self.messages_db_path.exists():
            logger.error(f"Messages database not found: {self.messages_db_path}")
            return []

        try:
            conn = sqlite3.connect(f"file:{self.messages_db_path}?mode=ro", uri=True)
            cursor = conn.cursor()

            # Build query for reaction messages
            # Reactions have associated_message_type in 2000-2005 (add) or 3000-3005 (remove)
            query = """
                SELECT
                    r.associated_message_type,
                    r.associated_message_guid,
                    r.associated_message_emoji,
                    r.date,
                    r.is_from_me,
                    h.id as reactor_handle,
                    orig.text as original_text,
                    orig.attributedBody as original_body
                FROM message r
                LEFT JOIN handle h ON r.handle_id = h.ROWID
                LEFT JOIN message orig ON r.associated_message_guid = orig.guid
                WHERE r.associated_message_type BETWEEN 2000 AND 3005
            """
            params = []

            if phone:
                query += " AND h.id LIKE ?"
                params.append(f"%{phone}%")

            query += " ORDER BY r.date DESC LIMIT ?"
            params.append(limit)

            cursor.execute(query, params)
            rows = cursor.fetchall()

            reactions = []
            for row in rows:
                (reaction_code, orig_guid, custom_emoji, date_cocoa, is_from_me,
                 reactor_handle, orig_text, orig_body) = row

                # Get reaction type name
                reaction_type = self.REACTION_TYPES.get(reaction_code, f"unknown_{reaction_code}")
                is_removal = reaction_code >= 3000

                # Get original message preview
                orig_preview = orig_text
                if not orig_preview and orig_body:
                    orig_preview = extract_text_from_blob(orig_body)
                if orig_preview and len(orig_preview) > 100:
                    orig_preview = orig_preview[:100] + "..."

                # Convert timestamp
                if date_cocoa:
                    cocoa_epoch = datetime(2001, 1, 1)
                    date = cocoa_epoch + timedelta(seconds=date_cocoa / 1_000_000_000)
                else:
                    date = None

                reactions.append({
                    "reaction_type": reaction_type.replace("remove_", "") if is_removal else reaction_type,
                    "reaction_emoji": custom_emoji,
                    "reactor_handle": reactor_handle or ("me" if is_from_me else "unknown"),
                    "is_from_me": bool(is_from_me),
                    "original_message_guid": orig_guid,
                    "original_message_preview": orig_preview or "[message not found]",
                    "date": date.isoformat() if date else None,
                    "is_removal": is_removal
                })

            conn.close()
            logger.info(f"Found {len(reactions)} reactions")
            return reactions

        except sqlite3.Error as e:
            logger.error(f"Database error: {e}")
            return []
        except Exception as e:
            logger.error(f"Error getting reactions: {e}")
            return []

    def get_conversation_analytics(
        self,
        phone: Optional[str] = None,
        days: int = 30
    ) -> Dict:
        """
        Get analytics about message patterns and frequency.

        T0 Feature: Understand communication patterns.

        Args:
            phone: Optional filter by specific contact (None = all contacts)
            days: Number of days to analyze

        Returns:
            Dict: Analytics including:
                - total_messages: Total message count
                - sent_count: Messages you sent
                - received_count: Messages received
                - avg_daily_messages: Average messages per day
                - busiest_hour: Hour with most messages (0-23)
                - busiest_day: Day of week with most messages
                - top_contacts: Top 10 contacts by message volume
                - response_stats: Average response time stats
                - attachment_count: Number of attachments
                - reaction_count: Number of reactions sent/received

        Example:
            analytics = interface.get_conversation_analytics(days=30)
            print(f"You exchanged {analytics['total_messages']} messages in the last 30 days")
        """
        logger.info(f"Getting conversation analytics (phone: {phone}, days: {days})")

        if not self.messages_db_path.exists():
            logger.error(f"Messages database not found: {self.messages_db_path}")
            return {}

        try:
            conn = sqlite3.connect(f"file:{self.messages_db_path}?mode=ro", uri=True)
            cursor = conn.cursor()

            # Calculate date threshold
            cutoff_date = datetime.now() - timedelta(days=days)
            cocoa_epoch = datetime(2001, 1, 1)
            cutoff_cocoa = int((cutoff_date - cocoa_epoch).total_seconds() * 1_000_000_000)

            base_filter = "WHERE m.date >= ?"
            params = [cutoff_cocoa]

            if phone:
                base_filter += " AND h.id LIKE ?"
                params.append(f"%{phone}%")

            # Get total counts
            cursor.execute(f"""
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN m.is_from_me = 1 THEN 1 ELSE 0 END) as sent,
                    SUM(CASE WHEN m.is_from_me = 0 THEN 1 ELSE 0 END) as received
                FROM message m
                LEFT JOIN handle h ON m.handle_id = h.ROWID
                {base_filter}
                AND m.associated_message_type IS NULL OR m.associated_message_type = 0
            """, params)
            row = cursor.fetchone()
            total, sent, received = row if row else (0, 0, 0)

            # Get messages by hour (for busiest hour)
            cursor.execute(f"""
                SELECT
                    CAST((m.date / 1000000000 / 3600) % 24 AS INTEGER) as hour,
                    COUNT(*) as count
                FROM message m
                LEFT JOIN handle h ON m.handle_id = h.ROWID
                {base_filter}
                GROUP BY hour
                ORDER BY count DESC
                LIMIT 1
            """, params)
            hour_row = cursor.fetchone()
            busiest_hour = hour_row[0] if hour_row else None

            # Get messages by day of week
            cursor.execute(f"""
                SELECT
                    CAST((m.date / 1000000000 / 86400 + 1) % 7 AS INTEGER) as dow,
                    COUNT(*) as count
                FROM message m
                LEFT JOIN handle h ON m.handle_id = h.ROWID
                {base_filter}
                GROUP BY dow
                ORDER BY count DESC
                LIMIT 1
            """, params)
            dow_row = cursor.fetchone()
            days_of_week = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
            busiest_day = days_of_week[dow_row[0]] if dow_row and dow_row[0] is not None else None

            # Get top contacts (only if not filtering by phone)
            top_contacts = []
            if not phone:
                cursor.execute(f"""
                    SELECT
                        h.id,
                        COUNT(*) as msg_count
                    FROM message m
                    JOIN handle h ON m.handle_id = h.ROWID
                    WHERE m.date >= ?
                    AND (m.associated_message_type IS NULL OR m.associated_message_type = 0)
                    GROUP BY h.id
                    ORDER BY msg_count DESC
                    LIMIT 10
                """, [cutoff_cocoa])
                top_contacts = [{"phone": row[0], "message_count": row[1]} for row in cursor.fetchall()]

            # Get attachment count
            cursor.execute(f"""
                SELECT COUNT(DISTINCT a.ROWID)
                FROM attachment a
                JOIN message_attachment_join maj ON a.ROWID = maj.attachment_id
                JOIN message m ON maj.message_id = m.ROWID
                LEFT JOIN handle h ON m.handle_id = h.ROWID
                {base_filter}
            """, params)
            attachment_count = cursor.fetchone()[0] or 0

            # Get reaction count
            cursor.execute(f"""
                SELECT COUNT(*)
                FROM message m
                LEFT JOIN handle h ON m.handle_id = h.ROWID
                {base_filter}
                AND m.associated_message_type BETWEEN 2000 AND 3005
            """, params)
            reaction_count = cursor.fetchone()[0] or 0

            conn.close()

            analytics = {
                "total_messages": total or 0,
                "sent_count": sent or 0,
                "received_count": received or 0,
                "avg_daily_messages": round((total or 0) / max(days, 1), 1),
                "busiest_hour": busiest_hour,
                "busiest_day": busiest_day,
                "top_contacts": top_contacts,
                "attachment_count": attachment_count,
                "reaction_count": reaction_count,
                "analysis_period_days": days
            }

            logger.info(f"Generated analytics: {total} messages over {days} days")
            return analytics

        except sqlite3.Error as e:
            logger.error(f"Database error: {e}")
            return {}
        except Exception as e:
            logger.error(f"Error getting analytics: {e}")
            return {}

    # ===== T1 FEATURES =====

    def get_message_thread(
        self,
        message_guid: Optional[str] = None,
        thread_originator_guid: Optional[str] = None,
        limit: int = 50
    ) -> List[Dict]:
        """
        Get messages in a reply thread.

        T1 Feature: Follow reply chains and inline replies.

        Args:
            message_guid: GUID of any message in the thread
            thread_originator_guid: GUID of the thread starter (if known)
            limit: Maximum messages to return

        Returns:
            List[Dict]: Messages in the thread, chronologically ordered:
                - text: Message content
                - date: Timestamp
                - is_from_me: Boolean
                - sender_handle: Who sent it
                - is_thread_originator: Whether this started the thread
                - reply_to_guid: What message this replies to

        Example:
            thread = interface.get_message_thread(message_guid="...")
            for msg in thread:
                prefix = "📌 " if msg['is_thread_originator'] else "  └ "
                print(f"{prefix}{msg['sender_handle']}: {msg['text'][:50]}")
        """
        logger.info(f"Getting message thread (guid: {message_guid})")

        if not message_guid and not thread_originator_guid:
            logger.error("Either message_guid or thread_originator_guid required")
            return []

        if not self.messages_db_path.exists():
            logger.error(f"Messages database not found: {self.messages_db_path}")
            return []

        try:
            conn = sqlite3.connect(f"file:{self.messages_db_path}?mode=ro", uri=True)
            cursor = conn.cursor()

            # If we have message_guid but not thread_originator, find the originator
            if message_guid and not thread_originator_guid:
                cursor.execute("""
                    SELECT thread_originator_guid, guid
                    FROM message
                    WHERE guid = ?
                """, (message_guid,))
                row = cursor.fetchone()
                if row:
                    thread_originator_guid = row[0] or row[1]

            if not thread_originator_guid:
                conn.close()
                return []

            # Get all messages in this thread
            cursor.execute("""
                SELECT
                    m.guid,
                    m.text,
                    m.attributedBody,
                    m.date,
                    m.is_from_me,
                    h.id as sender_handle,
                    m.thread_originator_guid,
                    m.reply_to_guid
                FROM message m
                LEFT JOIN handle h ON m.handle_id = h.ROWID
                WHERE m.guid = ?
                   OR m.thread_originator_guid = ?
                ORDER BY m.date ASC
                LIMIT ?
            """, (thread_originator_guid, thread_originator_guid, limit))

            rows = cursor.fetchall()

            messages = []
            for row in rows:
                (guid, text, attributed_body, date_cocoa, is_from_me,
                 sender_handle, orig_guid, reply_guid) = row

                # Extract text
                message_text = text
                if not message_text and attributed_body:
                    message_text = extract_text_from_blob(attributed_body)

                # Convert timestamp
                if date_cocoa:
                    cocoa_epoch = datetime(2001, 1, 1)
                    date = cocoa_epoch + timedelta(seconds=date_cocoa / 1_000_000_000)
                else:
                    date = None

                messages.append({
                    "guid": guid,
                    "text": message_text or "[message content not available]",
                    "date": date.isoformat() if date else None,
                    "is_from_me": bool(is_from_me),
                    "sender_handle": sender_handle or ("me" if is_from_me else "unknown"),
                    "is_thread_originator": guid == thread_originator_guid,
                    "reply_to_guid": reply_guid
                })

            conn.close()
            logger.info(f"Found {len(messages)} messages in thread")
            return messages

        except sqlite3.Error as e:
            logger.error(f"Database error: {e}")
            return []
        except Exception as e:
            logger.error(f"Error getting thread: {e}")
            return []

    def extract_links(
        self,
        phone: Optional[str] = None,
        days: Optional[int] = None,
        limit: int = 100
    ) -> List[Dict]:
        """
        Extract URLs shared in conversations.

        T1 Feature: Find all links that have been shared.

        Args:
            phone: Optional filter by contact
            days: Optional filter by recency
            limit: Maximum links to return

        Returns:
            List[Dict]: Link information including:
                - url: The extracted URL
                - message_text: Context from the message
                - date: When shared
                - is_from_me: Whether you shared it
                - sender_handle: Who shared it

        Example:
            links = interface.extract_links(days=7)
            for link in links:
                print(f"{link['sender_handle']} shared: {link['url']}")
        """
        logger.info(f"Extracting links (phone: {phone}, days: {days})")

        if not self.messages_db_path.exists():
            logger.error(f"Messages database not found: {self.messages_db_path}")
            return []

        try:
            conn = sqlite3.connect(f"file:{self.messages_db_path}?mode=ro", uri=True)
            cursor = conn.cursor()

            # Build query
            query = """
                SELECT
                    m.text,
                    m.attributedBody,
                    m.date,
                    m.is_from_me,
                    h.id as sender_handle
                FROM message m
                LEFT JOIN handle h ON m.handle_id = h.ROWID
                WHERE (m.text LIKE '%http%' OR m.was_data_detected = 1)
            """
            params = []

            if phone:
                query += " AND h.id LIKE ?"
                params.append(f"%{phone}%")

            if days:
                cutoff_date = datetime.now() - timedelta(days=days)
                cocoa_epoch = datetime(2001, 1, 1)
                cutoff_cocoa = int((cutoff_date - cocoa_epoch).total_seconds() * 1_000_000_000)
                query += " AND m.date >= ?"
                params.append(cutoff_cocoa)

            query += " ORDER BY m.date DESC LIMIT ?"
            params.append(limit * 2)  # Fetch more since some may not have URLs

            cursor.execute(query, params)
            rows = cursor.fetchall()

            # URL regex pattern
            url_pattern = re.compile(
                r'https?://[^\s<>"{}|\\^`\[\]]+'
            )

            links = []
            for row in rows:
                text, attributed_body, date_cocoa, is_from_me, sender_handle = row

                # Extract text
                message_text = text
                if not message_text and attributed_body:
                    message_text = extract_text_from_blob(attributed_body)

                if not message_text:
                    continue

                # Find URLs in text
                urls = url_pattern.findall(message_text)
                if not urls:
                    continue

                # Convert timestamp
                if date_cocoa:
                    cocoa_epoch = datetime(2001, 1, 1)
                    date = cocoa_epoch + timedelta(seconds=date_cocoa / 1_000_000_000)
                else:
                    date = None

                for url in urls:
                    # Clean URL (remove trailing punctuation)
                    url = url.rstrip('.,;:!?)')

                    links.append({
                        "url": url,
                        "message_text": message_text[:200] + "..." if len(message_text) > 200 else message_text,
                        "date": date.isoformat() if date else None,
                        "is_from_me": bool(is_from_me),
                        "sender_handle": sender_handle or ("me" if is_from_me else "unknown")
                    })

                    if len(links) >= limit:
                        break

                if len(links) >= limit:
                    break

            conn.close()
            logger.info(f"Found {len(links)} links")
            return links

        except sqlite3.Error as e:
            logger.error(f"Database error: {e}")
            return []
        except Exception as e:
            logger.error(f"Error extracting links: {e}")
            return []

    def get_voice_messages(
        self,
        phone: Optional[str] = None,
        limit: int = 50
    ) -> List[Dict]:
        """
        Get voice/audio messages with file paths for transcription.

        T1 Feature: Access voice messages for SuperWhisper transcription.

        Args:
            phone: Optional filter by contact
            limit: Maximum messages to return

        Returns:
            List[Dict]: Voice message information including:
                - attachment_path: Path to the audio file
                - mime_type: Audio format
                - duration_seconds: Length if available
                - date: When sent
                - is_from_me: Whether you sent it
                - sender_handle: Who sent it
                - is_played: Whether it's been played

        Example:
            voice_msgs = interface.get_voice_messages()
            for msg in voice_msgs:
                # Could pass msg['attachment_path'] to SuperWhisper
                print(f"Voice from {msg['sender_handle']}: {msg['attachment_path']}")
        """
        logger.info(f"Getting voice messages (phone: {phone})")

        if not self.messages_db_path.exists():
            logger.error(f"Messages database not found: {self.messages_db_path}")
            return []

        try:
            conn = sqlite3.connect(f"file:{self.messages_db_path}?mode=ro", uri=True)
            cursor = conn.cursor()

            # Query for audio messages
            query = """
                SELECT
                    a.filename,
                    a.mime_type,
                    a.total_bytes,
                    m.date,
                    m.is_from_me,
                    m.is_played,
                    h.id as sender_handle
                FROM message m
                JOIN message_attachment_join maj ON m.ROWID = maj.message_id
                JOIN attachment a ON maj.attachment_id = a.ROWID
                LEFT JOIN handle h ON m.handle_id = h.ROWID
                WHERE (m.is_audio_message = 1
                    OR a.mime_type LIKE 'audio/%'
                    OR a.uti LIKE '%audio%')
            """
            params = []

            if phone:
                query += " AND h.id LIKE ?"
                params.append(f"%{phone}%")

            query += " ORDER BY m.date DESC LIMIT ?"
            params.append(limit)

            cursor.execute(query, params)
            rows = cursor.fetchall()

            voice_messages = []
            for row in rows:
                (filename, mime_type, total_bytes, date_cocoa,
                 is_from_me, is_played, sender_handle) = row

                # Convert timestamp
                if date_cocoa:
                    cocoa_epoch = datetime(2001, 1, 1)
                    date = cocoa_epoch + timedelta(seconds=date_cocoa / 1_000_000_000)
                else:
                    date = None

                voice_messages.append({
                    "attachment_path": filename,
                    "mime_type": mime_type,
                    "size_bytes": total_bytes,
                    "date": date.isoformat() if date else None,
                    "is_from_me": bool(is_from_me),
                    "is_played": bool(is_played),
                    "sender_handle": sender_handle or ("me" if is_from_me else "unknown")
                })

            conn.close()
            logger.info(f"Found {len(voice_messages)} voice messages")
            return voice_messages

        except sqlite3.Error as e:
            logger.error(f"Database error: {e}")
            return []
        except Exception as e:
            logger.error(f"Error getting voice messages: {e}")
            return []

    def get_scheduled_messages(self) -> List[Dict]:
        """
        Get scheduled messages that are pending send.

        T1 Feature: View queued/scheduled messages (read-only).

        Note: This is read-only - scheduled messages are created through
        the Messages app UI, not programmatically.

        Returns:
            List[Dict]: Scheduled message information including:
                - text: Message content
                - scheduled_date: When it will be sent
                - recipient_handle: Who it's being sent to
                - schedule_state: Current state (pending, etc.)

        Example:
            scheduled = interface.get_scheduled_messages()
            for msg in scheduled:
                print(f"Scheduled for {msg['scheduled_date']}: {msg['text'][:50]}")
        """
        logger.info("Getting scheduled messages")

        if not self.messages_db_path.exists():
            logger.error(f"Messages database not found: {self.messages_db_path}")
            return []

        try:
            conn = sqlite3.connect(f"file:{self.messages_db_path}?mode=ro", uri=True)
            cursor = conn.cursor()

            # Query for scheduled messages (schedule_type = 2)
            cursor.execute("""
                SELECT
                    m.text,
                    m.attributedBody,
                    m.date,
                    m.schedule_state,
                    h.id as recipient_handle
                FROM message m
                LEFT JOIN handle h ON m.handle_id = h.ROWID
                WHERE m.schedule_type = 2
                ORDER BY m.date ASC
            """)

            rows = cursor.fetchall()

            scheduled = []
            for row in rows:
                text, attributed_body, date_cocoa, schedule_state, recipient = row

                # Extract text
                message_text = text
                if not message_text and attributed_body:
                    message_text = extract_text_from_blob(attributed_body)

                # Convert timestamp
                if date_cocoa:
                    cocoa_epoch = datetime(2001, 1, 1)
                    date = cocoa_epoch + timedelta(seconds=date_cocoa / 1_000_000_000)
                else:
                    date = None

                scheduled.append({
                    "text": message_text or "[message content not available]",
                    "scheduled_date": date.isoformat() if date else None,
                    "recipient_handle": recipient or "unknown",
                    "schedule_state": schedule_state
                })

            conn.close()
            logger.info(f"Found {len(scheduled)} scheduled messages")
            return scheduled

        except sqlite3.Error as e:
            logger.error(f"Database error: {e}")
            return []
        except Exception as e:
            logger.error(f"Error getting scheduled messages: {e}")
            return []

    def get_messages_by_phone(self, phone: str, limit: int = 20) -> List[Dict]:
        """
        Get messages by phone number (without needing contact to be configured).

        Sprint 2.5: Enhanced access for unknown numbers.

        Args:
            phone: Phone number or iMessage handle
            limit: Number of recent messages to retrieve

        Returns:
            List[Dict]: Messages with that phone number
        """
        # This is essentially the same as get_recent_messages but with
        # a clearer interface for the MCP tool
        return self.get_recent_messages(phone=phone, limit=limit)

    # ===== T2 FEATURES =====

    def get_conversation_for_summary(
        self,
        phone: str,
        days: Optional[int] = None,
        limit: int = 200
    ) -> Dict:
        """
        Get conversation data formatted for AI summarization.

        T2 Feature: Prepares conversation history in a structured format
        that Claude can easily summarize.

        Args:
            phone: Contact phone number or handle
            days: Optional limit to last N days
            limit: Maximum messages to include

        Returns:
            Dict: Formatted conversation data including:
                - phone: The contact identifier
                - message_count: Total messages retrieved
                - date_range: {start, end} dates of conversation
                - conversation_text: Formatted dialogue for summarization
                - key_stats: {sent, received, avg_length, topics_mentioned}
                - recent_topics: Detected topics/keywords
                - last_interaction: When the last message was

        Example:
            data = interface.get_conversation_for_summary(phone="+14155551234", days=7)
            # Pass data['conversation_text'] to Claude for summarization
        """
        logger.info(f"Getting conversation for summary (phone: {phone}, days: {days})")

        if not self.messages_db_path.exists():
            logger.error(f"Messages database not found: {self.messages_db_path}")
            return {}

        try:
            conn = sqlite3.connect(f"file:{self.messages_db_path}?mode=ro", uri=True)
            cursor = conn.cursor()

            # Build query
            query = """
                SELECT
                    m.text,
                    m.attributedBody,
                    m.date,
                    m.is_from_me
                FROM message m
                JOIN handle h ON m.handle_id = h.ROWID
                WHERE h.id LIKE ?
                    AND (m.associated_message_type IS NULL OR m.associated_message_type = 0)
                    AND m.item_type = 0
            """
            params = [f"%{phone}%"]

            if days:
                cutoff_date = datetime.now() - timedelta(days=days)
                cocoa_epoch = datetime(2001, 1, 1)
                cutoff_cocoa = int((cutoff_date - cocoa_epoch).total_seconds() * 1_000_000_000)
                query += " AND m.date >= ?"
                params.append(cutoff_cocoa)

            query += " ORDER BY m.date ASC LIMIT ?"
            params.append(limit)

            cursor.execute(query, params)
            rows = cursor.fetchall()

            if not rows:
                conn.close()
                return {
                    "phone": phone,
                    "message_count": 0,
                    "conversation_text": "",
                    "error": "No messages found"
                }

            # Process messages
            messages = []
            sent_count = 0
            received_count = 0
            total_length = 0
            word_freq = {}

            for row in rows:
                text, attributed_body, date_cocoa, is_from_me = row

                # Extract text
                message_text = text
                if not message_text and attributed_body:
                    message_text = extract_text_from_blob(attributed_body)

                if not message_text:
                    continue

                # Convert timestamp
                if date_cocoa:
                    cocoa_epoch = datetime(2001, 1, 1)
                    date = cocoa_epoch + timedelta(seconds=date_cocoa / 1_000_000_000)
                else:
                    date = datetime.now()

                # Track stats
                if is_from_me:
                    sent_count += 1
                    sender = "You"
                else:
                    received_count += 1
                    sender = "Them"

                total_length += len(message_text)

                # Simple word frequency for topic detection
                words = re.findall(r'\b\w{4,}\b', message_text.lower())
                for word in words:
                    if word not in {'that', 'this', 'with', 'from', 'have', 'just', 'what', 'when', 'where', 'would', 'could', 'should', 'about', 'their', 'there', 'these', 'those', 'been', 'were', 'will', 'your', 'some', 'them'}:
                        word_freq[word] = word_freq.get(word, 0) + 1

                messages.append({
                    "date": date,
                    "sender": sender,
                    "text": message_text
                })

            conn.close()

            if not messages:
                return {
                    "phone": phone,
                    "message_count": 0,
                    "conversation_text": "",
                    "error": "No text messages found"
                }

            # Build formatted conversation text
            conversation_lines = []
            current_date = None

            for msg in messages:
                msg_date = msg["date"].strftime("%Y-%m-%d")
                if msg_date != current_date:
                    conversation_lines.append(f"\n=== {msg_date} ===\n")
                    current_date = msg_date

                time_str = msg["date"].strftime("%H:%M")
                conversation_lines.append(f"[{time_str}] {msg['sender']}: {msg['text']}")

            # Get top topics
            top_topics = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)[:10]

            result = {
                "phone": phone,
                "message_count": len(messages),
                "date_range": {
                    "start": messages[0]["date"].isoformat(),
                    "end": messages[-1]["date"].isoformat()
                },
                "conversation_text": "\n".join(conversation_lines),
                "key_stats": {
                    "sent": sent_count,
                    "received": received_count,
                    "avg_message_length": round(total_length / len(messages)) if messages else 0,
                },
                "recent_topics": [word for word, count in top_topics if count >= 2],
                "last_interaction": messages[-1]["date"].isoformat()
            }

            logger.info(f"Prepared summary data: {len(messages)} messages")
            return result

        except sqlite3.Error as e:
            logger.error(f"Database error: {e}")
            return {"error": str(e)}
        except Exception as e:
            logger.error(f"Error getting conversation for summary: {e}")
            return {"error": str(e)}

    # Follow-up detection patterns
    FOLLOW_UP_PATTERNS = {
        "question": [
            r'\?$',  # Ends with question mark
            r'\bwhat\b.*\?',
            r'\bhow\b.*\?',
            r'\bwhen\b.*\?',
            r'\bwhere\b.*\?',
            r'\bwhy\b.*\?',
            r'\bcan you\b',
            r'\bcould you\b',
            r'\bwould you\b',
        ],
        "promise": [
            r'\bi\'ll\b',
            r'\bi will\b',
            r'\blet me\b',
            r'\bgonna\b',
            r'\bgoing to\b',
            r'\bwill do\b',
            r'\bwill get\b',
            r'\bwill send\b',
            r'\bwill check\b',
        ],
        "waiting": [
            r'\bwaiting for\b',
            r'\blet me know\b',
            r'\bget back to\b',
            r'\bhear from\b',
            r'\bkeep me posted\b',
            r'\bkeep me updated\b',
            r'\blmk\b',
        ],
        "time_reference": [
            r'\btomorrow\b',
            r'\bnext week\b',
            r'\bmonday\b',
            r'\btuesday\b',
            r'\bwednesday\b',
            r'\bthursday\b',
            r'\bfriday\b',
            r'\bsaturday\b',
            r'\bsunday\b',
            r'\bthis week\b',
            r'\bend of day\b',
            r'\beod\b',
            r'\basap\b',
            r'\bsoon\b',
        ],
    }

    def detect_follow_up_needed(
        self,
        days: int = 7,
        min_stale_days: int = 3,
        limit: int = 50
    ) -> Dict:
        """
        Detect conversations that may need follow-up.

        T2 Feature: Smart reminders - finds messages suggesting action needed.

        Args:
            days: Look back this many days for patterns
            min_stale_days: Flag conversations with no reply after this many days
            limit: Maximum items per category

        Returns:
            Dict: Follow-up needs organized by category:
                - unanswered_questions: Questions they asked that you didn't answer
                - pending_promises: Things you said you'd do
                - waiting_on_them: Things you're waiting on from them
                - stale_conversations: Important conversations gone quiet
                - time_sensitive: Messages with time references

        Example:
            follow_ups = interface.detect_follow_up_needed()
            for q in follow_ups['unanswered_questions']:
                print(f"Unanswered from {q['phone']}: {q['text'][:50]}")
        """
        logger.info(f"Detecting follow-up needs (days: {days})")

        if not self.messages_db_path.exists():
            logger.error(f"Messages database not found: {self.messages_db_path}")
            return {}

        try:
            conn = sqlite3.connect(f"file:{self.messages_db_path}?mode=ro", uri=True)
            cursor = conn.cursor()

            # Calculate date thresholds
            cutoff_date = datetime.now() - timedelta(days=days)
            stale_date = datetime.now() - timedelta(days=min_stale_days)
            cocoa_epoch = datetime(2001, 1, 1)
            cutoff_cocoa = int((cutoff_date - cocoa_epoch).total_seconds() * 1_000_000_000)
            stale_cocoa = int((stale_date - cocoa_epoch).total_seconds() * 1_000_000_000)

            results = {
                "unanswered_questions": [],
                "pending_promises": [],
                "waiting_on_them": [],
                "stale_conversations": [],
                "time_sensitive": [],
                "analysis_period_days": days
            }

            # Get recent messages with context
            cursor.execute("""
                SELECT
                    m.text,
                    m.attributedBody,
                    m.date,
                    m.is_from_me,
                    h.id as phone,
                    m.ROWID
                FROM message m
                JOIN handle h ON m.handle_id = h.ROWID
                WHERE m.date >= ?
                    AND (m.associated_message_type IS NULL OR m.associated_message_type = 0)
                    AND m.item_type = 0
                ORDER BY h.id, m.date DESC
            """, (cutoff_cocoa,))

            rows = cursor.fetchall()

            # Group messages by phone
            conversations = {}
            for row in rows:
                text, attributed_body, date_cocoa, is_from_me, phone, rowid = row

                message_text = text
                if not message_text and attributed_body:
                    message_text = extract_text_from_blob(attributed_body)

                if not message_text:
                    continue

                if date_cocoa:
                    date = cocoa_epoch + timedelta(seconds=date_cocoa / 1_000_000_000)
                else:
                    date = datetime.now()

                if phone not in conversations:
                    conversations[phone] = []

                conversations[phone].append({
                    "text": message_text,
                    "date": date,
                    "is_from_me": bool(is_from_me),
                    "rowid": rowid
                })

            # Analyze each conversation
            for phone, messages in conversations.items():
                if not messages:
                    continue

                # Messages are ordered DESC, so [0] is most recent
                last_msg = messages[0]
                last_from_me = last_msg["is_from_me"]
                last_date = last_msg["date"]

                # Check for stale conversations (they messaged last, we haven't replied)
                if not last_from_me and last_date < stale_date:
                    days_ago = (datetime.now() - last_date).days
                    results["stale_conversations"].append({
                        "phone": phone,
                        "last_message": last_msg["text"][:100],
                        "days_since_reply": days_ago,
                        "date": last_date.isoformat()
                    })

                # Analyze individual messages
                for msg in messages[:20]:  # Check last 20 messages per contact
                    text_lower = msg["text"].lower()

                    # Unanswered questions (from them, not replied)
                    if not msg["is_from_me"]:
                        for pattern in self.FOLLOW_UP_PATTERNS["question"]:
                            if re.search(pattern, text_lower):
                                # Check if we replied after this
                                has_reply = any(
                                    m["is_from_me"] and m["date"] > msg["date"]
                                    for m in messages
                                )
                                if not has_reply:
                                    if len(results["unanswered_questions"]) < limit:
                                        results["unanswered_questions"].append({
                                            "phone": phone,
                                            "text": msg["text"][:200],
                                            "date": msg["date"].isoformat(),
                                            "days_ago": (datetime.now() - msg["date"]).days
                                        })
                                break

                    # Promises we made
                    if msg["is_from_me"]:
                        for pattern in self.FOLLOW_UP_PATTERNS["promise"]:
                            if re.search(pattern, text_lower):
                                if len(results["pending_promises"]) < limit:
                                    results["pending_promises"].append({
                                        "phone": phone,
                                        "text": msg["text"][:200],
                                        "date": msg["date"].isoformat(),
                                        "days_ago": (datetime.now() - msg["date"]).days
                                    })
                                break

                    # Things we're waiting on
                    if msg["is_from_me"]:
                        for pattern in self.FOLLOW_UP_PATTERNS["waiting"]:
                            if re.search(pattern, text_lower):
                                # Check if they replied
                                has_reply = any(
                                    not m["is_from_me"] and m["date"] > msg["date"]
                                    for m in messages
                                )
                                if not has_reply:
                                    if len(results["waiting_on_them"]) < limit:
                                        results["waiting_on_them"].append({
                                            "phone": phone,
                                            "text": msg["text"][:200],
                                            "date": msg["date"].isoformat(),
                                            "days_waiting": (datetime.now() - msg["date"]).days
                                        })
                                break

                    # Time-sensitive messages
                    for pattern in self.FOLLOW_UP_PATTERNS["time_reference"]:
                        if re.search(pattern, text_lower):
                            if len(results["time_sensitive"]) < limit:
                                results["time_sensitive"].append({
                                    "phone": phone,
                                    "text": msg["text"][:200],
                                    "date": msg["date"].isoformat(),
                                    "is_from_me": msg["is_from_me"],
                                    "days_ago": (datetime.now() - msg["date"]).days
                                })
                            break

            conn.close()

            # Add summary counts
            results["summary"] = {
                "unanswered_questions": len(results["unanswered_questions"]),
                "pending_promises": len(results["pending_promises"]),
                "waiting_on_them": len(results["waiting_on_them"]),
                "stale_conversations": len(results["stale_conversations"]),
                "time_sensitive": len(results["time_sensitive"]),
                "total_action_items": sum([
                    len(results["unanswered_questions"]),
                    len(results["pending_promises"]),
                    len(results["waiting_on_them"]),
                    len(results["stale_conversations"]),
                ])
            }

            logger.info(f"Found {results['summary']['total_action_items']} follow-up items")
            return results

        except sqlite3.Error as e:
            logger.error(f"Database error: {e}")
            return {"error": str(e)}
        except Exception as e:
            logger.error(f"Error detecting follow-ups: {e}")
            return {"error": str(e)}

"""
Gmail email indexer.

Indexes emails using the Gmail MCP tools. Each email becomes one chunk
with subject, body, sender, recipients, and labels as metadata.

Note: This indexer is designed to be called from the MCP server context
where Gmail tools are available. For standalone use, you'll need to
provide email data directly.
"""

import hashlib
import logging
import re
from datetime import datetime
from typing import List, Dict, Any, Optional, Callable

from .base_indexer import BaseSourceIndexer
from .chunk import UnifiedChunk

logger = logging.getLogger(__name__)


class GmailIndexer(BaseSourceIndexer):
    """
    Indexes Gmail emails.

    This indexer can work in two modes:
    1. MCP mode: Uses gmail_fetch function to get emails
    2. Direct mode: Accepts pre-fetched email data

    Args:
        gmail_fetcher: Async function to fetch emails (for MCP mode)
        store: Optional UnifiedVectorStore to use
        use_local_embeddings: Use local embeddings instead of OpenAI

    Example (MCP mode):
        async def fetch_gmail(max_results, after_date):
            return await mcp_gmail_list_emails(max_results=max_results, after_date=after_date)

        indexer = GmailIndexer(gmail_fetcher=fetch_gmail)
        result = await indexer.index_async(days=30)

    Example (Direct mode):
        indexer = GmailIndexer()
        emails = [...]  # Pre-fetched emails
        chunks = indexer.chunk_data(emails)
        indexer.store.add_chunks(chunks)
    """

    source_name = "gmail"

    def __init__(
        self,
        gmail_fetcher: Optional[Callable] = None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.gmail_fetcher = gmail_fetcher

    def fetch_data(
        self,
        days: Optional[int] = None,
        limit: Optional[int] = None,
        **kwargs,
    ) -> List[Dict[str, Any]]:
        """
        Fetch emails - requires gmail_fetcher to be set.

        For async fetching, use index_with_data() instead.
        """
        logger.warning(
            "GmailIndexer.fetch_data() is a stub. "
            "Use index_with_data() with pre-fetched emails or "
            "provide a gmail_fetcher in async context."
        )
        return []

    def index_with_data(
        self,
        emails: List[Dict[str, Any]],
        batch_size: int = 100,
    ) -> Dict[str, Any]:
        """
        Index pre-fetched email data.

        This is the recommended method when emails are already fetched
        via MCP tools.

        Args:
            emails: List of email dicts from Gmail API/MCP
            batch_size: Batch size for embeddings

        Returns:
            Dict with indexing stats
        """
        start_time = datetime.now()

        if not emails:
            return {
                "success": True,
                "source": self.source_name,
                "chunks_found": 0,
                "chunks_indexed": 0,
                "duration_seconds": 0,
            }

        # Convert to chunks
        chunks = self.chunk_data(emails)

        if not chunks:
            return {
                "success": True,
                "source": self.source_name,
                "chunks_found": 0,
                "chunks_indexed": 0,
                "duration_seconds": 0,
            }

        # Index chunks
        result = self.store.add_chunks(chunks, batch_size=batch_size)
        indexed_count = result.get(self.source_name, 0)

        duration = (datetime.now() - start_time).total_seconds()

        return {
            "success": True,
            "source": self.source_name,
            "chunks_found": len(chunks),
            "chunks_indexed": indexed_count,
            "duration_seconds": duration,
        }

    def chunk_data(self, emails: List[Dict[str, Any]]) -> List[UnifiedChunk]:
        """
        Convert emails to UnifiedChunks.

        Each email becomes one chunk (emails are typically self-contained).
        """
        chunks = []

        for email in emails:
            chunk = self._email_to_chunk(email)
            if chunk:
                chunks.append(chunk)

        logger.info(f"Created {len(chunks)} chunks from {len(emails)} emails")
        return chunks

    def _email_to_chunk(self, email: Dict[str, Any]) -> Optional[UnifiedChunk]:
        """Convert a single email to a UnifiedChunk."""
        # Extract required fields
        subject = email.get("subject", "")
        body = email.get("body", "") or email.get("snippet", "")
        sender = email.get("from", "") or email.get("sender", "")

        # Skip emails without meaningful content
        if not body or len(body.strip()) < 20:
            return None

        # Parse date
        date_str = email.get("date", "")
        email_date = self._parse_email_date(date_str)

        # Get recipients
        to_list = email.get("to", [])
        if isinstance(to_list, str):
            to_list = [to_list]

        cc_list = email.get("cc", [])
        if isinstance(cc_list, str):
            cc_list = [cc_list]

        participants = [sender] + to_list + cc_list
        participants = [p for p in participants if p]  # Remove empty

        # Get labels/tags
        labels = email.get("labels", []) or email.get("labelIds", [])
        if isinstance(labels, str):
            labels = [labels]

        # Build full text
        full_text = f"Subject: {subject}\n\n{body}"

        # Get message ID (unique per email) and thread ID
        message_id = email.get("id") or email.get("message_id") or email.get("messageId", "")
        thread_id = email.get("thread_id") or email.get("threadId", "")
        context_id = thread_id or message_id

        # Generate unique chunk_id using message_id (guaranteed unique per email)
        # This prevents collisions when emails have similar content
        chunk_id = hashlib.sha256(f"gmail|{message_id}".encode()).hexdigest()[:12]

        return UnifiedChunk(
            chunk_id=chunk_id,
            source="gmail",
            text=full_text,
            title=subject,
            context_id=str(context_id),
            context_type="thread",
            timestamp=email_date or datetime.now(),
            participants=participants,
            tags=labels,
            metadata={
                "message_id": message_id,
                "thread_id": thread_id,
                "has_attachments": bool(email.get("attachments") or email.get("has_attachments")),
                "is_unread": email.get("is_unread", False),
                "snippet": email.get("snippet", "")[:200] if email.get("snippet") else "",
            },
        )

    def _parse_email_date(self, date_str: str) -> Optional[datetime]:
        """
        Parse email date string to datetime.

        Handles various email date formats:
        - RFC 2822: "Mon, 30 Dec 2024 13:45:00 -0800"
        - ISO 8601: "2024-12-30T13:45:00Z"
        - Simple: "2024-12-30"
        """
        if not date_str:
            return None

        # Try ISO format first
        try:
            return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        except ValueError:
            pass

        # Try parsing common email date formats
        formats = [
            "%a, %d %b %Y %H:%M:%S %z",  # RFC 2822
            "%d %b %Y %H:%M:%S %z",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d",
        ]

        for fmt in formats:
            try:
                return datetime.strptime(date_str[:30], fmt)
            except ValueError:
                continue

        logger.debug(f"Could not parse email date: {date_str}")
        return None

    @staticmethod
    def extract_email_address(full_address: str) -> str:
        """
        Extract email address from full address string.

        "John Doe <john@example.com>" -> "john@example.com"
        """
        match = re.search(r'<([^>]+)>', full_address)
        if match:
            return match.group(1)
        return full_address.strip()

    @staticmethod
    def extract_sender_name(full_address: str) -> str:
        """
        Extract sender name from full address string.

        "John Doe <john@example.com>" -> "John Doe"
        """
        match = re.match(r'^([^<]+)\s*<', full_address)
        if match:
            return match.group(1).strip()
        return full_address.strip()

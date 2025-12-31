"""
Conversation chunker for iMessage RAG.

Groups individual messages into embeddable conversation windows.
Individual messages are typically too short for effective embeddings
(5-20 words). This module creates coherent conversation chunks
(200-500 words) that capture context and meaning.

Chunking Strategy:
    1. Group by contact (each conversation is separate)
    2. Create time-based windows (messages within N hours)
    3. Merge short adjacent chunks
    4. Split overly long chunks at natural boundaries

CS Concept: This is a form of "semantic chunking" - we're not just
splitting by character count, but by meaning boundaries (conversation
turns, time gaps, topic shifts).
"""

import hashlib
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Iterator
from collections import defaultdict

logger = logging.getLogger(__name__)


@dataclass
class ConversationChunk:
    """
    A chunk of conversation suitable for embedding.

    Represents a coherent unit of conversation with enough context
    for semantic search to work effectively.

    Attributes:
        chunk_id: Unique identifier (hash of content + metadata)
        contact: Contact name or phone number
        text: Combined message text for embedding
        start_time: First message timestamp
        end_time: Last message timestamp
        message_count: Number of messages in this chunk
        is_group: Whether this is from a group chat
        group_name: Group chat name if applicable
        metadata: Additional context for retrieval
    """
    chunk_id: str
    contact: str
    text: str
    start_time: datetime
    end_time: datetime
    message_count: int
    is_group: bool = False
    group_name: Optional[str] = None
    metadata: Dict = field(default_factory=dict)

    @property
    def duration_minutes(self) -> int:
        """Duration of conversation in minutes."""
        delta = self.end_time - self.start_time
        return int(delta.total_seconds() / 60)

    @property
    def word_count(self) -> int:
        """Approximate word count."""
        return len(self.text.split())

    def to_embedding_text(self) -> str:
        """
        Format chunk for embedding with context prefix.

        Includes metadata that helps with retrieval:
        - Who you're talking to
        - When the conversation happened
        - Whether it's a group chat

        Returns:
            Formatted text optimized for embedding
        """
        date_str = self.start_time.strftime("%B %d, %Y")
        time_str = self.start_time.strftime("%I:%M %p")

        if self.is_group:
            context = f"Group chat '{self.group_name or 'Unnamed'}' on {date_str}"
        else:
            context = f"Conversation with {self.contact} on {date_str} at {time_str}"

        return f"{context}:\n\n{self.text}"

    def to_dict(self) -> Dict:
        """
        Convert to dictionary for storage.

        Note: ChromaDB doesn't accept None values in metadata,
        so we only include fields that have values.
        """
        result = {
            "chunk_id": self.chunk_id,
            "contact": self.contact,
            "text": self.text,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat(),
            "message_count": self.message_count,
            "is_group": self.is_group,
            "word_count": self.word_count,
            "duration_minutes": self.duration_minutes,
        }

        # Only add group_name if it has a value (ChromaDB rejects None)
        if self.group_name:
            result["group_name"] = self.group_name

        return result


class ConversationChunker:
    """
    Groups messages into embeddable conversation chunks.

    Uses time-based windowing with intelligent boundaries:
    - Messages within `window_hours` are grouped together
    - Chunks are split if they exceed `max_words`
    - Short chunks are merged if consecutive and same contact

    Args:
        window_hours: Max time between messages in same chunk (default: 4)
        min_words: Minimum words for a standalone chunk (default: 20)
        max_words: Maximum words before splitting (default: 500)
        min_messages: Minimum messages for a chunk (default: 2)

    Example:
        chunker = ConversationChunker(window_hours=4, max_words=400)
        chunks = chunker.chunk_messages(messages)
    """

    def __init__(
        self,
        window_hours: float = 4.0,
        min_words: int = 20,
        max_words: int = 500,
        min_messages: int = 2,
    ):
        self.window_hours = window_hours
        self.min_words = min_words
        self.max_words = max_words
        self.min_messages = min_messages

        # Cache for deduplication
        self._seen_chunk_ids: set = set()

    def chunk_messages(
        self,
        messages: List[Dict],
        contact_name: Optional[str] = None,
    ) -> List[ConversationChunk]:
        """
        Convert a list of messages into conversation chunks.

        Args:
            messages: List of message dicts from MessagesInterface
            contact_name: Optional contact name to use (otherwise uses phone)

        Returns:
            List of ConversationChunk objects ready for embedding

        Complexity: O(n log n) due to sorting, where n = number of messages.
        The grouping and chunking are O(n) linear passes.
        """
        if not messages:
            return []

        # Sort by date (oldest first for chronological chunking)
        sorted_messages = sorted(
            messages,
            key=lambda m: m.get("date") or "1970-01-01",
        )

        # Group by contact/conversation
        grouped = self._group_by_contact(sorted_messages)

        chunks = []
        for contact, contact_messages in grouped.items():
            # Use provided contact_name if available
            display_name = contact_name if contact_name and len(grouped) == 1 else contact

            # Create time-windowed chunks
            windowed = self._create_time_windows(contact_messages, display_name)

            # Merge small chunks, split large ones
            normalized = self._normalize_chunk_sizes(windowed)

            chunks.extend(normalized)

        # Filter duplicates
        unique_chunks = self._deduplicate(chunks)

        logger.info(f"Created {len(unique_chunks)} chunks from {len(messages)} messages")
        return unique_chunks

    def _group_by_contact(self, messages: List[Dict]) -> Dict[str, List[Dict]]:
        """
        Group messages by contact/conversation.

        Separates group chats from 1:1 conversations.
        Uses enriched contact names when available (set by retriever).

        Returns:
            Dict mapping contact identifier to list of messages
        """
        grouped = defaultdict(list)

        for msg in messages:
            if msg.get("is_group_chat"):
                # Group chats use group_id as key
                key = msg.get("group_id") or "unknown_group"
            else:
                # Prefer enriched contact name, fall back to phone
                key = msg.get("_contact_name") or msg.get("phone") or "unknown"

            grouped[key].append(msg)

        return dict(grouped)

    def _create_time_windows(
        self,
        messages: List[Dict],
        contact: str,
    ) -> List[ConversationChunk]:
        """
        Create chunks based on time gaps between messages.

        Messages within `window_hours` of each other are grouped.
        A gap larger than `window_hours` starts a new chunk.

        Args:
            messages: Messages for a single contact (sorted by date)
            contact: Contact name/identifier

        Returns:
            List of time-windowed chunks
        """
        if not messages:
            return []

        chunks = []
        current_messages = []
        last_time = None
        window_delta = timedelta(hours=self.window_hours)

        for msg in messages:
            msg_time = self._parse_datetime(msg.get("date"))
            if msg_time is None:
                continue

            # Check if this message starts a new window
            if last_time and (msg_time - last_time) > window_delta:
                # Save current chunk and start new one
                if current_messages:
                    chunk = self._create_chunk(current_messages, contact)
                    if chunk:
                        chunks.append(chunk)
                current_messages = []

            current_messages.append(msg)
            last_time = msg_time

        # Don't forget the last chunk
        if current_messages:
            chunk = self._create_chunk(current_messages, contact)
            if chunk:
                chunks.append(chunk)

        return chunks

    def _create_chunk(
        self,
        messages: List[Dict],
        contact: str,
    ) -> Optional[ConversationChunk]:
        """
        Create a single chunk from a list of messages.

        Args:
            messages: List of messages for this chunk
            contact: Contact name/identifier

        Returns:
            ConversationChunk or None if too short
        """
        if len(messages) < self.min_messages:
            return None

        # Build conversation text
        lines = []
        for msg in messages:
            sender = "You" if msg.get("is_from_me") else contact
            text = msg.get("text", "").strip()
            if text and text != "[message content not available]":
                lines.append(f"{sender}: {text}")

        if not lines:
            return None

        text = "\n".join(lines)

        # Check minimum word count
        if len(text.split()) < self.min_words:
            return None

        # Parse timestamps
        first_msg = messages[0]
        last_msg = messages[-1]
        start_time = self._parse_datetime(first_msg.get("date")) or datetime.now()
        end_time = self._parse_datetime(last_msg.get("date")) or start_time

        # Determine if group chat
        is_group = any(m.get("is_group_chat") for m in messages)
        group_name = first_msg.get("display_name") if is_group else None

        # Generate unique ID
        chunk_id = self._generate_chunk_id(contact, start_time, text)

        return ConversationChunk(
            chunk_id=chunk_id,
            contact=contact,
            text=text,
            start_time=start_time,
            end_time=end_time,
            message_count=len(messages),
            is_group=is_group,
            group_name=group_name,
            metadata={
                "phones": list(set(m.get("phone") for m in messages if m.get("phone"))),
            },
        )

    def _normalize_chunk_sizes(
        self,
        chunks: List[ConversationChunk],
    ) -> List[ConversationChunk]:
        """
        Merge small chunks and split large ones.

        Ensures chunks are within the target size range for optimal
        embedding quality.

        Args:
            chunks: List of time-windowed chunks

        Returns:
            Size-normalized chunks
        """
        if not chunks:
            return []

        normalized = []

        for chunk in chunks:
            if chunk.word_count > self.max_words:
                # Split large chunks at natural boundaries
                split_chunks = self._split_large_chunk(chunk)
                normalized.extend(split_chunks)
            else:
                normalized.append(chunk)

        # TODO: Could also merge consecutive small chunks here
        # For now, we keep them separate as they represent distinct
        # time windows which is semantically meaningful

        return normalized

    def _split_large_chunk(
        self,
        chunk: ConversationChunk,
    ) -> List[ConversationChunk]:
        """
        Split a large chunk at message boundaries.

        Tries to split at natural conversation breaks while keeping
        each part above the minimum size.

        Args:
            chunk: Chunk that exceeds max_words

        Returns:
            List of smaller chunks
        """
        lines = chunk.text.split("\n")

        if len(lines) <= 1:
            # Can't split a single line, just return as-is
            return [chunk]

        # Split roughly in half by line count
        # (A more sophisticated approach would use word count)
        mid = len(lines) // 2

        first_text = "\n".join(lines[:mid])
        second_text = "\n".join(lines[mid:])

        # Estimate time split (assume uniform distribution)
        duration = chunk.end_time - chunk.start_time
        mid_time = chunk.start_time + (duration / 2)

        first_chunk = ConversationChunk(
            chunk_id=self._generate_chunk_id(chunk.contact, chunk.start_time, first_text),
            contact=chunk.contact,
            text=first_text,
            start_time=chunk.start_time,
            end_time=mid_time,
            message_count=mid,
            is_group=chunk.is_group,
            group_name=chunk.group_name,
            metadata=chunk.metadata,
        )

        second_chunk = ConversationChunk(
            chunk_id=self._generate_chunk_id(chunk.contact, mid_time, second_text),
            contact=chunk.contact,
            text=second_text,
            start_time=mid_time,
            end_time=chunk.end_time,
            message_count=chunk.message_count - mid,
            is_group=chunk.is_group,
            group_name=chunk.group_name,
            metadata=chunk.metadata,
        )

        result = []

        # Recursively split if still too large
        if first_chunk.word_count > self.max_words:
            result.extend(self._split_large_chunk(first_chunk))
        else:
            result.append(first_chunk)

        if second_chunk.word_count > self.max_words:
            result.extend(self._split_large_chunk(second_chunk))
        else:
            result.append(second_chunk)

        return result

    def _deduplicate(
        self,
        chunks: List[ConversationChunk],
    ) -> List[ConversationChunk]:
        """
        Remove duplicate chunks based on chunk_id.

        Args:
            chunks: List of chunks to deduplicate

        Returns:
            List with duplicates removed
        """
        unique = []
        seen = set()

        for chunk in chunks:
            if chunk.chunk_id not in seen:
                seen.add(chunk.chunk_id)
                unique.append(chunk)

        return unique

    def _generate_chunk_id(
        self,
        contact: str,
        timestamp: datetime,
        text: str,
    ) -> str:
        """
        Generate a unique, deterministic ID for a chunk.

        Uses SHA256 hash of contact + timestamp + text content.
        This ensures the same conversation always gets the same ID,
        enabling incremental updates without re-indexing unchanged data.

        Args:
            contact: Contact identifier
            timestamp: Start time of chunk
            text: Chunk text content

        Returns:
            12-character hex string (truncated SHA256)
        """
        content = f"{contact}|{timestamp.isoformat()}|{text}"
        hash_obj = hashlib.sha256(content.encode("utf-8"))
        return hash_obj.hexdigest()[:12]

    def _parse_datetime(self, date_str: Optional[str]) -> Optional[datetime]:
        """
        Parse ISO format datetime string.

        Args:
            date_str: ISO format datetime string

        Returns:
            datetime object or None if parsing fails
        """
        if not date_str:
            return None

        try:
            # Handle various ISO formats
            # Strip timezone info for simplicity
            if "+" in date_str:
                date_str = date_str.split("+")[0]
            if "Z" in date_str:
                date_str = date_str.replace("Z", "")

            return datetime.fromisoformat(date_str)
        except (ValueError, TypeError):
            logger.debug(f"Failed to parse datetime: {date_str}")
            return None


def chunk_for_contact(
    messages: List[Dict],
    contact_name: str,
    **kwargs,
) -> List[ConversationChunk]:
    """
    Convenience function to chunk messages for a specific contact.

    Args:
        messages: Messages from MessagesInterface
        contact_name: Human-readable contact name
        **kwargs: Additional arguments for ConversationChunker

    Returns:
        List of conversation chunks

    Example:
        from src.messages_interface import MessagesInterface

        mi = MessagesInterface()
        messages = mi.get_recent_messages("+14155551234", limit=100)
        chunks = chunk_for_contact(messages, "John Doe")
    """
    chunker = ConversationChunker(**kwargs)
    return chunker.chunk_messages(messages, contact_name=contact_name)

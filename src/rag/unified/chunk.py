"""
Unified chunk dataclass for multi-source RAG.

All data sources produce chunks with this common structure,
enabling cross-source semantic search with consistent metadata.

CS Concept: This is a **Data Transfer Object (DTO)** pattern - a simple
container that carries data between layers without any business logic.
Using dataclasses gives us automatic __init__, __repr__, and comparison.
"""

import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Dict, Any


# Valid source types for the unified RAG system
SOURCE_TYPES = frozenset([
    "imessage",
    "gmail",
    "notes",
    "calendar",
    "slack",
    "superwhisper",
])

# Valid context types
CONTEXT_TYPES = frozenset([
    "conversation",   # iMessage, Slack DM
    "thread",         # Gmail, Slack thread
    "document",       # Notes, documents
    "event",          # Calendar
    "channel",        # Slack channel
    "transcription",  # SuperWhisper
])


@dataclass
class UnifiedChunk:
    """
    Common chunk format for all data sources.

    Attributes:
        chunk_id: Deterministic hash for deduplication
        source: Data source type (imessage, gmail, notes, etc.)
        text: Main text content to embed
        title: Optional title (subject, filename, event title)
        context_id: Grouping identifier (contact, thread_id, file path)
        context_type: Type of context (conversation, thread, document)
        timestamp: Primary timestamp in UTC
        end_timestamp: End time for duration-based content
        participants: List of people involved
        tags: Labels, categories, life areas
        word_count: Approximate word count
        metadata: Source-specific additional data
    """

    # Required fields
    source: str
    text: str
    context_id: str
    context_type: str
    timestamp: datetime

    # Optional fields
    chunk_id: Optional[str] = None  # Auto-generated if not provided
    title: Optional[str] = None
    end_timestamp: Optional[datetime] = None
    participants: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    word_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """Validate and compute derived fields."""
        # Validate source
        if self.source not in SOURCE_TYPES:
            raise ValueError(
                f"Invalid source '{self.source}'. Must be one of: {sorted(SOURCE_TYPES)}"
            )

        # Validate context_type
        if self.context_type not in CONTEXT_TYPES:
            raise ValueError(
                f"Invalid context_type '{self.context_type}'. "
                f"Must be one of: {sorted(CONTEXT_TYPES)}"
            )

        # Compute word count if not set
        if self.word_count == 0:
            self.word_count = len(self.text.split())

        # Generate chunk_id if not provided
        if self.chunk_id is None:
            self.chunk_id = self._generate_chunk_id()

    def _generate_chunk_id(self) -> str:
        """
        Generate deterministic chunk ID from content.

        Uses SHA256 hash of source|context_id|timestamp|text[:100]
        This ensures:
        - Same content always gets same ID (idempotent indexing)
        - Different content gets different ID (no collisions)
        - ID is reasonably short (12 chars)

        CS Concept: This is a **content-addressable** approach, similar to
        how Git hashes commits. The ID is derived from content, not assigned.
        """
        timestamp_str = self.timestamp.isoformat() if self.timestamp else ""
        content = f"{self.source}|{self.context_id}|{timestamp_str}|{self.text[:100]}"
        return hashlib.sha256(content.encode()).hexdigest()[:12]

    def to_embedding_text(self) -> str:
        """
        Format chunk for embedding.

        Adds context prefix to improve embedding quality.
        The prefix helps the embedding model understand what kind
        of content this is, improving retrieval accuracy.
        """
        prefix_parts = [f"[{self.source}]"]

        if self.title:
            prefix_parts.append(f"Title: {self.title}")

        if self.participants:
            participants_str = ", ".join(self.participants[:5])  # Limit for length
            prefix_parts.append(f"With: {participants_str}")

        if self.tags:
            prefix_parts.append(f"Tags: {', '.join(self.tags[:5])}")

        prefix = " | ".join(prefix_parts)
        return f"{prefix}\n\n{self.text}"

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert to dict for ChromaDB metadata storage.

        ChromaDB metadata has restrictions:
        - Values must be str, int, float, or bool
        - No None values
        - No nested objects

        So we flatten and filter appropriately.
        """
        result = {
            "chunk_id": self.chunk_id,
            "source": self.source,
            "text": self.text,
            "context_id": self.context_id,
            "context_type": self.context_type,
            "word_count": self.word_count,
        }

        # Add timestamp as ISO string
        if self.timestamp:
            result["timestamp"] = self.timestamp.isoformat()

        if self.end_timestamp:
            result["end_timestamp"] = self.end_timestamp.isoformat()

        if self.title:
            result["title"] = self.title

        # Store lists as comma-separated strings
        if self.participants:
            result["participants"] = ",".join(self.participants)

        if self.tags:
            result["tags"] = ",".join(self.tags)

        # Flatten simple metadata values
        for key, value in self.metadata.items():
            if isinstance(value, (str, int, float, bool)):
                result[f"meta_{key}"] = value

        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "UnifiedChunk":
        """
        Reconstruct chunk from stored dict.

        Reverses the to_dict() transformation.
        """
        # Parse timestamp
        timestamp = None
        if data.get("timestamp"):
            timestamp = datetime.fromisoformat(data["timestamp"])

        end_timestamp = None
        if data.get("end_timestamp"):
            end_timestamp = datetime.fromisoformat(data["end_timestamp"])

        # Parse lists from comma-separated strings
        participants = []
        if data.get("participants"):
            participants = data["participants"].split(",")

        tags = []
        if data.get("tags"):
            tags = data["tags"].split(",")

        # Extract metadata fields
        metadata = {}
        for key, value in data.items():
            if key.startswith("meta_"):
                metadata[key[5:]] = value  # Remove "meta_" prefix

        return cls(
            chunk_id=data.get("chunk_id"),
            source=data["source"],
            text=data["text"],
            title=data.get("title"),
            context_id=data["context_id"],
            context_type=data["context_type"],
            timestamp=timestamp,
            end_timestamp=end_timestamp,
            participants=participants,
            tags=tags,
            word_count=data.get("word_count", 0),
            metadata=metadata,
        )

    @property
    def duration_minutes(self) -> Optional[float]:
        """Calculate duration in minutes if both timestamps present."""
        if self.timestamp and self.end_timestamp:
            delta = self.end_timestamp - self.timestamp
            return delta.total_seconds() / 60
        return None

    def __repr__(self) -> str:
        """Concise string representation."""
        text_preview = self.text[:50] + "..." if len(self.text) > 50 else self.text
        return (
            f"UnifiedChunk(source={self.source!r}, "
            f"context={self.context_id!r}, "
            f"text={text_preview!r})"
        )

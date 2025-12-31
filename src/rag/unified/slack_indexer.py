"""
Slack message indexer.

Indexes Slack messages using the Rube MCP tools. Messages are grouped
into conversation chunks using time-window-based grouping similar to
the iMessage approach.

Note: This indexer is designed to be called from the MCP server context
where Rube/Slack tools are available.
"""

import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Callable

from .base_indexer import BaseSourceIndexer
from .chunk import UnifiedChunk

logger = logging.getLogger(__name__)


class SlackIndexer(BaseSourceIndexer):
    """
    Indexes Slack messages into conversation chunks.

    Messages are grouped by channel and time window to create
    coherent conversation chunks for semantic search.

    Args:
        slack_fetcher: Function to fetch Slack messages
        window_hours: Hours for grouping messages into chunks
        min_messages: Minimum messages per chunk
        store: Optional UnifiedVectorStore to use
        use_local_embeddings: Use local embeddings instead of OpenAI

    Example:
        indexer = SlackIndexer(window_hours=4.0)
        messages = [...]  # Fetched via Rube MCP
        result = indexer.index_with_data(messages)
    """

    source_name = "slack"

    def __init__(
        self,
        slack_fetcher: Optional[Callable] = None,
        window_hours: float = 4.0,
        min_messages: int = 2,
        min_words: int = 20,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.slack_fetcher = slack_fetcher
        self.window_hours = window_hours
        self.min_messages = min_messages
        self.min_words = min_words

    def fetch_data(
        self,
        days: Optional[int] = None,
        limit: Optional[int] = None,
        **kwargs,
    ) -> List[Dict[str, Any]]:
        """
        Fetch messages - requires slack_fetcher to be set.

        For direct use, call index_with_data() with pre-fetched messages.
        """
        logger.warning(
            "SlackIndexer.fetch_data() is a stub. "
            "Use index_with_data() with pre-fetched messages."
        )
        return []

    def index_with_data(
        self,
        messages: List[Dict[str, Any]],
        batch_size: int = 100,
    ) -> Dict[str, Any]:
        """
        Index pre-fetched Slack messages.

        Args:
            messages: List of Slack message dicts
            batch_size: Batch size for embeddings

        Returns:
            Dict with indexing stats
        """
        start_time = datetime.now()

        if not messages:
            return {
                "success": True,
                "source": self.source_name,
                "chunks_found": 0,
                "chunks_indexed": 0,
                "duration_seconds": 0,
            }

        # Convert to chunks
        chunks = self.chunk_data(messages)

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

    def chunk_data(self, messages: List[Dict[str, Any]]) -> List[UnifiedChunk]:
        """
        Convert messages to UnifiedChunks using time-window grouping.
        """
        if not messages:
            return []

        # Group by channel
        by_channel: Dict[str, List[Dict]] = {}
        for msg in messages:
            channel = msg.get("channel") or msg.get("channel_id", "unknown")
            if channel not in by_channel:
                by_channel[channel] = []
            by_channel[channel].append(msg)

        chunks = []

        for channel_id, channel_msgs in by_channel.items():
            channel_chunks = self._chunk_channel_messages(channel_id, channel_msgs)
            chunks.extend(channel_chunks)

        logger.info(
            f"Created {len(chunks)} Slack chunks from {len(messages)} messages "
            f"across {len(by_channel)} channels"
        )
        return chunks

    def _chunk_channel_messages(
        self,
        channel_id: str,
        messages: List[Dict[str, Any]],
    ) -> List[UnifiedChunk]:
        """Group messages from one channel into time-windowed chunks."""
        if not messages:
            return []

        # Sort by timestamp
        sorted_msgs = sorted(messages, key=lambda m: self._get_timestamp(m))

        chunks = []
        window_msgs = []
        window_start = None
        channel_name = None

        for msg in sorted_msgs:
            msg_time = self._get_timestamp(msg)
            if not msg_time:
                continue

            # Get channel name from first message
            if channel_name is None:
                channel_name = msg.get("channel_name", msg.get("channel", channel_id))

            # Check if message fits in current window
            if window_start is None:
                window_start = msg_time
                window_msgs = [msg]
            elif (msg_time - window_start).total_seconds() / 3600 <= self.window_hours:
                window_msgs.append(msg)
            else:
                # Window complete, create chunk
                chunk = self._create_chunk(
                    channel_id, channel_name, window_msgs, window_start
                )
                if chunk:
                    chunks.append(chunk)

                # Start new window
                window_start = msg_time
                window_msgs = [msg]

        # Handle remaining messages
        if window_msgs:
            chunk = self._create_chunk(
                channel_id, channel_name, window_msgs, window_start
            )
            if chunk:
                chunks.append(chunk)

        return chunks

    def _create_chunk(
        self,
        channel_id: str,
        channel_name: str,
        messages: List[Dict],
        start_time: datetime,
    ) -> Optional[UnifiedChunk]:
        """Create a UnifiedChunk from a group of messages."""
        if len(messages) < self.min_messages:
            return None

        # Format messages
        text_lines = []
        participants = set()
        end_time = start_time

        for msg in messages:
            user = msg.get("user") or msg.get("user_name", "Unknown")
            text = msg.get("text", "")
            msg_time = self._get_timestamp(msg)

            if msg_time and msg_time > end_time:
                end_time = msg_time

            participants.add(user)
            text_lines.append(f"{user}: {text}")

        full_text = "\n".join(text_lines)

        # Check minimum word count
        if len(full_text.split()) < self.min_words:
            return None

        # Determine if this is a thread
        is_thread = any(msg.get("thread_ts") for msg in messages)

        return UnifiedChunk(
            source="slack",
            text=full_text,
            title=f"#{channel_name}" if channel_name else f"Channel {channel_id}",
            context_id=channel_id,
            context_type="channel",
            timestamp=start_time,
            end_timestamp=end_time,
            participants=list(participants),
            tags=[],
            metadata={
                "channel_name": channel_name,
                "message_count": len(messages),
                "is_thread": is_thread,
                "duration_minutes": (end_time - start_time).total_seconds() / 60,
            },
        )

    def _get_timestamp(self, msg: Dict) -> Optional[datetime]:
        """Extract timestamp from Slack message."""
        # Slack timestamps can be in various formats
        ts = msg.get("ts") or msg.get("timestamp")

        if not ts:
            return None

        # Slack ts format: "1234567890.123456"
        if isinstance(ts, str) and "." in ts:
            try:
                epoch = float(ts)
                return datetime.fromtimestamp(epoch)
            except (ValueError, OSError):
                pass

        # Try as epoch integer
        if isinstance(ts, (int, float)):
            try:
                return datetime.fromtimestamp(float(ts))
            except (ValueError, OSError):
                pass

        # Try as ISO string
        if isinstance(ts, str):
            try:
                return datetime.fromisoformat(ts.replace("Z", "+00:00"))
            except ValueError:
                pass

        return None

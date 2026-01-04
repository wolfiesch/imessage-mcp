"""
Persistent state tracking for incremental indexing.

Stores last_indexed_at timestamps per source to enable delta indexing.
This prevents re-processing unchanged messages and dramatically speeds up
re-indexing operations (35s → <1s for no-op runs).

CS Concept: **Watermarking** - tracking progress through infinite streams.
Similar to Kafka consumer offsets or database replication cursors.
"""

from pathlib import Path
from datetime import datetime
import json
from typing import Optional
import logging

logger = logging.getLogger(__name__)


class IndexState:
    """
    Track last successful index time per source.

    Stores state in a JSON file for persistence across runs.
    Each source (imessage, gmail, notes, etc.) has its own timestamp.

    Args:
        state_file: Path to JSON state file (default: ~/.imessage_rag/index_state.json)

    Example:
        state = IndexState()

        # First run - no state exists
        last_indexed = state.get_last_indexed("imessage")  # Returns None

        # Index messages...

        # Update state after successful indexing
        state.update_last_indexed("imessage", datetime.now())

        # Second run - state exists
        last_indexed = state.get_last_indexed("imessage")  # Returns datetime
    """

    def __init__(self, state_file: Optional[Path] = None):
        if state_file is None:
            # Default: ~/.imessage_rag/index_state.json
            state_file = Path.home() / ".imessage_rag" / "index_state.json"

        self.state_file = Path(state_file)
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self._state = {}
        self._load()

    def _load(self):
        """Load state from JSON file."""
        if self.state_file.exists():
            try:
                with open(self.state_file) as f:
                    self._state = json.load(f)
                logger.info(f"Loaded index state from {self.state_file}")
            except (json.JSONDecodeError, IOError) as e:
                logger.warning(f"Failed to load index state: {e}. Starting fresh.")
                self._state = {}
        else:
            logger.info(f"No existing index state at {self.state_file}")
            self._state = {}

    def _save(self):
        """Save state to JSON file."""
        try:
            with open(self.state_file, 'w') as f:
                json.dump(self._state, f, indent=2)
            logger.debug(f"Saved index state to {self.state_file}")
        except IOError as e:
            logger.error(f"Failed to save index state: {e}")

    def get_last_indexed(self, source: str) -> Optional[datetime]:
        """
        Get last indexed timestamp for source.

        Args:
            source: Source name (e.g., "imessage", "gmail", "notes")

        Returns:
            datetime of last successful index, or None if never indexed
        """
        timestamp_str = self._state.get(source)
        if timestamp_str:
            try:
                return datetime.fromisoformat(timestamp_str)
            except ValueError as e:
                logger.warning(f"Invalid timestamp for {source}: {e}")
                return None
        return None

    def update_last_indexed(self, source: str, timestamp: datetime):
        """
        Update last indexed timestamp for source.

        Args:
            source: Source name (e.g., "imessage", "gmail", "notes")
            timestamp: datetime of last successfully indexed message

        Note: Automatically saves to disk after updating.
        """
        self._state[source] = timestamp.isoformat()
        self._save()
        logger.info(f"Updated index state for {source}: {timestamp.isoformat()}")

    def reset(self, source: Optional[str] = None):
        """
        Reset state for source (or all if None).

        Args:
            source: Source to reset, or None to reset all sources

        Example:
            # Reset just iMessage
            state.reset("imessage")

            # Reset everything
            state.reset()
        """
        if source:
            if source in self._state:
                del self._state[source]
                logger.info(f"Reset index state for {source}")
        else:
            self._state = {}
            logger.info("Reset all index state")

        self._save()

    def get_all_states(self) -> dict:
        """
        Get all source states.

        Returns:
            Dict mapping source names to ISO timestamp strings
        """
        return self._state.copy()

"""
SuperWhisper voice transcription indexer.

Indexes voice recordings from ~/Documents/superwhisper/recordings/
Each recording has a meta.json with transcription text and metadata.

This is the simplest indexer since data is local JSON files.
"""

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

from .base_indexer import BaseSourceIndexer
from .chunk import UnifiedChunk

logger = logging.getLogger(__name__)


# Default SuperWhisper data location
DEFAULT_SUPERWHISPER_PATH = Path.home() / "Documents" / "superwhisper" / "recordings"


class SuperWhisperIndexer(BaseSourceIndexer):
    """
    Indexes SuperWhisper voice transcriptions.

    Each recording is stored in a folder named by timestamp (e.g., 1764978472/)
    containing:
    - meta.json: Transcription text and metadata
    - output.wav: Audio file (not indexed)

    Args:
        recordings_path: Path to recordings directory
        store: Optional UnifiedVectorStore to use
        use_local_embeddings: Use local embeddings instead of OpenAI

    Example:
        indexer = SuperWhisperIndexer()
        result = indexer.index(days=30)  # Index last 30 days
        print(f"Indexed {result['chunks_indexed']} recordings")
    """

    source_name = "superwhisper"

    def __init__(
        self,
        recordings_path: Optional[Path] = None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.recordings_path = recordings_path or DEFAULT_SUPERWHISPER_PATH

        if not self.recordings_path.exists():
            logger.warning(
                f"SuperWhisper recordings not found at {self.recordings_path}"
            )

    def fetch_data(
        self,
        days: Optional[int] = None,
        limit: Optional[int] = None,
        **kwargs,
    ) -> List[Dict[str, Any]]:
        """
        Load recordings from the filesystem.

        Args:
            days: Only fetch recordings from last N days
            limit: Maximum number of recordings to fetch

        Returns:
            List of recording dicts with id and meta
        """
        if not self.recordings_path.exists():
            logger.warning(f"Recordings path does not exist: {self.recordings_path}")
            return []

        recordings = []
        cutoff_date = None
        if days:
            cutoff_date = self.days_ago(days)

        # Get all recording directories
        recording_dirs = []
        for item in self.recordings_path.iterdir():
            if item.is_dir() and item.name.isdigit():
                recording_dirs.append(item)

        # Sort by timestamp (most recent first for limit)
        recording_dirs.sort(key=lambda x: int(x.name), reverse=True)

        for recording_dir in recording_dirs:
            meta_path = recording_dir / "meta.json"
            if not meta_path.exists():
                continue

            try:
                with open(meta_path, "r", encoding="utf-8") as f:
                    meta = json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                logger.warning(f"Failed to read {meta_path}: {e}")
                continue

            # Parse datetime for filtering
            recording_dt = None
            if meta.get("datetime"):
                try:
                    recording_dt = datetime.fromisoformat(meta["datetime"])
                except ValueError:
                    pass

            # Apply date filter
            if cutoff_date and recording_dt and recording_dt < cutoff_date:
                continue

            # Skip empty transcriptions
            if not meta.get("result"):
                continue

            recordings.append({
                "id": recording_dir.name,
                "meta": meta,
                "datetime": recording_dt,
            })

            # Apply limit
            if limit and len(recordings) >= limit:
                break

        logger.info(f"Found {len(recordings)} SuperWhisper recordings")
        return recordings

    def chunk_data(self, recordings: List[Dict[str, Any]]) -> List[UnifiedChunk]:
        """
        Convert recordings to UnifiedChunks.

        Each recording becomes one chunk (they're typically short voice notes).
        """
        chunks = []

        for recording in recordings:
            chunk = self._recording_to_chunk(recording)
            if chunk:
                chunks.append(chunk)

        return chunks

    def _recording_to_chunk(self, recording: Dict[str, Any]) -> Optional[UnifiedChunk]:
        """Convert a single recording to a UnifiedChunk."""
        meta = recording.get("meta", {})
        recording_id = recording.get("id", "")
        recording_dt = recording.get("datetime")

        # Get transcription text
        text = meta.get("result", "")
        if not text or len(text.strip()) < 10:
            return None

        # Extract mode name for tagging
        mode_name = meta.get("modeName", "Unknown")

        # Duration in seconds
        duration_ms = meta.get("duration", 0)
        duration_sec = duration_ms / 1000 if duration_ms else 0

        # Build title from mode and duration
        duration_str = f"{duration_sec:.0f}s" if duration_sec else ""
        title = f"Voice note ({mode_name})"
        if duration_str:
            title = f"Voice note ({mode_name}, {duration_str})"

        return UnifiedChunk(
            source="superwhisper",
            text=text,
            title=title,
            context_id=recording_id,
            context_type="transcription",
            timestamp=recording_dt or datetime.now(),
            participants=[],  # Voice notes are self-directed
            tags=[mode_name] if mode_name else [],
            metadata={
                "duration_ms": duration_ms,
                "model": meta.get("modelName", ""),
                "model_key": meta.get("modelKey", ""),
                "processing_time": meta.get("processingTime", 0),
                "has_segments": bool(meta.get("segments")),
                "segment_count": len(meta.get("segments", [])),
                "app_version": meta.get("appVersion", ""),
            },
        )

    def get_recording_dates(self) -> Dict[str, datetime]:
        """
        Get date range of recordings.

        Returns:
            Dict with oldest and newest recording dates
        """
        recordings = self.fetch_data(limit=None)
        if not recordings:
            return {"oldest": None, "newest": None}

        dates = [r["datetime"] for r in recordings if r.get("datetime")]
        if not dates:
            return {"oldest": None, "newest": None}

        return {
            "oldest": min(dates),
            "newest": max(dates),
        }

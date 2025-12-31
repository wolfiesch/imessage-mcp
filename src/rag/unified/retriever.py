"""
Unified retriever for cross-source semantic search.

Provides a high-level interface for searching across all indexed
sources with result formatting for Claude consumption.

CS Concept: This is the **Facade Pattern** again - hiding the
complexity of multiple collections and search logic behind a
simple interface.
"""

import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any, Optional

from .chunk import SOURCE_TYPES
from .store import UnifiedVectorStore
from .superwhisper_indexer import SuperWhisperIndexer
from .notes_indexer import NotesIndexer
from .gmail_indexer import GmailIndexer
from .slack_indexer import SlackIndexer
from .calendar_indexer import CalendarIndexer

logger = logging.getLogger(__name__)


class UnifiedRetriever:
    """
    High-level interface for unified RAG operations.

    Provides methods for:
    - Indexing all or specific sources
    - Cross-source semantic search
    - Formatted context retrieval for Claude

    Args:
        persist_directory: ChromaDB storage location
        use_local_embeddings: Use local embeddings instead of OpenAI

    Example:
        retriever = UnifiedRetriever()

        # Index local sources
        retriever.index_superwhisper(days=30)
        retriever.index_notes()

        # Search across all sources
        results = retriever.search("dinner plans", limit=10)

        # Format for Claude
        context = retriever.ask("What restaurant did Sarah recommend?")
    """

    def __init__(
        self,
        persist_directory: Optional[str] = None,
        use_local_embeddings: bool = False,
    ):
        # Default persist directory
        if persist_directory is None:
            project_root = Path(__file__).parent.parent.parent.parent
            persist_directory = str(project_root / "data" / "chroma")

        self.store = UnifiedVectorStore(
            persist_directory=persist_directory,
            use_local_embeddings=use_local_embeddings,
        )

        # Lazy-initialize indexers
        self._superwhisper_indexer: Optional[SuperWhisperIndexer] = None
        self._notes_indexer: Optional[NotesIndexer] = None
        self._gmail_indexer: Optional[GmailIndexer] = None
        self._slack_indexer: Optional[SlackIndexer] = None
        self._calendar_indexer: Optional[CalendarIndexer] = None

    # === Indexing Methods ===

    def index_superwhisper(
        self,
        days: Optional[int] = None,
        limit: Optional[int] = None,
        recordings_path: Optional[Path] = None,
    ) -> Dict[str, Any]:
        """
        Index SuperWhisper voice transcriptions.

        Args:
            days: Only index recordings from last N days
            limit: Maximum recordings to index
            recordings_path: Custom path to recordings

        Returns:
            Dict with indexing stats
        """
        if self._superwhisper_indexer is None:
            self._superwhisper_indexer = SuperWhisperIndexer(
                store=self.store,
                recordings_path=recordings_path,
            )

        return self._superwhisper_indexer.index(days=days, limit=limit)

    def index_notes(
        self,
        days: Optional[int] = None,
        limit: Optional[int] = None,
        notes_path: Optional[Path] = None,
    ) -> Dict[str, Any]:
        """
        Index markdown notes/documents.

        Args:
            days: Only index files modified in last N days
            limit: Maximum files to index
            notes_path: Custom path to notes directory

        Returns:
            Dict with indexing stats
        """
        if self._notes_indexer is None:
            self._notes_indexer = NotesIndexer(
                store=self.store,
                notes_path=notes_path,
            )

        return self._notes_indexer.index(days=days, limit=limit)

    def index_gmail(
        self,
        emails: List[Dict[str, Any]],
        batch_size: int = 100,
    ) -> Dict[str, Any]:
        """
        Index Gmail emails (pre-fetched data).

        Args:
            emails: List of email dicts from Gmail MCP
            batch_size: Batch size for embeddings

        Returns:
            Dict with indexing stats
        """
        if self._gmail_indexer is None:
            self._gmail_indexer = GmailIndexer(store=self.store)

        return self._gmail_indexer.index_with_data(emails, batch_size=batch_size)

    def index_slack(
        self,
        messages: List[Dict[str, Any]],
        batch_size: int = 100,
    ) -> Dict[str, Any]:
        """
        Index Slack messages (pre-fetched data).

        Args:
            messages: List of message dicts from Slack MCP
            batch_size: Batch size for embeddings

        Returns:
            Dict with indexing stats
        """
        if self._slack_indexer is None:
            self._slack_indexer = SlackIndexer(store=self.store)

        return self._slack_indexer.index_with_data(messages, batch_size=batch_size)

    def index_calendar(
        self,
        events: List[Dict[str, Any]],
        batch_size: int = 100,
    ) -> Dict[str, Any]:
        """
        Index calendar events (pre-fetched data).

        Args:
            events: List of event dicts from Calendar API
            batch_size: Batch size for embeddings

        Returns:
            Dict with indexing stats
        """
        if self._calendar_indexer is None:
            self._calendar_indexer = CalendarIndexer(store=self.store)

        return self._calendar_indexer.index_with_data(events, batch_size=batch_size)

    def index_local_sources(
        self,
        days: Optional[int] = 30,
    ) -> Dict[str, Any]:
        """
        Index all local sources (SuperWhisper + Notes).

        This is a convenience method for indexing sources that
        don't require external API calls.

        Args:
            days: Number of days of history to index

        Returns:
            Combined indexing stats
        """
        results = {}

        # Index SuperWhisper
        sw_result = self.index_superwhisper(days=days)
        results["superwhisper"] = sw_result

        # Index Notes
        notes_result = self.index_notes(days=days)
        results["notes"] = notes_result

        # Summary
        total_chunks = sum(
            r.get("chunks_indexed", 0)
            for r in results.values()
            if isinstance(r, dict)
        )

        return {
            "by_source": results,
            "total_chunks_indexed": total_chunks,
        }

    # === Search Methods ===

    def search(
        self,
        query: str,
        sources: Optional[List[str]] = None,
        limit: int = 10,
        days: Optional[int] = None,
        participants: Optional[List[str]] = None,
        tags: Optional[List[str]] = None,
    ) -> List[Dict]:
        """
        Semantic search across indexed sources.

        Args:
            query: Natural language search query
            sources: List of sources to search (None = all)
            limit: Maximum results to return
            days: Only search content from last N days
            participants: Filter by participant names
            tags: Filter by tags

        Returns:
            List of search result dicts sorted by relevance
        """
        # Convert days to date filter
        min_date = None
        if days:
            min_date = datetime.now() - timedelta(days=days)

        return self.store.search(
            query=query,
            sources=sources,
            limit=limit,
            min_date=min_date,
            participants=participants,
            tags=tags,
        )

    def ask(
        self,
        question: str,
        sources: Optional[List[str]] = None,
        limit: int = 5,
        days: Optional[int] = None,
    ) -> str:
        """
        Search and format results for Claude consumption.

        Args:
            question: Natural language question
            sources: Sources to search (None = all)
            limit: Maximum results to include
            days: Only search recent content

        Returns:
            Formatted context string ready for Claude
        """
        results = self.search(
            query=question,
            sources=sources,
            limit=limit,
            days=days,
        )

        if not results:
            return f'No relevant content found for: "{question}"'

        # Format results
        formatted = [
            f'Found {len(results)} relevant result(s) for: "{question}"\n'
        ]

        for i, result in enumerate(results, 1):
            score = result.get("score", 0) * 100
            source = result.get("source", "unknown")
            title = result.get("title") or result.get("context_id", "")
            timestamp = result.get("timestamp", "")
            text = result.get("text", "")

            # Format timestamp
            if timestamp:
                try:
                    dt = datetime.fromisoformat(timestamp)
                    timestamp = dt.strftime("%Y-%m-%d %H:%M")
                except ValueError:
                    pass

            # Build header
            header_parts = [f"[{source}]"]
            if title:
                header_parts.append(title)
            if timestamp:
                header_parts.append(timestamp)
            header_parts.append(f"(relevance: {score:.0f}%)")

            formatted.append(f"\n**Result {i}** {' | '.join(header_parts)}:")
            formatted.append(text)
            formatted.append("\n---")

        return "\n".join(formatted)

    # === Stats Methods ===

    def get_stats(self, source: Optional[str] = None) -> Dict[str, Any]:
        """
        Get statistics about indexed content.

        Args:
            source: Specific source to get stats for (None = all)

        Returns:
            Dict with chunk counts, date ranges, etc.
        """
        return self.store.get_stats(source=source)

    def clear(self, source: Optional[str] = None) -> int:
        """
        Clear indexed data.

        Args:
            source: Specific source to clear (None = all)

        Returns:
            Number of chunks deleted
        """
        return self.store.clear(source=source)

    def list_sources(self) -> List[str]:
        """List all available source types."""
        return sorted(SOURCE_TYPES)

    def get_indexed_sources(self) -> List[str]:
        """List sources that have indexed content."""
        stats = self.get_stats()
        by_source = stats.get("by_source", {})

        return [
            source
            for source, info in by_source.items()
            if info.get("chunk_count", 0) > 0
        ]

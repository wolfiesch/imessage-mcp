"""
Base class for source-specific indexers.

Each data source (Gmail, Notes, Calendar, etc.) implements this
interface to produce UnifiedChunks for the vector store.

CS Concept: This is the **Template Method Pattern** - we define the
skeleton of the indexing algorithm in the base class, and subclasses
implement the source-specific steps.
"""

import logging
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any, Generator

from .chunk import UnifiedChunk
from .store import UnifiedVectorStore

logger = logging.getLogger(__name__)


class BaseSourceIndexer(ABC):
    """
    Abstract base class for data source indexers.

    Subclasses must implement:
    - source_name: The source type identifier
    - fetch_data(): Retrieve raw data from the source
    - chunk_data(): Convert raw data to UnifiedChunks

    Example usage:
        class GmailIndexer(BaseSourceIndexer):
            source_name = "gmail"

            def fetch_data(self, days=30, **kwargs):
                return gmail_api.list_emails(after=days_ago(days))

            def chunk_data(self, emails):
                return [self._email_to_chunk(e) for e in emails]
    """

    # Must be set by subclasses
    source_name: str = ""

    def __init__(
        self,
        store: Optional[UnifiedVectorStore] = None,
        use_local_embeddings: bool = False,
    ):
        """
        Initialize indexer.

        Args:
            store: Vector store to use (creates new one if None)
            use_local_embeddings: Use local embeddings instead of OpenAI
        """
        if not self.source_name:
            raise NotImplementedError("Subclass must set source_name")

        self.store = store or UnifiedVectorStore(
            use_local_embeddings=use_local_embeddings
        )
        self._indexed_count = 0

    @abstractmethod
    def fetch_data(
        self,
        days: Optional[int] = None,
        limit: Optional[int] = None,
        **kwargs,
    ) -> Any:
        """
        Fetch raw data from the source.

        Args:
            days: How many days of history to fetch
            limit: Maximum number of items to fetch
            **kwargs: Source-specific options

        Returns:
            Raw data in source-specific format
        """
        pass

    @abstractmethod
    def chunk_data(self, data: Any) -> List[UnifiedChunk]:
        """
        Convert raw data to UnifiedChunks.

        Args:
            data: Raw data from fetch_data()

        Returns:
            List of UnifiedChunk objects ready for indexing
        """
        pass

    def index(
        self,
        days: Optional[int] = None,
        limit: Optional[int] = None,
        batch_size: int = 100,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Full indexing pipeline: fetch -> chunk -> store.

        This is the main entry point for indexing a source.

        Args:
            days: How many days of history to index
            limit: Maximum items to index
            batch_size: Batch size for embedding API
            **kwargs: Source-specific options

        Returns:
            Dict with indexing stats
        """
        start_time = datetime.now()

        logger.info(f"Starting {self.source_name} indexing (days={days}, limit={limit})")

        # Step 1: Fetch data
        try:
            data = self.fetch_data(days=days, limit=limit, **kwargs)
        except Exception as e:
            logger.error(f"Failed to fetch {self.source_name} data: {e}")
            return {
                "success": False,
                "error": str(e),
                "source": self.source_name,
            }

        # Step 2: Convert to chunks
        try:
            chunks = self.chunk_data(data)
        except Exception as e:
            logger.error(f"Failed to chunk {self.source_name} data: {e}")
            return {
                "success": False,
                "error": str(e),
                "source": self.source_name,
            }

        if not chunks:
            logger.info(f"No {self.source_name} chunks to index")
            return {
                "success": True,
                "source": self.source_name,
                "chunks_found": 0,
                "chunks_indexed": 0,
                "duration_seconds": (datetime.now() - start_time).total_seconds(),
            }

        logger.info(f"Created {len(chunks)} {self.source_name} chunks")

        # Step 3: Add to store
        try:
            result = self.store.add_chunks(chunks, batch_size=batch_size)
            indexed_count = result.get(self.source_name, 0)
        except Exception as e:
            logger.error(f"Failed to index {self.source_name} chunks: {e}")
            return {
                "success": False,
                "error": str(e),
                "source": self.source_name,
                "chunks_found": len(chunks),
            }

        duration = (datetime.now() - start_time).total_seconds()
        self._indexed_count += indexed_count

        logger.info(
            f"Indexed {indexed_count} {self.source_name} chunks in {duration:.1f}s"
        )

        return {
            "success": True,
            "source": self.source_name,
            "chunks_found": len(chunks),
            "chunks_indexed": indexed_count,
            "duration_seconds": duration,
        }

    def get_stats(self) -> Dict[str, Any]:
        """Get stats for this source from the store."""
        return self.store.get_stats(source=self.source_name)

    def clear(self) -> int:
        """Clear all indexed data for this source."""
        return self.store.clear(source=self.source_name)

    # Utility methods for subclasses

    @staticmethod
    def days_ago(days: int) -> datetime:
        """Get datetime for N days ago."""
        return datetime.now() - timedelta(days=days)

    @staticmethod
    def safe_get(data: Dict, *keys, default=None):
        """
        Safely get nested dictionary value.

        Example:
            safe_get(data, "user", "profile", "name", default="Unknown")
        """
        result = data
        for key in keys:
            if isinstance(result, dict):
                result = result.get(key)
            else:
                return default
            if result is None:
                return default
        return result

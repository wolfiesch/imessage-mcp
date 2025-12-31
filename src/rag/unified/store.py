"""
Unified vector store supporting multiple collections.

Extends the base MessageVectorStore to support:
- Multiple source-specific collections
- Cross-collection search
- Source filtering
- Unified result format

CS Concept: This uses the **Facade Pattern** - providing a simplified
interface to a complex subsystem (multiple ChromaDB collections).
"""

import logging
from pathlib import Path
from typing import List, Dict, Optional, Any
from datetime import datetime

from .chunk import UnifiedChunk, SOURCE_TYPES

logger = logging.getLogger(__name__)

# Lazy imports
_chromadb = None


def _get_chromadb():
    """Lazy import ChromaDB."""
    global _chromadb
    if _chromadb is None:
        try:
            import chromadb
            _chromadb = chromadb
        except ImportError:
            raise ImportError("ChromaDB not installed. Run: pip install chromadb")
    return _chromadb


class UnifiedVectorStore:
    """
    Multi-collection vector store for unified RAG.

    Manages separate ChromaDB collections per source type while
    providing unified search across all or selected sources.

    Args:
        persist_directory: Where to store ChromaDB data
        use_local_embeddings: Use local embeddings instead of OpenAI

    Example:
        store = UnifiedVectorStore()
        store.add_chunks([chunk1, chunk2])  # Auto-routes to correct collection
        results = store.search("dinner plans", sources=["imessage", "gmail"])
    """

    # Collection name prefix for unified sources
    COLLECTION_PREFIX = "unified_"

    def __init__(
        self,
        persist_directory: Optional[str] = None,
        use_local_embeddings: bool = False,
    ):
        # Default persist directory
        if persist_directory is None:
            project_root = Path(__file__).parent.parent.parent.parent
            persist_directory = str(project_root / "data" / "chroma")

        self.persist_directory = persist_directory
        self.use_local_embeddings = use_local_embeddings

        # Ensure directory exists
        Path(persist_directory).mkdir(parents=True, exist_ok=True)

        # Initialize ChromaDB client
        chromadb = _get_chromadb()
        self.client = chromadb.PersistentClient(path=persist_directory)

        # Initialize embedding provider (shared across collections)
        from ..store import EmbeddingProvider
        self.embedder = EmbeddingProvider(use_local=use_local_embeddings)

        # Collection cache
        self._collections: Dict[str, Any] = {}

        logger.info(f"Initialized UnifiedVectorStore at {persist_directory}")

    def _get_collection(self, source: str):
        """
        Get or create collection for a source type.

        Collections are cached to avoid repeated lookups.
        """
        if source not in SOURCE_TYPES:
            raise ValueError(f"Invalid source: {source}")

        if source not in self._collections:
            collection_name = f"{self.COLLECTION_PREFIX}{source}_chunks"
            self._collections[source] = self.client.get_or_create_collection(
                name=collection_name,
                metadata={"hnsw:space": "cosine"},
            )
            logger.debug(f"Loaded collection: {collection_name}")

        return self._collections[source]

    def add_chunks(
        self,
        chunks: List[UnifiedChunk],
        batch_size: int = 100,
    ) -> Dict[str, int]:
        """
        Add chunks to appropriate collections.

        Chunks are automatically routed to their source-specific collection.
        Existing chunks (by chunk_id) are skipped.

        Args:
            chunks: List of UnifiedChunk objects
            batch_size: Batch size for embedding API calls

        Returns:
            Dict mapping source -> count of chunks added
        """
        if not chunks:
            return {}

        # Group chunks by source
        by_source: Dict[str, List[UnifiedChunk]] = {}
        for chunk in chunks:
            if chunk.source not in by_source:
                by_source[chunk.source] = []
            by_source[chunk.source].append(chunk)

        results = {}

        for source, source_chunks in by_source.items():
            collection = self._get_collection(source)

            # Filter out existing chunks
            existing_ids = set(collection.get()["ids"])
            new_chunks = [c for c in source_chunks if c.chunk_id not in existing_ids]

            if not new_chunks:
                results[source] = 0
                continue

            logger.info(
                f"Indexing {len(new_chunks)} new {source} chunks "
                f"(skipping {len(source_chunks) - len(new_chunks)} existing)"
            )

            # Process in batches
            added = 0
            for i in range(0, len(new_chunks), batch_size):
                batch = new_chunks[i:i + batch_size]

                ids = [c.chunk_id for c in batch]
                texts = [c.to_embedding_text() for c in batch]
                metadatas = [c.to_dict() for c in batch]

                # Generate embeddings
                embeddings = self.embedder.embed(texts)

                # Add to collection
                collection.add(
                    ids=ids,
                    embeddings=embeddings,
                    documents=texts,
                    metadatas=metadatas,
                )

                added += len(batch)

            results[source] = added
            logger.info(f"Indexed {added} {source} chunks")

        return results

    def search(
        self,
        query: str,
        sources: Optional[List[str]] = None,
        limit: int = 10,
        min_date: Optional[datetime] = None,
        max_date: Optional[datetime] = None,
        participants: Optional[List[str]] = None,
        tags: Optional[List[str]] = None,
    ) -> List[Dict]:
        """
        Semantic search across one or more sources.

        Args:
            query: Natural language search query
            sources: List of sources to search (None = all)
            limit: Max results per source
            min_date: Filter chunks after this date
            max_date: Filter chunks before this date
            participants: Filter by participant names
            tags: Filter by tags

        Returns:
            List of result dicts sorted by relevance score
        """
        # Default to all sources
        if sources is None:
            sources = list(SOURCE_TYPES)

        # Validate sources
        invalid_sources = set(sources) - SOURCE_TYPES
        if invalid_sources:
            raise ValueError(f"Invalid sources: {invalid_sources}")

        # Generate query embedding once
        query_embedding = self.embedder.embed_single(query)

        all_results = []

        for source in sources:
            collection = self._get_collection(source)

            if collection.count() == 0:
                continue

            # Query this collection
            results = collection.query(
                query_embeddings=[query_embedding],
                n_results=limit,
                include=["documents", "metadatas", "distances"],
            )

            # Process results
            for i in range(len(results["ids"][0])):
                chunk_id = results["ids"][0][i]
                document = results["documents"][0][i]
                metadata = results["metadatas"][0][i]
                distance = results["distances"][0][i]

                # Convert distance to similarity
                score = 1 - distance

                # Apply date filters
                if min_date or max_date:
                    chunk_time = metadata.get("timestamp")
                    if chunk_time:
                        try:
                            chunk_dt = datetime.fromisoformat(chunk_time)
                            if min_date and chunk_dt < min_date:
                                continue
                            if max_date and chunk_dt > max_date:
                                continue
                        except (ValueError, TypeError):
                            pass

                # Apply participant filter
                if participants:
                    chunk_participants = metadata.get("participants", "").split(",")
                    if not any(p in chunk_participants for p in participants):
                        continue

                # Apply tags filter
                if tags:
                    chunk_tags = metadata.get("tags", "").split(",")
                    if not any(t in chunk_tags for t in tags):
                        continue

                all_results.append({
                    "chunk_id": chunk_id,
                    "source": source,
                    "text": metadata.get("text", document),
                    "title": metadata.get("title"),
                    "context_id": metadata.get("context_id"),
                    "context_type": metadata.get("context_type"),
                    "timestamp": metadata.get("timestamp"),
                    "participants": metadata.get("participants", "").split(",") if metadata.get("participants") else [],
                    "tags": metadata.get("tags", "").split(",") if metadata.get("tags") else [],
                    "score": score,
                    "metadata": metadata,
                })

        # Sort by score (highest first)
        all_results.sort(key=lambda x: x["score"], reverse=True)

        # Return top results across all sources
        return all_results[:limit]

    def get_stats(self, source: Optional[str] = None) -> Dict[str, Any]:
        """
        Get statistics about indexed content.

        Args:
            source: Specific source to get stats for (None = all)

        Returns:
            Dict with counts, date ranges, etc.
        """
        sources_to_check = [source] if source else list(SOURCE_TYPES)
        sources_to_check = [s for s in sources_to_check if s in SOURCE_TYPES]

        total_chunks = 0
        by_source = {}
        oldest = None
        newest = None
        all_participants = set()
        all_tags = set()

        for src in sources_to_check:
            collection = self._get_collection(src)
            count = collection.count()

            if count == 0:
                by_source[src] = {"chunk_count": 0}
                continue

            # Get all metadata for stats
            all_data = collection.get(include=["metadatas"])

            source_oldest = None
            source_newest = None

            for meta in all_data["metadatas"]:
                if not meta:
                    continue

                # Track timestamps
                ts = meta.get("timestamp")
                if ts:
                    if source_oldest is None or ts < source_oldest:
                        source_oldest = ts
                    if source_newest is None or ts > source_newest:
                        source_newest = ts

                # Collect participants
                if meta.get("participants"):
                    for p in meta["participants"].split(","):
                        if p:
                            all_participants.add(p)

                # Collect tags
                if meta.get("tags"):
                    for t in meta["tags"].split(","):
                        if t:
                            all_tags.add(t)

            by_source[src] = {
                "chunk_count": count,
                "oldest": source_oldest,
                "newest": source_newest,
            }

            total_chunks += count

            if source_oldest:
                if oldest is None or source_oldest < oldest:
                    oldest = source_oldest
            if source_newest:
                if newest is None or source_newest > newest:
                    newest = source_newest

        return {
            "total_chunks": total_chunks,
            "by_source": by_source,
            "oldest_chunk": oldest,
            "newest_chunk": newest,
            "unique_participants": len(all_participants),
            "unique_tags": len(all_tags),
            "persist_directory": self.persist_directory,
        }

    def clear(self, source: Optional[str] = None) -> int:
        """
        Clear indexed data.

        Args:
            source: Specific source to clear (None = all sources)

        Returns:
            Total chunks deleted
        """
        sources_to_clear = [source] if source else list(SOURCE_TYPES)
        total_deleted = 0

        for src in sources_to_clear:
            if src not in SOURCE_TYPES:
                continue

            collection_name = f"{self.COLLECTION_PREFIX}{src}_chunks"
            try:
                collection = self.client.get_collection(collection_name)
                count = collection.count()
                if count > 0:
                    self.client.delete_collection(collection_name)
                    total_deleted += count
                    logger.info(f"Cleared {count} chunks from {src}")

                # Remove from cache
                if src in self._collections:
                    del self._collections[src]
            except Exception:
                # Collection doesn't exist
                pass

        return total_deleted

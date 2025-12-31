"""
Vector store for iMessage RAG using ChromaDB.

Stores conversation chunk embeddings and provides semantic search.
Supports both OpenAI embeddings (high quality) and local sentence-transformers
(privacy-preserving).

CS Concept: Vector stores use "approximate nearest neighbor" (ANN) algorithms
like HNSW (Hierarchical Navigable Small World) to find similar vectors in
O(log n) time instead of O(n) brute force. This is how they scale to millions
of documents.

Architecture Pattern: This is the **Repository Pattern** - we abstract away
the storage mechanism (ChromaDB) behind a clean interface. If we wanted to
switch to FAISS or Pinecone later, only this module changes.
"""

import logging
import os
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from datetime import datetime

logger = logging.getLogger(__name__)

# Lazy imports to avoid startup cost if not using RAG
_chromadb = None
_openai = None
_sentence_transformers = None


def _get_chromadb():
    """Lazy import ChromaDB."""
    global _chromadb
    if _chromadb is None:
        try:
            import chromadb
            _chromadb = chromadb
        except ImportError:
            raise ImportError(
                "ChromaDB not installed. Run: pip install chromadb"
            )
    return _chromadb


def _get_openai():
    """Lazy import OpenAI."""
    global _openai
    if _openai is None:
        try:
            from openai import OpenAI
            _openai = OpenAI
        except ImportError:
            raise ImportError(
                "OpenAI not installed. Run: pip install openai"
            )
    return _openai


class EmbeddingProvider:
    """
    Generates embeddings for text using OpenAI or local models.

    Supports two backends:
    - OpenAI (default): High quality, requires API key, sends data to cloud
    - Local: Uses sentence-transformers, runs locally, slower but private

    Args:
        use_local: If True, use local sentence-transformers instead of OpenAI
        model: Model name (OpenAI: "text-embedding-3-small", local: "all-MiniLM-L6-v2")
    """

    def __init__(
        self,
        use_local: bool = False,
        model: Optional[str] = None,
    ):
        self.use_local = use_local

        if use_local:
            self.model = model or "all-MiniLM-L6-v2"
            self._init_local_model()
        else:
            self.model = model or "text-embedding-3-small"
            self._init_openai()

    def _init_openai(self):
        """Initialize OpenAI client."""
        OpenAI = _get_openai()
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise ValueError(
                "OPENAI_API_KEY environment variable not set. "
                "Either set it or use use_local=True for local embeddings."
            )
        self.client = OpenAI(api_key=api_key)
        self.dimensions = 1536  # text-embedding-3-small dimensions
        logger.info(f"Initialized OpenAI embeddings with model: {self.model}")

    def _init_local_model(self):
        """Initialize local sentence-transformers model."""
        global _sentence_transformers
        try:
            from sentence_transformers import SentenceTransformer
            _sentence_transformers = SentenceTransformer
        except ImportError:
            raise ImportError(
                "sentence-transformers not installed. "
                "Run: pip install sentence-transformers"
            )

        self.client = _sentence_transformers(self.model)
        # Get dimensions from model
        self.dimensions = self.client.get_sentence_embedding_dimension()
        logger.info(f"Initialized local embeddings with model: {self.model} (dim={self.dimensions})")

    def embed(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for a list of texts.

        Args:
            texts: List of text strings to embed

        Returns:
            List of embedding vectors (each is a list of floats)

        Complexity: O(n) where n = total tokens across all texts.
        API calls are batched for efficiency.
        """
        if not texts:
            return []

        if self.use_local:
            return self._embed_local(texts)
        else:
            return self._embed_openai(texts)

    def _embed_openai(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings using OpenAI API."""
        try:
            response = self.client.embeddings.create(
                model=self.model,
                input=texts,
            )
            return [item.embedding for item in response.data]
        except Exception as e:
            logger.error(f"OpenAI embedding error: {e}")
            raise

    def _embed_local(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings using local model."""
        try:
            embeddings = self.client.encode(texts, convert_to_numpy=True)
            return embeddings.tolist()
        except Exception as e:
            logger.error(f"Local embedding error: {e}")
            raise

    def embed_single(self, text: str) -> List[float]:
        """
        Generate embedding for a single text.

        Args:
            text: Text string to embed

        Returns:
            Embedding vector as list of floats
        """
        return self.embed([text])[0]


class MessageVectorStore:
    """
    Vector store for iMessage conversation chunks.

    Wraps ChromaDB with iMessage-specific functionality:
    - Stores conversation chunks with metadata
    - Semantic search by natural language query
    - Incremental updates (only index new chunks)
    - Metadata filtering (by contact, date range, etc.)

    Args:
        persist_directory: Where to store ChromaDB data (default: data/chroma)
        collection_name: Name of the ChromaDB collection (default: imessage_chunks)
        use_local_embeddings: Use local embeddings instead of OpenAI

    Example:
        store = MessageVectorStore()
        store.add_chunks(chunks)
        results = store.search("dinner plans", limit=5)
    """

    def __init__(
        self,
        persist_directory: Optional[str] = None,
        collection_name: str = "imessage_chunks",
        use_local_embeddings: bool = False,
    ):
        # Default persist directory relative to Texting project
        if persist_directory is None:
            project_root = Path(__file__).parent.parent.parent
            persist_directory = str(project_root / "data" / "chroma")

        self.persist_directory = persist_directory
        self.collection_name = collection_name

        # Ensure directory exists
        Path(persist_directory).mkdir(parents=True, exist_ok=True)

        # Initialize ChromaDB
        chromadb = _get_chromadb()
        self.client = chromadb.PersistentClient(path=persist_directory)

        # Initialize embedding provider
        self.embedder = EmbeddingProvider(use_local=use_local_embeddings)

        # Get or create collection
        # We use our own embedding function via EmbeddingProvider
        self.collection = self.client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},  # Use cosine similarity
        )

        logger.info(
            f"Initialized MessageVectorStore: {persist_directory}/{collection_name} "
            f"({self.collection.count()} chunks indexed)"
        )

    def add_chunks(
        self,
        chunks: List["ConversationChunk"],  # Forward reference
        batch_size: int = 100,
    ) -> int:
        """
        Add conversation chunks to the vector store.

        Skips chunks that are already indexed (by chunk_id).
        Batches embedding requests for efficiency.

        Args:
            chunks: List of ConversationChunk objects to index
            batch_size: Number of chunks to embed in one API call

        Returns:
            Number of new chunks added

        Complexity: O(n) for n chunks, with n/batch_size API calls.
        """
        if not chunks:
            return 0

        # Filter out already-indexed chunks
        existing_ids = set(self.collection.get()["ids"])
        new_chunks = [c for c in chunks if c.chunk_id not in existing_ids]

        if not new_chunks:
            logger.info("All chunks already indexed, nothing to add")
            return 0

        logger.info(f"Indexing {len(new_chunks)} new chunks (skipping {len(chunks) - len(new_chunks)} existing)")

        # Process in batches
        added = 0
        for i in range(0, len(new_chunks), batch_size):
            batch = new_chunks[i:i + batch_size]

            # Prepare data for ChromaDB
            ids = [c.chunk_id for c in batch]
            texts = [c.to_embedding_text() for c in batch]
            metadatas = [c.to_dict() for c in batch]

            # Generate embeddings
            embeddings = self.embedder.embed(texts)

            # Add to collection
            self.collection.add(
                ids=ids,
                embeddings=embeddings,
                documents=texts,
                metadatas=metadatas,
            )

            added += len(batch)
            logger.debug(f"Added batch of {len(batch)} chunks ({added}/{len(new_chunks)})")

        logger.info(f"Successfully indexed {added} chunks")
        return added

    def search(
        self,
        query: str,
        limit: int = 5,
        contact_filter: Optional[str] = None,
        min_date: Optional[datetime] = None,
        max_date: Optional[datetime] = None,
    ) -> List[Dict]:
        """
        Semantic search for conversation chunks.

        Args:
            query: Natural language search query
            limit: Maximum number of results to return
            contact_filter: Only return chunks from this contact
            min_date: Only return chunks after this date
            max_date: Only return chunks before this date

        Returns:
            List of result dicts with keys:
            - chunk_id: Unique identifier
            - text: Conversation text
            - contact: Who the conversation was with
            - start_time: When conversation started
            - score: Similarity score (0-1, higher = more similar)
            - metadata: Full chunk metadata

        Example:
            results = store.search("dinner plans", contact_filter="John")
            for r in results:
                print(f"{r['contact']}: {r['text'][:100]}... (score: {r['score']:.2f})")
        """
        if self.collection.count() == 0:
            logger.warning("Vector store is empty, no results to return")
            return []

        # Build where clause for metadata filtering
        where = None
        if contact_filter:
            where = {"contact": {"$eq": contact_filter}}

        # Generate query embedding
        query_embedding = self.embedder.embed_single(query)

        # Search
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=limit,
            where=where,
            include=["documents", "metadatas", "distances"],
        )

        # Format results
        formatted = []
        for i in range(len(results["ids"][0])):
            chunk_id = results["ids"][0][i]
            document = results["documents"][0][i]
            metadata = results["metadatas"][0][i]
            distance = results["distances"][0][i]

            # Convert distance to similarity score (cosine distance -> similarity)
            # ChromaDB returns L2 distance for cosine space, need to convert
            score = 1 - distance  # For cosine, distance is 1 - similarity

            # Apply date filters (post-query since ChromaDB doesn't support date comparisons)
            if min_date or max_date:
                chunk_start = metadata.get("start_time")
                if chunk_start:
                    try:
                        chunk_dt = datetime.fromisoformat(chunk_start.replace("Z", ""))
                        if min_date and chunk_dt < min_date:
                            continue
                        if max_date and chunk_dt > max_date:
                            continue
                    except (ValueError, TypeError):
                        pass

            formatted.append({
                "chunk_id": chunk_id,
                "text": metadata.get("text", document),
                "contact": metadata.get("contact", "Unknown"),
                "start_time": metadata.get("start_time"),
                "end_time": metadata.get("end_time"),
                "message_count": metadata.get("message_count", 0),
                "is_group": metadata.get("is_group", False),
                "group_name": metadata.get("group_name"),
                "score": score,
                "metadata": metadata,
            })

        return formatted

    def get_indexed_contacts(self) -> List[str]:
        """
        Get list of all contacts that have been indexed.

        Returns:
            Sorted list of unique contact identifiers
        """
        if self.collection.count() == 0:
            return []

        all_data = self.collection.get(include=["metadatas"])
        contacts = set()
        for meta in all_data["metadatas"]:
            if meta and meta.get("contact"):
                contacts.add(meta["contact"])

        return sorted(contacts)

    def get_stats(self) -> Dict:
        """
        Get statistics about the vector store.

        Returns:
            Dict with chunk_count, contact_count, date_range, etc.
        """
        count = self.collection.count()

        if count == 0:
            return {
                "chunk_count": 0,
                "contact_count": 0,
                "oldest_chunk": None,
                "newest_chunk": None,
            }

        all_data = self.collection.get(include=["metadatas"])

        contacts = set()
        oldest = None
        newest = None

        for meta in all_data["metadatas"]:
            if meta:
                if meta.get("contact"):
                    contacts.add(meta["contact"])

                start_time = meta.get("start_time")
                if start_time:
                    if oldest is None or start_time < oldest:
                        oldest = start_time
                    if newest is None or start_time > newest:
                        newest = start_time

        return {
            "chunk_count": count,
            "contact_count": len(contacts),
            "contacts": sorted(contacts),
            "oldest_chunk": oldest,
            "newest_chunk": newest,
            "persist_directory": self.persist_directory,
        }

    def clear(self) -> int:
        """
        Clear all data from the vector store.

        ⚠️ DANGER ZONE: This deletes all indexed chunks!

        Returns:
            Number of chunks deleted
        """
        count = self.collection.count()
        if count > 0:
            # ChromaDB doesn't have a clear method, so we delete the collection
            # and recreate it
            self.client.delete_collection(self.collection_name)
            self.collection = self.client.get_or_create_collection(
                name=self.collection_name,
                metadata={"hnsw:space": "cosine"},
            )
            logger.info(f"Cleared {count} chunks from vector store")

        return count

    def delete_by_contact(self, contact: str) -> int:
        """
        Delete all chunks for a specific contact.

        Args:
            contact: Contact identifier to delete

        Returns:
            Number of chunks deleted
        """
        # Get IDs of chunks to delete
        results = self.collection.get(
            where={"contact": {"$eq": contact}},
            include=[],
        )

        ids_to_delete = results["ids"]
        if not ids_to_delete:
            return 0

        self.collection.delete(ids=ids_to_delete)
        logger.info(f"Deleted {len(ids_to_delete)} chunks for contact: {contact}")

        return len(ids_to_delete)

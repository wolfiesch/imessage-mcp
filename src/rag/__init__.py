"""
iMessage RAG (Retrieval-Augmented Generation) module.

Provides semantic search over iMessage conversations using embeddings
and vector similarity search.

Components:
- chunker: Groups messages into embeddable conversation windows
- embedder: Generates embeddings (OpenAI or local)
- store: ChromaDB vector store for similarity search
- retriever: Combines search with context synthesis
"""

from .chunker import ConversationChunker, ConversationChunk
from .store import MessageVectorStore

__all__ = [
    "ConversationChunker",
    "ConversationChunk",
    "MessageVectorStore",
]

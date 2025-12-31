"""
Unified RAG system for multi-source knowledge indexing.

Supports indexing and semantic search across:
- iMessage conversations (existing)
- Gmail emails
- Markdown notes/documents
- Calendar events
- Slack messages
- SuperWhisper voice transcriptions
"""

from .chunk import UnifiedChunk, SOURCE_TYPES, CONTEXT_TYPES
from .store import UnifiedVectorStore
from .base_indexer import BaseSourceIndexer
from .superwhisper_indexer import SuperWhisperIndexer
from .notes_indexer import NotesIndexer
from .gmail_indexer import GmailIndexer
from .slack_indexer import SlackIndexer
from .calendar_indexer import CalendarIndexer
from .retriever import UnifiedRetriever

__all__ = [
    # Core
    "UnifiedChunk",
    "UnifiedVectorStore",
    "BaseSourceIndexer",
    "UnifiedRetriever",
    # Constants
    "SOURCE_TYPES",
    "CONTEXT_TYPES",
    # Indexers
    "SuperWhisperIndexer",
    "NotesIndexer",
    "GmailIndexer",
    "SlackIndexer",
    "CalendarIndexer",
]

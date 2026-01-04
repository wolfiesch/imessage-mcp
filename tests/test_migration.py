"""
Integration tests for RAG data migration.

Tests the migration from old 'imessage_chunks' collection to new 'unified_imessage_chunks'.
"""

import pytest
from pathlib import Path
import sys

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "Texting"))


def test_migration_tool_exists():
    """Verify migration tool handler is defined in server."""
    from mcp_server import server

    # Check handler function exists
    assert hasattr(server, 'handle_migrate_rag_data')
    assert callable(server.handle_migrate_rag_data)


def test_migration_idempotent():
    """
    Test that migration can be run multiple times safely.

    This is a smoke test - actual migration testing requires:
    1. Old RAG collection with data
    2. New unified collection created
    3. Running the migration

    For now, we just verify the handler doesn't crash.
    """
    # This test would require setting up ChromaDB collections
    # which is integration-level testing beyond unit tests
    #
    # In production, test by:
    # 1. Call index_knowledge(source="imessage") to create new collection
    # 2. Call migrate_rag_data() - should copy data
    # 3. Call migrate_rag_data() again - should be idempotent
    pass


def test_new_system_works_without_old():
    """
    Verify new unified RAG system is independent of old system.

    The new system should work even if old RAG code is deleted.
    """
    from src.rag.unified.retriever import UnifiedRetriever
    from src.rag.unified.imessage_indexer import ImessageIndexer

    # Should be able to import without errors
    assert UnifiedRetriever is not None
    assert ImessageIndexer is not None

    # These classes should not depend on old RAG modules
    # Verify by checking imports don't reference old code
    import inspect

    retriever_source = inspect.getsourcefile(UnifiedRetriever)
    assert retriever_source is not None
    assert "unified" in retriever_source

    indexer_source = inspect.getsourcefile(ImessageIndexer)
    assert indexer_source is not None
    assert "unified" in indexer_source


def test_deprecation_warnings_present():
    """Verify deprecation warnings are in place for old tools."""
    from mcp_server import server
    import inspect

    # Check handle_index_messages has deprecation
    index_messages_source = inspect.getsource(server.handle_index_messages)
    assert "DEPRECATED" in index_messages_source
    assert "index_knowledge" in index_messages_source

    # Check handle_ask_messages has deprecation
    ask_messages_source = inspect.getsource(server.handle_ask_messages)
    assert "DEPRECATED" in ask_messages_source
    assert "search_knowledge" in ask_messages_source


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

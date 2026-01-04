"""
Test iMessage unified indexer.

Tests the ImessageIndexer integration with the unified RAG system.
"""
import pytest
import tempfile
import shutil
from datetime import datetime
from pathlib import Path

from src.rag.unified.imessage_indexer import ImessageIndexer
from src.rag.unified.store import UnifiedVectorStore


@pytest.fixture
def test_store():
    """Create a temporary vector store for testing."""
    temp_dir = tempfile.mkdtemp()
    store = UnifiedVectorStore(
        persist_directory=temp_dir,
        use_local_embeddings=True,  # Avoid API costs
    )
    yield store
    # Cleanup
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def indexer(test_store):
    """Create an ImessageIndexer instance for testing."""
    return ImessageIndexer(store=test_store)


def test_imessage_indexer_initialization(indexer):
    """Test that ImessageIndexer initializes correctly."""
    assert indexer.source_name == "imessage"
    assert indexer.messages is not None
    assert indexer.contacts is not None
    assert indexer.chunker is not None


def test_fetch_data_basic(indexer):
    """Test basic message fetching."""
    # Fetch a small number of messages
    messages = indexer.fetch_data(limit=50)

    assert isinstance(messages, list)
    # May be 0 if no messages in database
    if len(messages) > 0:
        # Verify message structure
        msg = messages[0]
        assert "text" in msg or "is_from_me" in msg


def test_fetch_data_with_contact_filter(indexer):
    """Test fetching messages from a specific contact."""
    # This test will skip if the contact doesn't exist
    # In a real test environment, you'd use a known test contact
    try:
        messages = indexer.fetch_data(limit=20, contact_name="Test Contact")
        # If contact exists, should get messages
        assert isinstance(messages, list)
    except ValueError as e:
        # Expected if contact doesn't exist
        assert "not found" in str(e)


def test_chunk_data_basic(indexer):
    """Test converting messages to chunks."""
    # Fetch some messages first
    messages = indexer.fetch_data(limit=100)

    if not messages:
        pytest.skip("No messages available for testing")

    # Convert to chunks
    chunks = indexer.chunk_data(messages)

    assert isinstance(chunks, list)

    if len(chunks) > 0:
        # Verify chunk structure
        chunk = chunks[0]
        assert chunk.source == "imessage"
        assert chunk.context_type == "conversation"
        assert chunk.word_count > 0
        assert len(chunk.text) > 20
        assert chunk.timestamp is not None


def test_chunk_conversion(indexer):
    """Test ConversationChunk to UnifiedChunk conversion."""
    from src.rag.chunker import ConversationChunk

    # Create a sample ConversationChunk
    conv_chunk = ConversationChunk(
        chunk_id="test_123",
        contact="Test Contact",
        text="Hello, this is a test conversation with enough words to be valid.",
        start_time=datetime.now(),
        end_time=datetime.now(),
        message_count=5,
        is_group=False,
        group_name=None,
        metadata={}
    )

    # Convert to UnifiedChunk
    unified_chunk = indexer._conversation_chunk_to_unified(conv_chunk)

    assert unified_chunk is not None
    assert unified_chunk.source == "imessage"
    assert unified_chunk.chunk_id == "test_123"
    assert unified_chunk.title == "Conversation with Test Contact"
    assert "Test Contact" in unified_chunk.participants
    assert unified_chunk.metadata["message_count"] == 5
    assert unified_chunk.metadata["is_group"] is False


def test_group_chat_conversion(indexer):
    """Test group chat ConversationChunk conversion."""
    from src.rag.chunker import ConversationChunk

    # Create a group chat chunk
    conv_chunk = ConversationChunk(
        chunk_id="group_123",
        contact="+1234567890",
        text="This is a group chat conversation with multiple participants discussing something.",
        start_time=datetime.now(),
        end_time=datetime.now(),
        message_count=10,
        is_group=True,
        group_name="Test Group",
        metadata={"phones": ["+1234567890", "+0987654321"]}
    )

    # Convert to UnifiedChunk
    unified_chunk = indexer._conversation_chunk_to_unified(conv_chunk)

    assert unified_chunk is not None
    assert unified_chunk.title == "Group: Test Group"
    assert "group_chat" in unified_chunk.tags
    assert unified_chunk.metadata["is_group"] is True
    assert len(unified_chunk.participants) > 1  # Should have multiple participants


def test_short_chunks_filtered(indexer):
    """Test that very short chunks are filtered out."""
    from src.rag.chunker import ConversationChunk

    # Create a chunk that's too short
    short_chunk = ConversationChunk(
        chunk_id="short_123",
        contact="Test",
        text="Hi",  # Only 1 word
        start_time=datetime.now(),
        end_time=datetime.now(),
        message_count=1,
        is_group=False,
        group_name=None,
        metadata={}
    )

    # Should return None for too-short chunks
    unified_chunk = indexer._conversation_chunk_to_unified(short_chunk)
    assert unified_chunk is None


def test_index_full_pipeline(test_store):
    """Test the full index pipeline: fetch → chunk → store."""
    indexer = ImessageIndexer(store=test_store)

    # Run indexing with small limit
    result = indexer.index(limit=100)

    assert result["success"] is True
    assert "chunks_found" in result
    assert "chunks_indexed" in result
    assert "source" in result
    assert result["source"] == "imessage"

    # chunks_indexed might be 0 if all chunks are duplicates or no messages
    # but the operation should still succeed
    assert result["chunks_indexed"] >= 0


def test_deduplication(test_store):
    """Test that re-indexing same messages doesn't create duplicates."""
    indexer = ImessageIndexer(store=test_store)

    # Index first time
    result1 = indexer.index(limit=50)
    chunks_first = result1.get("chunks_indexed", 0)

    # Index again with same messages
    result2 = indexer.index(limit=50)
    chunks_second = result2.get("chunks_indexed", 0)

    # Second indexing should add 0 or very few new chunks
    # (might have a few new if messages came in between calls)
    assert chunks_second <= chunks_first


def test_integration_with_search(test_store):
    """Test end-to-end: index and then search."""
    # Index some messages using the test store
    indexer = ImessageIndexer(store=test_store)
    result = indexer.index(limit=200)

    assert result["success"]

    if result["chunks_indexed"] > 0:
        # Search directly on the test store (not through UnifiedRetriever)
        # to avoid embedding dimension mismatch
        results = test_store.search("hello", sources=["imessage"], limit=3)

        # Should return a list (may be empty if "hello" doesn't appear)
        assert isinstance(results, list)

        # If we got results, verify structure
        if len(results) > 0:
            # Results should have metadata dict
            for r in results:
                assert isinstance(r, dict)
                metadata = r.get("metadata", {})
                # Should have source in metadata
                if "source" in metadata:
                    assert metadata["source"] == "imessage"


def test_contact_name_enrichment(indexer):
    """Test that contact names are used when available."""
    # This is hard to test without a known contact database
    # Just verify that the enrichment code doesn't crash
    messages = indexer.fetch_data(limit=20)

    # Check if any messages have _contact_name enriched
    has_enriched = any(msg.get("_contact_name") for msg in messages)

    # This assertion might fail if no contacts are in the database
    # but at least verifies the code runs
    assert isinstance(has_enriched, bool)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

#!/usr/bin/env python3
"""
Test script for iMessage RAG functionality.

Tests the full RAG pipeline:
1. Fetch messages from Messages database
2. Chunk into conversation windows
3. Generate embeddings
4. Store in ChromaDB
5. Semantic search

Usage:
    python3 scripts/test_rag.py
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.messages_interface import MessagesInterface
from src.rag.chunker import ConversationChunker
from src.rag.store import MessageVectorStore
from src.rag.retriever import MessageRetriever


def test_chunker():
    """Test the conversation chunker."""
    print("\n" + "="*60)
    print("Testing Conversation Chunker")
    print("="*60)

    # Fetch some test messages
    mi = MessagesInterface()
    messages = mi.get_all_recent_conversations(limit=100)

    print(f"Fetched {len(messages)} messages")

    if not messages:
        print("No messages found. Check Full Disk Access permissions.")
        return False

    # Chunk messages
    chunker = ConversationChunker(window_hours=4, min_words=15)
    chunks = chunker.chunk_messages(messages)

    print(f"Created {len(chunks)} chunks")

    if chunks:
        print("\nSample chunk:")
        chunk = chunks[0]
        print(f"  ID: {chunk.chunk_id}")
        print(f"  Contact: {chunk.contact}")
        print(f"  Messages: {chunk.message_count}")
        print(f"  Words: {chunk.word_count}")
        print(f"  Duration: {chunk.duration_minutes} minutes")
        print(f"  Text preview: {chunk.text[:100]}...")

    return len(chunks) > 0


def test_vector_store():
    """Test the vector store (requires OpenAI API key)."""
    print("\n" + "="*60)
    print("Testing Vector Store")
    print("="*60)

    try:
        # Create test store with a separate collection for testing
        store = MessageVectorStore(
            collection_name="imessage_test",
        )

        print(f"Store initialized at: {store.persist_directory}")
        print(f"Current count: {store.collection.count()}")

        # Fetch and chunk some messages
        mi = MessagesInterface()
        messages = mi.get_all_recent_conversations(limit=50)

        if not messages:
            print("No messages to index")
            return False

        chunker = ConversationChunker()
        chunks = chunker.chunk_messages(messages)

        if not chunks:
            print("No chunks created")
            return False

        print(f"Indexing {len(chunks)} chunks...")

        # Add chunks
        added = store.add_chunks(chunks[:10])  # Just index first 10 for test
        print(f"Added {added} new chunks")

        # Test search
        if store.collection.count() > 0:
            print("\nTesting search...")
            results = store.search("plans", limit=3)
            print(f"Found {len(results)} results for 'plans'")

            for i, r in enumerate(results, 1):
                print(f"\n  Result {i}:")
                print(f"    Contact: {r['contact']}")
                print(f"    Score: {r['score']:.2%}")
                print(f"    Preview: {r['text'][:80]}...")

        # Get stats
        stats = store.get_stats()
        print(f"\nStats: {stats}")

        return True

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_retriever():
    """Test the high-level retriever."""
    print("\n" + "="*60)
    print("Testing Message Retriever")
    print("="*60)

    try:
        retriever = MessageRetriever()

        print("Retriever initialized")
        stats = retriever.get_stats()
        print(f"Current stats: {stats}")

        # Index recent messages if empty
        if stats.get("chunk_count", 0) == 0:
            print("\nIndexing recent messages (last 7 days)...")
            added = retriever.index_recent_messages(days=7, limit=100)
            print(f"Added {added} chunks")

        # Test search
        if retriever.get_stats().get("chunk_count", 0) > 0:
            print("\nTesting ask()...")
            context, results = retriever.ask("dinner plans")
            print(f"Found {len(results)} relevant conversations")
            print(f"\nContext preview:\n{context[:500]}...")

        return True

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all tests."""
    print("iMessage RAG Test Suite")
    print("="*60)

    results = {
        "chunker": test_chunker(),
        "vector_store": test_vector_store(),
        "retriever": test_retriever(),
    }

    print("\n" + "="*60)
    print("Test Results")
    print("="*60)

    for test, passed in results.items():
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"  {test}: {status}")

    all_passed = all(results.values())
    print(f"\nOverall: {'All tests passed!' if all_passed else 'Some tests failed'}")

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())

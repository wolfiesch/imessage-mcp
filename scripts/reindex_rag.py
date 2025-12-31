#!/usr/bin/env python3
"""
Reindex RAG with proper contact name resolution.

Clears existing index and reindexes messages with
contact names from macOS Contacts.

Usage:
    python3 scripts/reindex_rag.py           # Last 90 days (default)
    python3 scripts/reindex_rag.py --all     # Complete 4-year history
    python3 scripts/reindex_rag.py --days 365  # Custom time range
"""

import sys
import argparse
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.rag.retriever import MessageRetriever


def main():
    """Clear and reindex RAG."""
    parser = argparse.ArgumentParser(description="Reindex iMessage RAG")
    parser.add_argument("--all", action="store_true", help="Index complete message history (~4 years)")
    parser.add_argument("--days", type=int, default=90, help="Days of history to index (default: 90)")
    parser.add_argument("--no-clear", action="store_true", help="Don't clear existing index (incremental)")
    args = parser.parse_args()

    print("=" * 60)
    print("iMessage RAG Reindex")
    print("=" * 60)

    # Initialize retriever
    print("\nInitializing retriever...")
    retriever = MessageRetriever(
        persist_directory=str(Path(__file__).parent.parent / "data" / "chroma"),
        contacts_config=str(Path(__file__).parent.parent / "config" / "contacts.json"),
    )

    # Show current stats
    stats = retriever.get_stats()
    print(f"\nCurrent index: {stats.get('chunk_count', 0)} chunks")

    # Clear existing (unless --no-clear)
    if not args.no_clear:
        print("\nClearing existing index...")
        deleted = retriever.clear_index()
        print(f"Deleted {deleted} chunks")

    # Index based on mode
    if args.all:
        print("\nIndexing COMPLETE message history (this may take a few minutes)...")
        added = retriever.index_all_history()
    else:
        print(f"\nIndexing messages (last {args.days} days)...")
        # Calculate appropriate limit based on days
        # ~500 messages per day is a reasonable estimate for active users
        limit = max(10000, args.days * 200)
        added = retriever.index_recent_messages(days=args.days, limit=limit)

    print(f"Added {added} new chunks")

    # Show new stats
    stats = retriever.get_stats()
    print(f"\nNew index stats:")
    print(f"  Chunks: {stats.get('chunk_count', 0)}")
    print(f"  Contacts: {len(stats.get('contacts', []))}")
    print(f"  Date range: {stats.get('oldest_date', 'N/A')} to {stats.get('newest_date', 'N/A')}")

    if stats.get("contacts"):
        print(f"\nIndexed contacts:")
        for contact in sorted(stats.get("contacts", []))[:15]:
            print(f"    {contact}")
        if len(stats.get("contacts", [])) > 15:
            print(f"    ... and {len(stats.get('contacts', [])) - 15} more")

    print("\n✓ Reindex complete!")
    return 0


if __name__ == "__main__":
    sys.exit(main())

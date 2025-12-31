"""
High-level retriever for iMessage RAG.

Provides a simple interface for:
1. Indexing messages from the Messages database
2. Semantic search across conversations
3. Synthesizing answers with context

This is the main entry point for using iMessage RAG.

Example:
    retriever = MessageRetriever()

    # Index recent messages
    retriever.index_recent_messages(days=30)

    # Search
    results = retriever.search("dinner plans")

    # Ask a question (returns synthesized answer)
    answer = retriever.ask("What restaurant did Sarah recommend?")
"""

import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional, Tuple
import sys

# Add parent directories for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.rag.chunker import ConversationChunker, ConversationChunk
from src.rag.store import MessageVectorStore
from src.messages_interface import MessagesInterface
from src.contacts_manager import ContactsManager

logger = logging.getLogger(__name__)


class MessageRetriever:
    """
    High-level interface for iMessage RAG.

    Combines message fetching, chunking, embedding, and search
    into a simple API.

    Args:
        use_local_embeddings: Use local embeddings (slower, private)
        persist_directory: Where to store vector database
        contacts_config: Path to contacts.json

    Example:
        retriever = MessageRetriever()
        retriever.index_contact("John Doe", days=90)
        results = retriever.search("that thing John mentioned")
    """

    def __init__(
        self,
        use_local_embeddings: bool = False,
        persist_directory: Optional[str] = None,
        contacts_config: Optional[str] = None,
    ):
        # Initialize components
        self.messages = MessagesInterface()

        # Resolve contacts config path
        if contacts_config is None:
            project_root = Path(__file__).parent.parent.parent
            contacts_config = str(project_root / "config" / "contacts.json")

        self.contacts = ContactsManager(contacts_config)

        # Initialize vector store
        self.store = MessageVectorStore(
            persist_directory=persist_directory,
            use_local_embeddings=use_local_embeddings,
        )

        # Initialize chunker
        self.chunker = ConversationChunker()

        logger.info(f"MessageRetriever initialized. {self.store.collection.count()} chunks indexed.")

    def index_contact(
        self,
        contact_name: str,
        days: int = 90,
        limit: int = 1000,
    ) -> int:
        """
        Index messages with a specific contact.

        Args:
            contact_name: Contact name to look up
            days: How many days of history to index
            limit: Maximum messages to fetch

        Returns:
            Number of new chunks indexed

        Raises:
            ValueError: If contact not found
        """
        # Look up contact
        contact = self.contacts.get_contact_by_name(contact_name)
        if not contact:
            available = [c.name for c in self.contacts.list_contacts()]
            raise ValueError(
                f"Contact '{contact_name}' not found. "
                f"Available: {', '.join(available[:5])}{'...' if len(available) > 5 else ''}"
            )

        logger.info(f"Indexing messages with {contact.name} ({contact.phone}), last {days} days")

        # Fetch messages
        messages = self.messages.get_recent_messages(contact.phone, limit=limit)

        if not messages:
            logger.warning(f"No messages found for {contact.name}")
            return 0

        # Filter to date range
        cutoff = datetime.now() - timedelta(days=days)
        filtered = []
        for msg in messages:
            if msg.get("date"):
                try:
                    msg_date = datetime.fromisoformat(msg["date"].replace("Z", "").split("+")[0])
                    if msg_date >= cutoff:
                        filtered.append(msg)
                except (ValueError, TypeError):
                    filtered.append(msg)  # Include if can't parse date
            else:
                filtered.append(msg)

        logger.info(f"Found {len(filtered)} messages in last {days} days (of {len(messages)} total)")

        # Chunk messages
        chunks = self.chunker.chunk_messages(filtered, contact_name=contact.name)

        if not chunks:
            logger.warning("No chunks created (messages may be too short)")
            return 0

        # Index chunks
        added = self.store.add_chunks(chunks)

        return added

    def index_all_contacts(
        self,
        days: int = 90,
        limit_per_contact: int = 500,
    ) -> Dict[str, int]:
        """
        Index messages with all configured contacts.

        Args:
            days: How many days of history to index
            limit_per_contact: Maximum messages per contact

        Returns:
            Dict mapping contact name to number of chunks indexed
        """
        results = {}
        contacts = self.contacts.list_contacts()

        for contact in contacts:
            try:
                added = self.index_contact(
                    contact.name,
                    days=days,
                    limit=limit_per_contact,
                )
                results[contact.name] = added
            except Exception as e:
                logger.error(f"Error indexing {contact.name}: {e}")
                results[contact.name] = -1

        total = sum(v for v in results.values() if v > 0)
        logger.info(f"Indexed {total} chunks across {len(contacts)} contacts")

        return results

    def index_recent_messages(
        self,
        days: int = 30,
        limit: int = 10000,
    ) -> int:
        """
        Index recent messages from all conversations.

        This indexes conversations with people who may not be in your
        contacts list.

        Args:
            days: How many days of history to index (default 30)
            limit: Maximum messages to fetch (default 10000 = ~3 months)
                   Use higher limits for more history:
                   - 5000 = ~1 month
                   - 10000 = ~3 months
                   - 50000 = ~1 year
                   - 150000 = all time (~4 years)

        Returns:
            Number of new chunks indexed
        """
        logger.info(f"Indexing recent messages from all conversations, last {days} days (limit={limit})")

        # Fetch all recent messages
        messages = self.messages.get_all_recent_conversations(limit=limit)

        if not messages:
            logger.warning("No messages found")
            return 0

        # Filter to date range
        cutoff = datetime.now() - timedelta(days=days)
        filtered = []
        for msg in messages:
            if msg.get("date"):
                try:
                    msg_date = datetime.fromisoformat(msg["date"].replace("Z", "").split("+")[0])
                    if msg_date >= cutoff:
                        filtered.append(msg)
                except (ValueError, TypeError):
                    filtered.append(msg)

        logger.info(f"Found {len(filtered)} messages in last {days} days")

        # Enrich with contact names where available
        for msg in filtered:
            phone = msg.get("phone")
            if phone:
                contact = self.contacts.get_contact_by_phone(phone)
                if contact:
                    msg["_contact_name"] = contact.name

        # Chunk messages
        chunks = self.chunker.chunk_messages(filtered)

        if not chunks:
            logger.warning("No chunks created")
            return 0

        # Index chunks
        added = self.store.add_chunks(chunks)

        return added

    def search(
        self,
        query: str,
        limit: int = 5,
        contact: Optional[str] = None,
        days: Optional[int] = None,
    ) -> List[Dict]:
        """
        Semantic search across indexed messages.

        Args:
            query: Natural language search query
            limit: Maximum number of results
            contact: Filter to specific contact
            days: Only search messages from last N days

        Returns:
            List of search results with text, contact, date, and score

        Example:
            results = retriever.search("dinner plans", contact="Sarah")
            for r in results:
                print(f"{r['contact']}: {r['text'][:100]}...")
        """
        # Calculate date filter
        min_date = None
        if days:
            min_date = datetime.now() - timedelta(days=days)

        # Resolve contact name to canonical form if provided
        contact_filter = None
        if contact:
            resolved = self.contacts.get_contact_by_name(contact)
            if resolved:
                contact_filter = resolved.name
            else:
                # Use as-is (might be phone number)
                contact_filter = contact

        return self.store.search(
            query=query,
            limit=limit,
            contact_filter=contact_filter,
            min_date=min_date,
        )

    def ask(
        self,
        question: str,
        limit: int = 5,
        contact: Optional[str] = None,
    ) -> Tuple[str, List[Dict]]:
        """
        Ask a question and get a synthesized answer.

        Retrieves relevant conversation chunks and formats them
        for context. Returns both the formatted context and the
        raw search results.

        Note: This method prepares context for Claude but doesn't
        call Claude directly - that happens at the MCP layer.

        Args:
            question: Natural language question
            limit: Number of context chunks to retrieve
            contact: Filter to specific contact

        Returns:
            Tuple of (formatted_context, search_results)

        Example:
            context, results = retriever.ask("What restaurant did Sarah recommend?")
            # context is ready to inject into a Claude prompt
        """
        results = self.search(question, limit=limit, contact=contact)

        if not results:
            return (
                "No relevant messages found in the indexed conversations.",
                [],
            )

        # Format context for Claude
        context_parts = []
        for i, r in enumerate(results, 1):
            date_str = r.get("start_time", "Unknown date")
            if date_str and len(date_str) > 10:
                date_str = date_str[:10]  # Just the date part

            contact_name = r.get("contact", "Unknown")
            text = r.get("text", "")
            score = r.get("score", 0)

            context_parts.append(
                f"**Conversation {i}** (with {contact_name}, {date_str}, relevance: {score:.0%}):\n"
                f"{text}\n"
            )

        formatted_context = (
            f"Found {len(results)} relevant conversation(s) for: \"{question}\"\n\n"
            + "\n---\n\n".join(context_parts)
        )

        return formatted_context, results

    def get_stats(self) -> Dict:
        """
        Get statistics about the indexed messages.

        Returns:
            Dict with chunk_count, contact_count, date_range, etc.
        """
        return self.store.get_stats()

    def get_indexed_contacts(self) -> List[str]:
        """
        Get list of contacts that have been indexed.

        Returns:
            Sorted list of contact names
        """
        return self.store.get_indexed_contacts()

    def index_all_history(
        self,
        batch_size: int = 20000,
        max_messages: int = 150000,
    ) -> int:
        """
        Index complete message history (all time).

        Fetches all available messages and indexes them in batches.
        This can take several minutes for large histories.

        Args:
            batch_size: Messages to process per batch (for memory efficiency)
            max_messages: Maximum total messages to fetch

        Returns:
            Total number of new chunks indexed
        """
        logger.info(f"Indexing complete message history (max {max_messages} messages)")

        # Fetch all messages
        messages = self.messages.get_all_recent_conversations(limit=max_messages)

        if not messages:
            logger.warning("No messages found")
            return 0

        logger.info(f"Found {len(messages)} total messages")

        # Enrich with contact names
        for msg in messages:
            phone = msg.get("phone")
            if phone:
                contact = self.contacts.get_contact_by_phone(phone)
                if contact:
                    msg["_contact_name"] = contact.name

        # Chunk and index all messages
        chunks = self.chunker.chunk_messages(messages)

        if not chunks:
            logger.warning("No chunks created")
            return 0

        # Index chunks
        added = self.store.add_chunks(chunks)
        logger.info(f"Indexed {added} new chunks from {len(messages)} messages")

        return added

    def clear_index(self) -> int:
        """
        Clear all indexed data.

        ⚠️ DANGER ZONE: Deletes all embeddings!

        Returns:
            Number of chunks deleted
        """
        return self.store.clear()

    def reindex_contact(
        self,
        contact_name: str,
        days: int = 90,
        limit: int = 1000,
    ) -> int:
        """
        Re-index messages for a contact (clears existing and re-indexes).

        Args:
            contact_name: Contact to re-index
            days: Days of history
            limit: Max messages

        Returns:
            Number of chunks indexed
        """
        # Look up contact for canonical name
        contact = self.contacts.get_contact_by_name(contact_name)
        if not contact:
            raise ValueError(f"Contact '{contact_name}' not found")

        # Delete existing chunks for this contact
        deleted = self.store.delete_by_contact(contact.name)
        logger.info(f"Deleted {deleted} existing chunks for {contact.name}")

        # Re-index
        return self.index_contact(contact_name, days=days, limit=limit)


def quick_index(days: int = 30, use_local: bool = False) -> MessageRetriever:
    """
    Convenience function to quickly set up and index messages.

    Args:
        days: Days of history to index
        use_local: Use local embeddings (no API key needed)

    Returns:
        Configured MessageRetriever with indexed data

    Example:
        retriever = quick_index(days=60)
        results = retriever.search("dinner plans")
    """
    retriever = MessageRetriever(use_local_embeddings=use_local)
    retriever.index_recent_messages(days=days)
    return retriever

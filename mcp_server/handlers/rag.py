# ============================================================================
# CHANGELOG (recent first, max 5 entries)
# 01/03/2026 - Extracted from server.py during MCP refactoring (Claude)
# ============================================================================
"""
RAG (Retrieval Augmented Generation) Handlers

Handles tools for semantic search across indexed content:
- index_messages: (DEPRECATED) Index iMessages for semantic search
- ask_messages: (DEPRECATED) Semantic search across indexed conversations
- rag_stats: Get statistics about the indexed message database
- index_knowledge: Index content from multiple sources
- search_knowledge: Semantic search across all indexed sources
- knowledge_stats: Get statistics about the knowledge base
- migrate_rag_data: Migrate old RAG collection to unified collection
"""

import logging
from mcp import types

from utils.validation import validate_non_empty_string, validate_positive_int
from utils.responses import text_response
from utils.errors import handle_rag_error

logger = logging.getLogger(__name__)


async def handle_index_messages(
    arguments: dict,
    get_retriever,
    get_unified_retriever,
    messages,
    contacts
) -> list[types.TextContent]:
    """
    ⚠️ DEPRECATED: Handle index_messages tool call.

    Use index_knowledge(source="imessage") instead.

    Args:
        arguments: {"contact_name": Optional[str], "days": Optional[int], "all_history": Optional[bool]}
        get_retriever: Function to get the MessageRetriever
        get_unified_retriever: Function to get the UnifiedRetriever
        messages: MessagesInterface instance
        contacts: ContactsManager instance

    Returns:
        Status message about indexing
    """
    logger.warning(
        "⚠️ DEPRECATED: index_messages is deprecated. "
        "Use index_knowledge(source='imessage') instead for better performance and features."
    )

    contact_name = arguments.get("contact_name")
    all_history = arguments.get("all_history", False)

    # Validate days (allow up to 1460 = 4 years)
    days_raw = arguments.get("days", 30)
    days, error = validate_positive_int(days_raw, "days", min_val=1, max_val=1460)
    if error:
        return text_response(f"Validation error: {error}")
    if days is None:
        days = 30

    try:
        retriever = get_retriever()

        # Full history indexing
        if all_history and not contact_name:
            chunks_added = retriever.index_all_history()
            stats = retriever.get_stats()
            contacts_indexed = stats.get("contacts", [])

            return text_response(
                f"✓ Indexed COMPLETE message history\n\n"
                f"• {chunks_added} new conversation chunks created\n"
                f"• Total chunks: {stats.get('chunk_count', 0)}\n"
                f"• Contacts indexed: {len(contacts_indexed)}\n"
                f"• Date range: ALL TIME\n\n"
                f"You can now use ask_messages to search these conversations."
            )

        if contact_name:
            # Index specific contact
            contact = contacts.get_contact_by_name(contact_name)
            if not contact:
                return text_response(
                    f"Contact '{contact_name}' not found. "
                    f"Available contacts: {', '.join(c.name for c in contacts.list_contacts()[:5])}..."
                )

            chunks_added = retriever.index_contact(contact.name, days=days)

            return text_response(
                f"✓ Indexed messages with {contact.name}\n\n"
                f"• {chunks_added} conversation chunks created\n"
                f"• Date range: last {days} days\n\n"
                f"You can now use ask_messages to search these conversations."
            )
        else:
            # Index all recent messages
            chunks_added = retriever.index_recent_messages(days=days)
            stats = retriever.get_stats()
            contacts_indexed = stats.get("contacts", [])

            return text_response(
                f"✓ Indexed recent messages\n\n"
                f"• {chunks_added} new conversation chunks created\n"
                f"• Total chunks: {stats.get('chunk_count', 0)}\n"
                f"• Contacts indexed: {len(contacts_indexed)}\n"
                f"• Date range: last {days} days\n\n"
                f"You can now use ask_messages to search these conversations."
            )

    except Exception as e:
        return handle_rag_error(e, "indexing messages")


async def handle_ask_messages(
    arguments: dict,
    get_retriever,
    get_unified_retriever,
    messages,
    contacts
) -> list[types.TextContent]:
    """
    ⚠️ DEPRECATED: Handle ask_messages tool call.

    Use search_knowledge(sources=["imessage"]) instead.

    Args:
        arguments: {"question": str, "contact_name": Optional[str], "limit": Optional[int]}
        get_retriever: Function to get the MessageRetriever
        get_unified_retriever: Function to get the UnifiedRetriever
        messages: MessagesInterface instance
        contacts: ContactsManager instance

    Returns:
        Relevant conversation context
    """
    logger.warning(
        "⚠️ DEPRECATED: ask_messages is deprecated. "
        "Use search_knowledge(sources=['imessage']) instead for multi-source search capabilities."
    )

    # Validate question
    question, error = validate_non_empty_string(arguments.get("question"), "question")
    if error:
        return text_response(f"Validation error: {error}")

    contact_name = arguments.get("contact_name")

    # Validate limit
    limit_raw = arguments.get("limit", 5)
    limit, error = validate_positive_int(limit_raw, "limit", min_val=1, max_val=20)
    if error:
        return text_response(f"Validation error: {error}")
    if limit is None:
        limit = 5

    try:
        retriever = get_retriever()

        # Check if index is empty
        stats = retriever.get_stats()
        if stats.get("chunk_count", 0) == 0:
            return text_response(
                "No messages have been indexed yet.\n\n"
                "Run index_messages first to create the search index:\n"
                "• index_messages with days=30 (indexes all recent messages)\n"
                "• index_messages with contact_name=\"John\" (indexes specific contact)"
            )

        # Perform semantic search
        context, results = retriever.ask(
            question=question,
            limit=limit,
            contact=contact_name,
        )

        if not results:
            filter_text = f" with {contact_name}" if contact_name else ""
            return text_response(
                f"No relevant conversations found{filter_text} for: \"{question}\""
            )

        return text_response(context)

    except Exception as e:
        return handle_rag_error(e, "searching messages")


async def handle_rag_stats(
    arguments: dict,
    get_retriever,
    get_unified_retriever,
    messages,
    contacts
) -> list[types.TextContent]:
    """
    Handle rag_stats tool call.

    Args:
        arguments: {} (no arguments needed)
        get_retriever: Function to get the MessageRetriever
        get_unified_retriever: Function to get the UnifiedRetriever
        messages: MessagesInterface instance
        contacts: ContactsManager instance

    Returns:
        Statistics about the indexed message database
    """
    try:
        retriever = get_retriever()
        stats = retriever.get_stats()

        if stats.get("chunk_count", 0) == 0:
            return text_response(
                "RAG index is empty.\n\n"
                "Run index_messages first to build the search index."
            )

        # Format stats
        lines = [
            "RAG Index Statistics",
            "=" * 40,
            f"Total chunks: {stats.get('chunk_count', 0)}",
        ]

        contacts_list = stats.get("contacts", [])
        if contacts_list:
            lines.append(f"Contacts indexed: {len(contacts_list)}")
            lines.append(f"  {', '.join(contacts_list[:10])}")
            if len(contacts_list) > 10:
                lines.append(f"  ...and {len(contacts_list) - 10} more")

        if stats.get("oldest_date"):
            lines.append(f"Date range: {stats['oldest_date'][:10]} to {stats.get('newest_date', 'now')[:10]}")

        return text_response("\n".join(lines))

    except Exception as e:
        return handle_rag_error(e, "getting stats")


async def handle_index_knowledge(
    arguments: dict,
    get_retriever,
    get_unified_retriever,
    messages,
    contacts
) -> list[types.TextContent]:
    """
    Handle index_knowledge tool call for unified multi-source RAG.

    Args:
        arguments: {"source": str, "days": Optional[int], "limit": Optional[int], ...}
        get_retriever: Function to get the MessageRetriever
        get_unified_retriever: Function to get the UnifiedRetriever
        messages: MessagesInterface instance
        contacts: ContactsManager instance

    Returns:
        Status message about indexing
    """
    source = arguments.get("source", "").lower()
    days = arguments.get("days", 30)
    limit = arguments.get("limit")

    if not source:
        return text_response(
            "Error: 'source' is required. Options: imessage, superwhisper, notes, local, gmail, slack, calendar"
        )

    # Validate days
    if days:
        validated, error = validate_positive_int(days, "days", min_val=1, max_val=1460)
        if error:
            return text_response(f"Error: {error}")
        days = validated

    # Validate limit
    if limit:
        validated, error = validate_positive_int(limit, "limit", min_val=1, max_val=10000)
        if error:
            return text_response(f"Error: {error}")
        limit = validated

    try:
        retriever = get_unified_retriever()

        if source == "superwhisper":
            result = retriever.index_superwhisper(days=days, limit=limit)
            return text_response(
                f"SuperWhisper indexing complete!\n"
                f"- Transcriptions found: {result.get('chunks_found', 0)}\n"
                f"- Transcriptions indexed: {result.get('chunks_indexed', 0)}\n"
                f"- Duration: {result.get('duration_seconds', 0):.1f}s\n\n"
                f"Use search_knowledge to search your voice transcriptions."
            )

        elif source == "notes":
            result = retriever.index_notes(days=days, limit=limit)
            return text_response(
                f"Notes indexing complete!\n"
                f"- Document sections found: {result.get('chunks_found', 0)}\n"
                f"- Sections indexed: {result.get('chunks_indexed', 0)}\n"
                f"- Duration: {result.get('duration_seconds', 0):.1f}s\n\n"
                f"Use search_knowledge to search your notes."
            )

        elif source == "local":
            result = retriever.index_local_sources(days=days)
            by_source = result.get("by_source", {})
            return text_response(
                f"Local sources indexing complete!\n\n"
                f"SuperWhisper:\n"
                f"  - Found: {by_source.get('superwhisper', {}).get('chunks_found', 0)}\n"
                f"  - Indexed: {by_source.get('superwhisper', {}).get('chunks_indexed', 0)}\n\n"
                f"Notes:\n"
                f"  - Found: {by_source.get('notes', {}).get('chunks_found', 0)}\n"
                f"  - Indexed: {by_source.get('notes', {}).get('chunks_indexed', 0)}\n\n"
                f"Total chunks indexed: {result.get('total_chunks_indexed', 0)}\n\n"
                f"Use search_knowledge to search across all sources."
            )

        elif source == "imessage":
            # iMessage indexing with incremental mode
            from src.rag.unified.imessage_indexer import ImessageIndexer

            contact_name = arguments.get("contact_name")
            incremental = arguments.get("incremental", True)

            indexer = ImessageIndexer(
                messages_interface=messages,
                contacts_manager=contacts,
                store=retriever.store,
            )

            result = indexer.index(
                days=days,
                limit=limit,
                contact_name=contact_name,
                incremental=incremental,
            )

            if result["success"]:
                return text_response(
                    f"✓ Indexed iMessages\n\n"
                    f"• Source: iMessage\n"
                    f"• Chunks indexed: {result['chunks_indexed']}\n"
                    f"• Messages processed: ~{result.get('chunks_found', 0) * 3}\n"
                    f"• Date range: {'last ' + str(days) + ' days' if days else 'all available'}\n"
                    f"• Contact filter: {contact_name or 'none (all conversations)'}\n\n"
                    f"You can now search these conversations with search_knowledge."
                )
            else:
                return text_response(
                    f"Error indexing iMessages: {result.get('error', 'Unknown error')}"
                )

        elif source in ("gmail", "slack", "calendar"):
            return text_response(
                f"Indexing {source} requires pre-fetched data.\n\n"
                f"For {source}, first fetch data using the appropriate MCP tools, "
                f"then pass the data to the indexer programmatically.\n\n"
                f"For local sources (superwhisper, notes), use index_knowledge directly."
            )

        else:
            return text_response(
                f"Unknown source: {source}. Options: imessage, superwhisper, notes, local, gmail, slack, calendar"
            )

    except Exception as e:
        return handle_rag_error(e, f"indexing {source}")


async def handle_search_knowledge(
    arguments: dict,
    get_retriever,
    get_unified_retriever,
    messages,
    contacts
) -> list[types.TextContent]:
    """
    Handle search_knowledge tool call for unified semantic search.

    Args:
        arguments: {"query": str, "sources": Optional[list], "days": Optional[int], "limit": Optional[int]}
        get_retriever: Function to get the MessageRetriever
        get_unified_retriever: Function to get the UnifiedRetriever
        messages: MessagesInterface instance
        contacts: ContactsManager instance

    Returns:
        Relevant content from indexed sources
    """
    query = arguments.get("query", "").strip()
    sources = arguments.get("sources")
    days = arguments.get("days")
    limit = arguments.get("limit", 10)

    if not query:
        return text_response("Error: 'query' is required.")

    # Validate limit
    if limit:
        validated, error = validate_positive_int(limit, "limit", min_val=1, max_val=50)
        if error:
            return text_response(f"Error: {error}")
        limit = validated

    # Validate days
    if days:
        validated, error = validate_positive_int(days, "days", min_val=1, max_val=1460)
        if error:
            return text_response(f"Error: {error}")
        days = validated

    try:
        retriever = get_unified_retriever()

        # Check if anything is indexed
        stats = retriever.get_stats()
        if stats.get("total_chunks", 0) == 0:
            return text_response(
                "No content has been indexed yet.\n\n"
                "Run index_knowledge first to build the search index:\n"
                "• index_knowledge with source='superwhisper' (voice transcriptions)\n"
                "• index_knowledge with source='notes' (markdown documents)\n"
                "• index_knowledge with source='local' (both)"
            )

        # Perform search
        context = retriever.ask(
            question=query,
            sources=sources,
            limit=limit,
            days=days,
        )

        return text_response(context)

    except Exception as e:
        return handle_rag_error(e, "searching knowledge")


async def handle_knowledge_stats(
    arguments: dict,
    get_retriever,
    get_unified_retriever,
    messages,
    contacts
) -> list[types.TextContent]:
    """
    Handle knowledge_stats tool call.

    Args:
        arguments: {"source": Optional[str]}
        get_retriever: Function to get the MessageRetriever
        get_unified_retriever: Function to get the UnifiedRetriever
        messages: MessagesInterface instance
        contacts: ContactsManager instance

    Returns:
        Statistics about the knowledge base
    """
    source = arguments.get("source")

    try:
        retriever = get_unified_retriever()
        stats = retriever.get_stats(source=source)

        if stats.get("total_chunks", 0) == 0:
            return text_response(
                "Knowledge base is empty.\n\n"
                "Run index_knowledge to start building the search index:\n"
                "• index_knowledge with source='superwhisper'\n"
                "• index_knowledge with source='notes'\n"
                "• index_knowledge with source='local' (both)"
            )

        # Format stats
        lines = [
            "Knowledge Base Statistics",
            "=" * 40,
            f"Total chunks indexed: {stats.get('total_chunks', 0)}",
            f"Unique participants: {stats.get('unique_participants', 0)}",
            f"Unique tags: {stats.get('unique_tags', 0)}",
            "",
            "By Source:",
        ]

        by_source = stats.get("by_source", {})
        for src, info in sorted(by_source.items()):
            count = info.get("chunk_count", 0)
            if count > 0:
                oldest = info.get("oldest", "N/A")
                newest = info.get("newest", "N/A")
                lines.append(f"  {src}: {count} chunks")
                lines.append(f"    Range: {oldest[:10] if oldest else 'N/A'} to {newest[:10] if newest else 'N/A'}")

        if stats.get("oldest_chunk") and stats.get("newest_chunk"):
            lines.append("")
            lines.append(f"Overall date range: {stats['oldest_chunk'][:10]} to {stats['newest_chunk'][:10]}")

        return text_response("\n".join(lines))

    except Exception as e:
        return handle_rag_error(e, "getting knowledge stats")


async def handle_migrate_rag_data(
    arguments: dict,
    get_retriever,
    get_unified_retriever,
    messages,
    contacts
) -> list[types.TextContent]:
    """
    Handle migrate_rag_data tool call.

    One-time migration from old RAG collection to unified collection.

    Args:
        arguments: {} (no arguments needed)
        get_retriever: Function to get the MessageRetriever
        get_unified_retriever: Function to get the UnifiedRetriever
        messages: MessagesInterface instance
        contacts: ContactsManager instance

    Returns:
        Migration status
    """
    try:
        retriever = get_unified_retriever()

        # Check if migration is needed
        stats_before = retriever.get_stats()
        if stats_before.get("by_source", {}).get("imessage", {}).get("chunk_count", 0) > 0:
            return text_response(
                "Migration already completed or not needed.\n\n"
                f"Current iMessage chunks: {stats_before['by_source']['imessage']['chunk_count']}"
            )

        # Perform migration
        result = retriever.migrate_from_legacy()

        if result.get("success"):
            return text_response(
                f"✓ Migration completed!\n\n"
                f"• Chunks migrated: {result.get('chunks_migrated', 0)}\n"
                f"• Source: old 'imessage_chunks' collection\n"
                f"• Destination: unified collection\n\n"
                f"You can now use search_knowledge to search all your data."
            )
        else:
            return text_response(
                f"Migration failed: {result.get('error', 'Unknown error')}"
            )

    except Exception as e:
        return handle_rag_error(e, "migrating RAG data")

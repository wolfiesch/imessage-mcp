"""
Benchmarks for indexing operations.
Measures throughput, latency, and memory usage.
"""
import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "Texting"))

from src.messages_interface import MessagesInterface
from src.rag.chunker import ConversationChunker
from src.rag.unified.imessage_indexer import ImessageIndexer
from benchmarks.benchmark_runner import benchmark, save_benchmark_results, print_results
from benchmarks.config import BENCHMARK_SIZES, MESSAGES_DB_PATH, RESULTS_DIR


def bench_message_fetch(size: str):
    """Benchmark raw message fetching from database."""
    limit = BENCHMARK_SIZES[size]

    with benchmark(f"message_fetch_{size}") as result:
        interface = MessagesInterface()
        messages = interface.get_all_recent_conversations(limit=limit)

        result.add_metric("messages_fetched", len(messages))
        if result.elapsed_seconds > 0:
            result.add_metric("messages_per_second", len(messages) / result.elapsed_seconds)

    return result


def bench_chunking(size: str):
    """Benchmark conversation chunking."""
    limit = BENCHMARK_SIZES[size]

    # Pre-fetch messages (not part of benchmark)
    interface = MessagesInterface()
    messages = interface.get_all_recent_conversations(limit=limit)

    with benchmark(f"chunking_{size}") as result:
        chunker = ConversationChunker(window_hours=4.0, min_words=20, max_words=500)
        chunks = chunker.chunk_messages(messages)

        result.add_metric("messages_chunked", len(messages))
        result.add_metric("chunks_created", len(chunks))
        if result.elapsed_seconds > 0:
            result.add_metric("chunks_per_second", len(chunks) / result.elapsed_seconds)

    return result


def bench_full_index(size: str):
    """Benchmark end-to-end indexing (fetch + chunk)."""
    limit = BENCHMARK_SIZES[size]

    with benchmark(f"full_index_{size}") as result:
        indexer = ImessageIndexer()

        # Fetch and chunk
        messages = indexer.fetch_data(limit=limit)
        chunks = indexer.chunk_data(messages)

        result.add_metric("messages_fetched", len(messages))
        result.add_metric("chunks_indexed", len(chunks))
        if result.elapsed_seconds > 0:
            result.add_metric("chunks_per_second", len(chunks) / result.elapsed_seconds)

    return result


def run_all_indexing_benchmarks():
    """Run complete indexing benchmark suite."""
    results = []

    print("Running indexing benchmarks...")
    print(f"Using Messages database: {MESSAGES_DB_PATH}")

    if not MESSAGES_DB_PATH.exists():
        print(f"ERROR: Messages database not found at {MESSAGES_DB_PATH}")
        print("Skipping indexing benchmarks")
        return results

    # Run each benchmark size
    for size in ["tiny", "small", "medium"]:  # Skip "large" by default (too slow)
        print(f"\nBenchmarking {size} dataset ({BENCHMARK_SIZES[size]} messages)...")

        try:
            results.append(bench_message_fetch(size))
        except Exception as e:
            print(f"  Error in message_fetch_{size}: {e}")

        try:
            results.append(bench_chunking(size))
        except Exception as e:
            print(f"  Error in chunking_{size}: {e}")

        try:
            results.append(bench_full_index(size))
        except Exception as e:
            print(f"  Error in full_index_{size}: {e}")

    # Save and display
    output_file = RESULTS_DIR / "indexing_benchmarks.json"
    save_benchmark_results(results, output_file)
    print_results(results)

    return results


if __name__ == "__main__":
    run_all_indexing_benchmarks()

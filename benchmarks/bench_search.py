"""
Benchmarks for search and retrieval operations.
Measures query latency and breakdown (embedding vs retrieval).
"""
import sys
from pathlib import Path
import time

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "Texting"))

from src.rag.unified.retriever import UnifiedRetriever
from src.rag.store import EmbeddingProvider
from benchmarks.benchmark_runner import benchmark, save_benchmark_results, print_results
from benchmarks.config import RESULTS_DIR

# Standard test queries of varying complexity
TEST_QUERIES = {
    "simple": "restaurant",
    "medium": "what restaurant did we talk about?",
    "complex": "what restaurants did Sarah recommend last month and what did she say about them?",
    "semantic": "places to eat that have good ambiance for a date"
}


def bench_embedding_generation(query_type: str):
    """Benchmark embedding generation alone."""
    query = TEST_QUERIES[query_type]

    with benchmark(f"embedding_{query_type}") as result:
        try:
            provider = EmbeddingProvider(use_local=False)

            # Time embedding generation
            start = time.perf_counter()
            embedding = provider.get_embedding(query)
            elapsed = time.perf_counter() - start

            result.add_metric("query_length", len(query))
            result.add_metric("embedding_dim", len(embedding))
            result.add_metric("embedding_time_ms", elapsed * 1000)
        except Exception as e:
            print(f"  Error generating embedding: {e}")
            result.add_metric("error", str(e))

    return result


def bench_retrieval(query_type: str, k: int = 5):
    """Benchmark semantic search retrieval."""
    query = TEST_QUERIES[query_type]

    with benchmark(f"retrieval_{query_type}_k{k}") as result:
        try:
            retriever = UnifiedRetriever()

            # Time full retrieval
            start = time.perf_counter()
            results = retriever.search(query, limit=k)
            elapsed = time.perf_counter() - start

            result.add_metric("results_returned", len(results))
            result.add_metric("latency_ms", elapsed * 1000)
            result.add_metric("k", k)
        except Exception as e:
            print(f"  Error during retrieval: {e}")
            result.add_metric("error", str(e))
            result.add_metric("results_returned", 0)

    return result


def bench_ask_query(query_type: str):
    """Benchmark end-to-end ask() with formatted results."""
    query = TEST_QUERIES[query_type]

    with benchmark(f"ask_{query_type}") as result:
        try:
            retriever = UnifiedRetriever()

            # Time full ask pipeline
            start = time.perf_counter()
            answer = retriever.ask(query, limit=5)
            elapsed = time.perf_counter() - start

            result.add_metric("answer_length", len(answer) if answer else 0)
            result.add_metric("total_latency_ms", elapsed * 1000)
        except Exception as e:
            print(f"  Error during ask: {e}")
            result.add_metric("error", str(e))
            result.add_metric("answer_length", 0)

    return result


def bench_search_k_scaling():
    """Benchmark how retrieval scales with k (number of results)."""
    results = []
    query = TEST_QUERIES["medium"]

    for k in [1, 5, 10, 20, 50]:
        with benchmark(f"k_scaling_k{k}") as result:
            try:
                retriever = UnifiedRetriever()
                retrieved = retriever.search(query, limit=k)

                result.add_metric("k", k)
                result.add_metric("results_returned", len(retrieved))
                result.add_metric("latency_ms", result.elapsed_seconds * 1000)
            except Exception as e:
                print(f"  Error in k={k} scaling: {e}")
                result.add_metric("error", str(e))

        results.append(result)

    return results


def run_all_search_benchmarks():
    """Run complete search benchmark suite."""
    results = []

    print("Running search benchmarks...")

    # Check if we can connect to vector store
    try:
        retriever = UnifiedRetriever()
        stats = retriever.get_stats()
        total_chunks = stats.get("total_chunks", 0)
        print(f"Vector store has {total_chunks} chunks indexed")

        if total_chunks == 0:
            print("WARNING: No content indexed. Search benchmarks may return empty results.")
            print("Consider running indexing benchmarks first or indexing some content.")
    except Exception as e:
        print(f"WARNING: Could not connect to vector store: {e}")
        print("Search benchmarks may fail")

    # Embedding generation
    print("\nBenchmarking embedding generation...")
    for query_type in ["simple", "medium", "complex"]:
        try:
            results.append(bench_embedding_generation(query_type))
        except Exception as e:
            print(f"  Skipped embedding_{query_type}: {e}")

    # Retrieval
    print("\nBenchmarking retrieval...")
    for query_type in ["simple", "medium", "complex"]:
        try:
            results.append(bench_retrieval(query_type, k=5))
        except Exception as e:
            print(f"  Skipped retrieval_{query_type}: {e}")

    # End-to-end ask
    print("\nBenchmarking end-to-end ask()...")
    for query_type in ["simple", "medium"]:
        try:
            results.append(bench_ask_query(query_type))
        except Exception as e:
            print(f"  Skipped ask_{query_type}: {e}")

    # K scaling
    print("\nBenchmarking k scaling...")
    try:
        results.extend(bench_search_k_scaling())
    except Exception as e:
        print(f"  Skipped k_scaling: {e}")

    # Save and display
    output_file = RESULTS_DIR / "search_benchmarks.json"
    save_benchmark_results(results, output_file)
    print_results(results)

    return results


if __name__ == "__main__":
    run_all_search_benchmarks()

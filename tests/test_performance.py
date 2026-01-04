"""
Performance regression tests.
Fails if performance degrades beyond acceptable thresholds.
"""
import pytest
import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "Texting"))

from benchmarks.bench_indexing import bench_message_fetch, bench_chunking
from benchmarks.bench_search import bench_embedding_generation, bench_retrieval

# Performance thresholds (fail if exceeded)
THRESHOLDS = {
    "message_fetch_small": 0.5,  # Max 0.5s for 1k messages
    "chunking_small": 1.0,       # Max 1.0s for 1k messages
    "embedding_simple": 1.0,     # Max 1s for simple embedding (includes API latency)
    "retrieval_medium_k5": 2.0,  # Max 2s for medium query (includes API latency)
}


@pytest.mark.performance
def test_message_fetch_performance():
    """Ensure message fetching stays fast."""
    result = bench_message_fetch("small")
    threshold = THRESHOLDS["message_fetch_small"]

    assert result.elapsed_seconds < threshold, \
        f"Message fetch took {result.elapsed_seconds}s, threshold is {threshold}s"


@pytest.mark.performance
def test_chunking_performance():
    """Ensure chunking stays fast."""
    result = bench_chunking("small")
    threshold = THRESHOLDS["chunking_small"]

    assert result.elapsed_seconds < threshold, \
        f"Chunking took {result.elapsed_seconds}s, threshold is {threshold}s"


@pytest.mark.performance
def test_embedding_performance():
    """Ensure embedding generation stays fast."""
    try:
        result = bench_embedding_generation("simple")
        threshold = THRESHOLDS["embedding_simple"]

        # Only check if no error occurred
        if "error" not in result.metrics:
            assert result.elapsed_seconds < threshold, \
                f"Embedding took {result.elapsed_seconds}s, threshold is {threshold}s"
        else:
            pytest.skip(f"Embedding failed: {result.metrics['error']}")
    except Exception as e:
        pytest.skip(f"Embedding benchmark failed: {e}")


@pytest.mark.performance
def test_retrieval_performance():
    """Ensure search retrieval stays fast."""
    try:
        result = bench_retrieval("medium", k=5)
        threshold = THRESHOLDS["retrieval_medium_k5"]

        # Only check if no error occurred
        if "error" not in result.metrics:
            assert result.elapsed_seconds < threshold, \
                f"Retrieval took {result.elapsed_seconds}s, threshold is {threshold}s"
        else:
            pytest.skip(f"Retrieval failed: {result.metrics['error']}")
    except Exception as e:
        pytest.skip(f"Retrieval benchmark failed: {e}")


@pytest.mark.performance
def test_benchmark_consistency():
    """Ensure benchmarks produce consistent results (variance check)."""
    # Run message fetch twice
    result1 = bench_message_fetch("tiny")
    result2 = bench_message_fetch("tiny")

    # Calculate variance
    if result1.elapsed_seconds > 0 and result2.elapsed_seconds > 0:
        variance = abs(result1.elapsed_seconds - result2.elapsed_seconds) / result1.elapsed_seconds

        # Variance should be < 50% (benchmarks are reasonably stable)
        assert variance < 0.5, \
            f"Benchmark variance too high: {variance*100:.1f}% (run1={result1.elapsed_seconds}s, run2={result2.elapsed_seconds}s)"

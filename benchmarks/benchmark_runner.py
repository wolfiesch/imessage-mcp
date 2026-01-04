"""
Core benchmark runner with timing and profiling utilities.
"""
import time
import psutil
import json
from typing import Dict, Any, List
from pathlib import Path
from datetime import datetime
from contextlib import contextmanager


class BenchmarkResult:
    """Container for benchmark results."""

    def __init__(self, name: str):
        self.name = name
        self.start_time = None
        self.end_time = None
        self.memory_start = None
        self.memory_peak = None
        self.metrics = {}

    @property
    def elapsed_seconds(self) -> float:
        """Total elapsed time in seconds."""
        return self.end_time - self.start_time if self.end_time else 0.0

    @property
    def memory_used_mb(self) -> float:
        """Peak memory increase in MB."""
        if self.memory_peak and self.memory_start:
            return (self.memory_peak - self.memory_start) / 1024 / 1024
        return 0.0

    def add_metric(self, key: str, value: Any):
        """Add custom metric to results."""
        self.metrics[key] = value

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "name": self.name,
            "elapsed_seconds": self.elapsed_seconds,
            "memory_used_mb": self.memory_used_mb,
            "timestamp": datetime.now().isoformat(),
            "metrics": self.metrics
        }


@contextmanager
def benchmark(name: str):
    """
    Context manager for benchmarking code blocks.

    Usage:
        with benchmark("my_operation") as result:
            # code to benchmark
            result.add_metric("items_processed", 1000)
    """
    result = BenchmarkResult(name)
    process = psutil.Process()

    # Start measurements
    result.memory_start = process.memory_info().rss
    result.start_time = time.perf_counter()

    try:
        yield result
    finally:
        # End measurements
        result.end_time = time.perf_counter()
        result.memory_peak = process.memory_info().rss


def save_benchmark_results(results: List[BenchmarkResult], output_file: Path):
    """Save benchmark results to JSON file."""
    data = [r.to_dict() for r in results]

    # Load existing results if file exists
    if output_file.exists():
        with open(output_file) as f:
            existing = json.load(f)
        data = existing + data

    with open(output_file, 'w') as f:
        json.dump(data, f, indent=2)

    print(f"Saved benchmark results to {output_file}")


def print_results(results: List[BenchmarkResult]):
    """Print formatted benchmark results to console."""
    print("\n" + "="*80)
    print("BENCHMARK RESULTS")
    print("="*80)

    for result in results:
        print(f"\n{result.name}")
        print(f"  Time: {result.elapsed_seconds:.3f}s")
        print(f"  Memory: {result.memory_used_mb:.1f} MB")

        if result.metrics:
            print("  Metrics:")
            for key, value in result.metrics.items():
                print(f"    {key}: {value}")

    print("="*80 + "\n")

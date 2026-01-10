#!/usr/bin/env python3
"""
Rust vs Python CLI Performance Benchmark
Compares execution time across all implemented commands.

CHANGELOG:
- 01/10/2026 - Initial implementation (Claude)
"""
import subprocess
import time
import json
from pathlib import Path
from dataclasses import dataclass
from typing import List, Dict, Any, Optional
import statistics

PROJECT_ROOT = Path(__file__).parent.parent
RUST_CLI = PROJECT_ROOT / "gateway/wolfies-imessage/target/release/wolfies-imessage"
PYTHON_CLI = PROJECT_ROOT / "gateway/imessage_client.py"


@dataclass
class CommandBenchmark:
    """Configuration for a single command benchmark."""
    name: str
    rust_args: List[str]
    python_args: List[str]
    iterations: int = 10
    warmup: int = 2


@dataclass
class BenchmarkResult:
    """Results for a single benchmark run."""
    command: str
    rust_mean: float
    rust_median: float
    rust_min: float
    rust_max: float
    rust_stddev: float
    python_mean: float
    python_median: float
    python_min: float
    python_max: float
    python_stddev: float
    speedup: float
    rust_times: List[float]
    python_times: List[float]


def run_command(cmd: List[str], iterations: int = 10, warmup: int = 2) -> List[float]:
    """Run command multiple times and measure execution time.

    Args:
        cmd: Command to run as list of strings
        iterations: Number of iterations to run
        warmup: Number of warmup runs (not counted)

    Returns:
        List of execution times in milliseconds
    """
    times = []

    # Warmup runs
    for _ in range(warmup):
        subprocess.run(cmd, capture_output=True, timeout=30)

    # Measured runs
    for _ in range(iterations):
        start = time.perf_counter()
        result = subprocess.run(cmd, capture_output=True, timeout=30)
        end = time.perf_counter()

        if result.returncode != 0:
            print(f"Warning: Command failed: {' '.join(cmd)}")
            print(f"stderr: {result.stderr.decode()}")
            continue

        times.append((end - start) * 1000)  # Convert to milliseconds

    return times


def benchmark_command(bench: CommandBenchmark) -> Optional[BenchmarkResult]:
    """Benchmark a single command in both Rust and Python.

    Args:
        bench: CommandBenchmark configuration

    Returns:
        BenchmarkResult with timing statistics
    """
    print(f"\nBenchmarking: {bench.name}")
    print(f"  Iterations: {bench.iterations}, Warmup: {bench.warmup}")

    # Build Rust command
    rust_cmd = [str(RUST_CLI)] + bench.rust_args + ["--json"]
    print(f"  Rust: {' '.join(rust_cmd[1:])}")

    # Build Python command
    python_cmd = ["python3", str(PYTHON_CLI)] + bench.python_args + ["--json"]
    print(f"  Python: {' '.join(python_cmd[2:])}")

    # Run benchmarks
    try:
        rust_times = run_command(rust_cmd, bench.iterations, bench.warmup)
        python_times = run_command(python_cmd, bench.iterations, bench.warmup)

        if not rust_times or not python_times:
            print(f"  Skipped: insufficient successful runs")
            return None

        # Calculate statistics
        rust_mean = statistics.mean(rust_times)
        rust_median = statistics.median(rust_times)
        rust_min = min(rust_times)
        rust_max = max(rust_times)
        rust_stddev = statistics.stdev(rust_times) if len(rust_times) > 1 else 0

        python_mean = statistics.mean(python_times)
        python_median = statistics.median(python_times)
        python_min = min(python_times)
        python_max = max(python_times)
        python_stddev = statistics.stdev(python_times) if len(python_times) > 1 else 0

        speedup = python_mean / rust_mean

        print(f"  Rust:   {rust_mean:.1f}ms (median: {rust_median:.1f}ms)")
        print(f"  Python: {python_mean:.1f}ms (median: {python_median:.1f}ms)")
        print(f"  Speedup: {speedup:.2f}x")

        return BenchmarkResult(
            command=bench.name,
            rust_mean=rust_mean,
            rust_median=rust_median,
            rust_min=rust_min,
            rust_max=rust_max,
            rust_stddev=rust_stddev,
            python_mean=python_mean,
            python_median=python_median,
            python_min=python_min,
            python_max=python_max,
            python_stddev=python_stddev,
            speedup=speedup,
            rust_times=rust_times,
            python_times=python_times
        )
    except subprocess.TimeoutExpired:
        print(f"  Skipped: command timed out")
        return None
    except Exception as e:
        print(f"  Skipped: {e}")
        return None


def print_summary_table(results: List[BenchmarkResult]):
    """Print formatted summary table."""
    print("\n" + "="*100)
    print("RUST vs PYTHON PERFORMANCE COMPARISON")
    print("="*100)
    print(f"{'Command':<30} {'Rust (ms)':<15} {'Python (ms)':<15} {'Speedup':<10}")
    print("-"*100)

    for result in results:
        print(f"{result.command:<30} "
              f"{result.rust_mean:>7.1f} ± {result.rust_stddev:>5.1f}  "
              f"{result.python_mean:>7.1f} ± {result.python_stddev:>5.1f}  "
              f"{result.speedup:>6.2f}x")

    print("-"*100)

    # Overall statistics
    avg_speedup = statistics.mean([r.speedup for r in results])
    median_speedup = statistics.median([r.speedup for r in results])

    print(f"\nOverall Performance:")
    print(f"  Average speedup: {avg_speedup:.2f}x")
    print(f"  Median speedup:  {median_speedup:.2f}x")
    print("="*100 + "\n")


def save_results(results: List[BenchmarkResult], output_file: Path):
    """Save results to JSON file."""
    data = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "iterations": results[0].rust_times.__len__() if results else 0,
        "benchmarks": [
            {
                "command": r.command,
                "rust": {
                    "mean_ms": r.rust_mean,
                    "median_ms": r.rust_median,
                    "min_ms": r.rust_min,
                    "max_ms": r.rust_max,
                    "stddev_ms": r.rust_stddev,
                    "times_ms": r.rust_times
                },
                "python": {
                    "mean_ms": r.python_mean,
                    "median_ms": r.python_median,
                    "min_ms": r.python_min,
                    "max_ms": r.python_max,
                    "stddev_ms": r.python_stddev,
                    "times_ms": r.python_times
                },
                "speedup": r.speedup
            }
            for r in results
        ],
        "summary": {
            "average_speedup": statistics.mean([r.speedup for r in results]),
            "median_speedup": statistics.median([r.speedup for r in results]),
            "min_speedup": min([r.speedup for r in results]),
            "max_speedup": max([r.speedup for r in results])
        }
    }

    with open(output_file, 'w') as f:
        json.dump(data, f, indent=2)

    print(f"Results saved to: {output_file}")


def main():
    """Run all benchmarks and generate report."""
    print("Rust vs Python CLI Performance Benchmark")
    print("="*100)
    print(f"Rust CLI: {RUST_CLI}")
    print(f"Python CLI: {PYTHON_CLI}")

    # Verify binaries exist
    if not RUST_CLI.exists():
        print(f"\nError: Rust CLI not found at {RUST_CLI}")
        print("Build it with: cd gateway/wolfies-imessage && cargo build --release")
        return

    if not PYTHON_CLI.exists():
        print(f"\nError: Python CLI not found at {PYTHON_CLI}")
        return

    # Define benchmarks
    benchmarks = [
        # Reading commands
        CommandBenchmark(
            name="recent (10 conversations)",
            rust_args=["recent", "--limit", "10"],
            python_args=["recent", "--limit", "10"]
        ),
        CommandBenchmark(
            name="unread",
            rust_args=["unread"],
            python_args=["unread"]
        ),
        CommandBenchmark(
            name="text-search",
            rust_args=["text-search", "--query", "test", "--limit", "20"],
            python_args=["text-search", "--query", "test", "--limit", "20"]
        ),

        # Analytics commands
        CommandBenchmark(
            name="analytics (30 days)",
            rust_args=["analytics", "--days", "30"],
            python_args=["analytics", "--days", "30"]
        ),
        CommandBenchmark(
            name="followup (7 days)",
            rust_args=["followup", "--days", "7", "--stale", "2"],
            python_args=["followup", "--days", "7", "--stale", "2"]
        ),
        CommandBenchmark(
            name="reactions (100)",
            rust_args=["reactions", "--limit", "100"],
            python_args=["reactions", "--limit", "100"]
        ),

        # Discovery commands
        CommandBenchmark(
            name="handles (30 days)",
            rust_args=["handles", "--days", "30", "--limit", "50"],
            python_args=["handles", "--days", "30", "--limit", "50"]
        ),
        CommandBenchmark(
            name="unknown (30 days)",
            rust_args=["unknown", "--days", "30", "--limit", "50"],
            python_args=["unknown", "--days", "30", "--limit", "50"]
        ),
        CommandBenchmark(
            name="discover (90 days)",
            rust_args=["discover", "--days", "90", "--min-messages", "5", "--limit", "20"],
            python_args=["discover", "--days", "90", "--min-messages", "5", "--limit", "20"]
        ),

        # Group commands
        CommandBenchmark(
            name="groups (50)",
            rust_args=["groups", "--limit", "50"],
            python_args=["groups", "--limit", "50"]
        ),
    ]

    # Run benchmarks
    results = []
    for bench in benchmarks:
        result = benchmark_command(bench)
        if result:
            results.append(result)

    if not results:
        print("\nNo successful benchmarks completed.")
        return

    # Print summary
    print_summary_table(results)

    # Save results
    output_file = PROJECT_ROOT / "benchmarks/results/rust_vs_python_benchmark.json"
    output_file.parent.mkdir(parents=True, exist_ok=True)
    save_results(results, output_file)

    print(f"\n✅ Benchmark complete! Tested {len(results)} commands.")


if __name__ == "__main__":
    main()

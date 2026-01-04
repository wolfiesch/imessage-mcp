#!/usr/bin/env python3
"""
Benchmark suite for iMessage CLI Gateway performance testing.

Tests:
1. Command execution time (cold start)
2. Database query performance across different operations
3. Contact resolution speed
4. JSON output overhead
5. Comparison with MCP server startup

Usage:
    python3 gateway/benchmarks.py                    # Run all benchmarks
    python3 gateway/benchmarks.py --quick           # Run quick benchmarks only
    python3 gateway/benchmarks.py --json            # Output results as JSON
    python3 gateway/benchmarks.py --compare-mcp     # Include MCP server comparison
"""

import sys
import time
import json
import subprocess
import statistics
from pathlib import Path
from typing import Dict, List, Any
from dataclasses import dataclass, asdict
import argparse

# Project paths
SCRIPT_DIR = Path(__file__).parent
REPO_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(REPO_ROOT))

CLI_PATH = SCRIPT_DIR / "imessage_client.py"


@dataclass
class BenchmarkResult:
    """Result of a single benchmark run."""
    name: str
    description: str
    iterations: int
    mean_ms: float
    median_ms: float
    min_ms: float
    max_ms: float
    std_dev_ms: float
    success_rate: float


@dataclass
class BenchmarkSuite:
    """Collection of benchmark results."""
    suite_name: str
    timestamp: str
    results: List[BenchmarkResult]
    metadata: Dict[str, Any]


def run_cli_command(cmd: List[str], timeout: int = 30) -> tuple[float, bool, str]:
    """
    Run a CLI command and measure execution time.

    Returns:
        (execution_time_ms, success, output)
    """
    start = time.perf_counter()
    try:
        result = subprocess.run(
            ["python3", str(CLI_PATH)] + cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(REPO_ROOT)
        )
        elapsed = (time.perf_counter() - start) * 1000  # Convert to ms
        success = result.returncode == 0
        output = result.stdout if success else result.stderr
        return elapsed, success, output
    except subprocess.TimeoutExpired:
        elapsed = (time.perf_counter() - start) * 1000
        return elapsed, False, "TIMEOUT"
    except Exception as e:
        elapsed = (time.perf_counter() - start) * 1000
        return elapsed, False, str(e)


def benchmark_command(
    name: str,
    description: str,
    cmd: List[str],
    iterations: int = 10
) -> BenchmarkResult:
    """
    Benchmark a CLI command over multiple iterations.

    Args:
        name: Benchmark name
        description: What's being tested
        cmd: Command arguments (without python3 gateway/imessage_client.py)
        iterations: Number of times to run the command

    Returns:
        BenchmarkResult with timing statistics
    """
    print(f"Running: {name} ({iterations} iterations)...", end=" ", flush=True)

    timings = []
    successes = 0

    for i in range(iterations):
        elapsed, success, _ = run_cli_command(cmd)
        timings.append(elapsed)
        if success:
            successes += 1

    success_rate = (successes / iterations) * 100

    result = BenchmarkResult(
        name=name,
        description=description,
        iterations=iterations,
        mean_ms=statistics.mean(timings),
        median_ms=statistics.median(timings),
        min_ms=min(timings),
        max_ms=max(timings),
        std_dev_ms=statistics.stdev(timings) if len(timings) > 1 else 0,
        success_rate=success_rate
    )

    print(f"✓ (mean: {result.mean_ms:.2f}ms, success: {success_rate:.0f}%)")
    return result


def benchmark_startup_overhead(iterations: int = 20) -> BenchmarkResult:
    """Test CLI startup overhead with minimal command."""
    return benchmark_command(
        name="startup_overhead",
        description="CLI startup time with --help",
        cmd=["--help"],
        iterations=iterations
    )


def benchmark_contacts_list(iterations: int = 10) -> BenchmarkResult:
    """Test listing all contacts."""
    return benchmark_command(
        name="contacts_list",
        description="List all contacts (no JSON)",
        cmd=["contacts"],
        iterations=iterations
    )


def benchmark_contacts_list_json(iterations: int = 10) -> BenchmarkResult:
    """Test listing contacts with JSON output."""
    return benchmark_command(
        name="contacts_list_json",
        description="List all contacts with JSON serialization",
        cmd=["contacts", "--json"],
        iterations=iterations
    )


def benchmark_unread_messages(iterations: int = 10) -> BenchmarkResult:
    """Test fetching unread messages."""
    return benchmark_command(
        name="unread_messages",
        description="Fetch unread messages",
        cmd=["unread"],
        iterations=iterations
    )


def benchmark_recent_conversations(iterations: int = 10, limit: int = 10) -> BenchmarkResult:
    """Test fetching recent conversations."""
    return benchmark_command(
        name=f"recent_conversations_{limit}",
        description=f"Fetch {limit} recent conversations",
        cmd=["recent", "--limit", str(limit)],
        iterations=iterations
    )


def benchmark_search_small(iterations: int = 10) -> BenchmarkResult:
    """Test searching messages with small result set."""
    return benchmark_command(
        name="search_small",
        description="Search messages (limit 10)",
        cmd=["search", "Mom", "--limit", "10"],
        iterations=iterations
    )


def benchmark_search_medium(iterations: int = 10) -> BenchmarkResult:
    """Test searching messages with medium result set."""
    return benchmark_command(
        name="search_medium",
        description="Search messages (limit 50)",
        cmd=["search", "Mom", "--limit", "50"],
        iterations=iterations
    )


def benchmark_search_large(iterations: int = 5) -> BenchmarkResult:
    """Test searching messages with large result set."""
    return benchmark_command(
        name="search_large",
        description="Search messages (limit 200)",
        cmd=["search", "Mom", "--limit", "200"],
        iterations=iterations
    )


def benchmark_analytics(iterations: int = 5) -> BenchmarkResult:
    """Test conversation analytics (computationally intensive)."""
    return benchmark_command(
        name="analytics_30days",
        description="Conversation analytics for 30 days",
        cmd=["analytics", "--days", "30"],
        iterations=iterations
    )


def benchmark_followup_detection(iterations: int = 5) -> BenchmarkResult:
    """Test follow-up detection (complex query)."""
    return benchmark_command(
        name="followup_detection",
        description="Detect follow-ups needed (7 days)",
        cmd=["followup", "--days", "7"],
        iterations=iterations
    )


# =============================================================================
# NEW COMMAND BENCHMARKS (T0, T1, T2)
# =============================================================================


def benchmark_groups_list(iterations: int = 10) -> BenchmarkResult:
    """Test listing group chats."""
    return benchmark_command(
        name="groups_list",
        description="List group chats",
        cmd=["groups", "--json"],
        iterations=iterations
    )


def benchmark_attachments(iterations: int = 10) -> BenchmarkResult:
    """Test getting attachments."""
    return benchmark_command(
        name="attachments",
        description="Get attachments (photos/videos/files)",
        cmd=["attachments", "--limit", "20", "--json"],
        iterations=iterations
    )


def benchmark_reactions(iterations: int = 10) -> BenchmarkResult:
    """Test getting reactions/tapbacks."""
    return benchmark_command(
        name="reactions",
        description="Get reactions (tapbacks)",
        cmd=["reactions", "--limit", "20", "--json"],
        iterations=iterations
    )


def benchmark_links(iterations: int = 10) -> BenchmarkResult:
    """Test extracting links from messages."""
    return benchmark_command(
        name="links",
        description="Extract shared URLs",
        cmd=["links", "--limit", "20", "--json"],
        iterations=iterations
    )


def benchmark_voice_messages(iterations: int = 10) -> BenchmarkResult:
    """Test getting voice messages."""
    return benchmark_command(
        name="voice_messages",
        description="Get voice messages",
        cmd=["voice", "--limit", "10", "--json"],
        iterations=iterations
    )


def benchmark_handles(iterations: int = 10) -> BenchmarkResult:
    """Test listing recent handles."""
    return benchmark_command(
        name="handles_list",
        description="List recent phone/email handles",
        cmd=["handles", "--days", "7", "--json"],
        iterations=iterations
    )


def benchmark_unknown_senders(iterations: int = 5) -> BenchmarkResult:
    """Test finding unknown senders (computationally intensive)."""
    return benchmark_command(
        name="unknown_senders",
        description="Find messages from non-contacts",
        cmd=["unknown", "--days", "7", "--json"],
        iterations=iterations
    )


def benchmark_scheduled(iterations: int = 10) -> BenchmarkResult:
    """Test getting scheduled messages."""
    return benchmark_command(
        name="scheduled_messages",
        description="Get scheduled messages",
        cmd=["scheduled", "--json"],
        iterations=iterations
    )


def benchmark_summary(iterations: int = 5) -> BenchmarkResult:
    """Test getting conversation summary (complex)."""
    return benchmark_command(
        name="conversation_summary",
        description="Get AI-ready conversation summary",
        cmd=["summary", "Mom", "--limit", "50", "--json"],
        iterations=iterations
    )


def benchmark_mcp_server_startup(iterations: int = 10) -> BenchmarkResult:
    """
    Benchmark MCP server startup overhead.

    This simulates the cost of starting the MCP server for each Claude Code session.
    We measure the time to import and initialize the server.
    """
    print(f"Running: MCP server startup simulation ({iterations} iterations)...", end=" ", flush=True)

    timings = []
    successes = 0

    for _ in range(iterations):
        start = time.perf_counter()
        try:
            # Simulate MCP server import and initialization
            result = subprocess.run(
                [
                    "python3", "-c",
                    "import sys; "
                    f"sys.path.insert(0, '{REPO_ROOT}'); "
                    "from mcp_server.server import app; "
                    "print('initialized')"
                ],
                capture_output=True,
                text=True,
                timeout=10,
                cwd=str(REPO_ROOT)
            )
            elapsed = (time.perf_counter() - start) * 1000
            success = "initialized" in result.stdout
            timings.append(elapsed)
            if success:
                successes += 1
        except Exception:
            elapsed = (time.perf_counter() - start) * 1000
            timings.append(elapsed)

    success_rate = (successes / iterations) * 100 if iterations > 0 else 0

    result = BenchmarkResult(
        name="mcp_server_startup",
        description="MCP server import + initialization overhead",
        iterations=iterations,
        mean_ms=statistics.mean(timings) if timings else 0,
        median_ms=statistics.median(timings) if timings else 0,
        min_ms=min(timings) if timings else 0,
        max_ms=max(timings) if timings else 0,
        std_dev_ms=statistics.stdev(timings) if len(timings) > 1 else 0,
        success_rate=success_rate
    )

    print(f"✓ (mean: {result.mean_ms:.2f}ms, success: {success_rate:.0f}%)")
    return result


def run_quick_benchmarks() -> List[BenchmarkResult]:
    """Run a quick subset of benchmarks (fast execution)."""
    print("\n=== Quick Benchmark Suite ===\n")
    return [
        benchmark_startup_overhead(iterations=10),
        benchmark_contacts_list(iterations=5),
        benchmark_unread_messages(iterations=5),
        benchmark_recent_conversations(iterations=5, limit=10),
        benchmark_search_small(iterations=5),
    ]


def run_full_benchmarks() -> List[BenchmarkResult]:
    """Run the full benchmark suite."""
    print("\n=== Full Benchmark Suite ===\n")
    return [
        # Core operations
        benchmark_startup_overhead(iterations=20),
        benchmark_contacts_list(iterations=10),
        benchmark_contacts_list_json(iterations=10),

        # Message operations
        benchmark_unread_messages(iterations=10),
        benchmark_recent_conversations(iterations=10, limit=10),
        benchmark_recent_conversations(iterations=10, limit=50),

        # Search operations (varying complexity)
        benchmark_search_small(iterations=10),
        benchmark_search_medium(iterations=10),
        benchmark_search_large(iterations=5),

        # Complex operations
        benchmark_analytics(iterations=5),
        benchmark_followup_detection(iterations=5),

        # T0 Features - Core
        benchmark_groups_list(iterations=10),
        benchmark_attachments(iterations=10),

        # T1 Features - Advanced
        benchmark_reactions(iterations=10),
        benchmark_links(iterations=10),
        benchmark_voice_messages(iterations=10),

        # T2 Features - Discovery
        benchmark_handles(iterations=10),
        benchmark_unknown_senders(iterations=5),
        benchmark_scheduled(iterations=10),
        benchmark_summary(iterations=5),
    ]


def run_comparison_benchmarks() -> List[BenchmarkResult]:
    """Run benchmarks comparing Gateway CLI vs MCP server."""
    print("\n=== Gateway CLI vs MCP Server Comparison ===\n")

    cli_results = [
        benchmark_startup_overhead(iterations=20),
        benchmark_contacts_list(iterations=10),
        benchmark_search_small(iterations=10),
    ]

    mcp_result = benchmark_mcp_server_startup(iterations=20)

    return cli_results + [mcp_result]


def print_summary(results: List[BenchmarkResult]):
    """Print a human-readable summary of benchmark results."""
    print("\n" + "=" * 80)
    print("BENCHMARK RESULTS SUMMARY")
    print("=" * 80)

    # Group by performance tier
    fast = [r for r in results if r.mean_ms < 100]
    medium = [r for r in results if 100 <= r.mean_ms < 500]
    slow = [r for r in results if r.mean_ms >= 500]

    print("\n⚡ FAST (<100ms):")
    for r in fast:
        print(f"  {r.name:30s} {r.mean_ms:7.2f}ms ± {r.std_dev_ms:6.2f}ms")

    print("\n⚙️  MEDIUM (100-500ms):")
    for r in medium:
        print(f"  {r.name:30s} {r.mean_ms:7.2f}ms ± {r.std_dev_ms:6.2f}ms")

    print("\n🐌 SLOW (>500ms):")
    for r in slow:
        print(f"  {r.name:30s} {r.mean_ms:7.2f}ms ± {r.std_dev_ms:6.2f}ms")

    # Overall statistics
    print("\n" + "=" * 80)
    print("OVERALL STATISTICS:")
    all_means = [r.mean_ms for r in results]
    print(f"  Average execution time: {statistics.mean(all_means):.2f}ms")
    print(f"  Median execution time:  {statistics.median(all_means):.2f}ms")
    print(f"  Fastest operation:      {min(all_means):.2f}ms ({min(results, key=lambda r: r.mean_ms).name})")
    print(f"  Slowest operation:      {max(all_means):.2f}ms ({max(results, key=lambda r: r.mean_ms).name})")

    # Success rates
    failed = [r for r in results if r.success_rate < 100]
    if failed:
        print("\n⚠️  OPERATIONS WITH FAILURES:")
        for r in failed:
            print(f"  {r.name}: {r.success_rate:.0f}% success rate")
    else:
        print("\n✓ All operations completed successfully (100% success rate)")

    print("=" * 80)


def main():
    parser = argparse.ArgumentParser(
        description="Benchmark suite for iMessage CLI Gateway",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Run quick benchmarks only (faster)"
    )
    parser.add_argument(
        "--compare-mcp",
        action="store_true",
        help="Include MCP server comparison benchmarks"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON"
    )
    parser.add_argument(
        "--output",
        "-o",
        help="Save results to file (JSON format)"
    )

    args = parser.parse_args()

    # Run benchmarks
    if args.quick:
        results = run_quick_benchmarks()
    elif args.compare_mcp:
        results = run_comparison_benchmarks()
    else:
        results = run_full_benchmarks()

    # Create suite
    suite = BenchmarkSuite(
        suite_name="quick" if args.quick else "full",
        timestamp=time.strftime("%Y-%m-%d %H:%M:%S"),
        results=results,
        metadata={
            "cli_path": str(CLI_PATH),
            "total_benchmarks": len(results),
            "python_version": sys.version.split()[0]
        }
    )

    # Output results
    if args.json or args.output:
        output_data = {
            "suite_name": suite.suite_name,
            "timestamp": suite.timestamp,
            "metadata": suite.metadata,
            "results": [asdict(r) for r in suite.results]
        }

        if args.output:
            with open(args.output, 'w') as f:
                json.dump(output_data, f, indent=2)
            print(f"\nResults saved to {args.output}")
        else:
            print(json.dumps(output_data, indent=2))
    else:
        print_summary(results)

    return 0


if __name__ == '__main__':
    sys.exit(main())

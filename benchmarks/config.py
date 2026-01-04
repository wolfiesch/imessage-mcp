"""Benchmark configuration and constants."""
from pathlib import Path

# Benchmark data sizes
BENCHMARK_SIZES = {
    "tiny": 100,      # 100 messages - fast smoke test
    "small": 1000,    # 1k messages - quick validation
    "medium": 10000,  # 10k messages - realistic workload
    "large": 50000,   # 50k messages - full database
}

# Benchmark results directory
RESULTS_DIR = Path(__file__).parent / "results"
RESULTS_DIR.mkdir(exist_ok=True)

# Test data
MESSAGES_DB_PATH = Path.home() / "Library" / "Messages" / "chat.db"

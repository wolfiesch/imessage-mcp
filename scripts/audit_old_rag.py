#!/usr/bin/env python3
"""
Audit script to find usage of old RAG system.

Searches for imports and references to old RAG modules that should be replaced
with the new unified RAG system.

Usage:
    python3 scripts/audit_old_rag.py
"""

import os
import re
from pathlib import Path
from typing import List, Tuple

# Old RAG patterns to search for
OLD_RAG_PATTERNS = [
    # Old module imports
    r"from\s+(?:Texting\.)?src\.rag\.retriever\s+import",
    r"from\s+(?:Texting\.)?src\.rag\.indexer\s+import",
    r"from\s+(?:Texting\.)?src\.rag\.conversation_chunker\s+import",

    # Direct imports
    r"import\s+(?:Texting\.)?src\.rag\.retriever",
    r"import\s+(?:Texting\.)?src\.rag\.indexer",
    r"import\s+(?:Texting\.)?src\.rag\.conversation_chunker",

    # Old class usage
    r"Retriever\(",
    r"Indexer\(",

    # Old MCP tool names (in code, not tool definitions)
    r"ask_messages\s*\(",
    r"index_messages\s*\(",
]

# Files to exclude from search
EXCLUDE_PATTERNS = [
    r"\.git/",
    r"__pycache__/",
    r"\.pytest_cache/",
    r"\.pyc$",
    r"benchmarks/",
    r"scripts/audit_old_rag\.py",  # Don't flag ourselves
]


def should_exclude(file_path: str) -> bool:
    """Check if file should be excluded from search."""
    for pattern in EXCLUDE_PATTERNS:
        if re.search(pattern, file_path):
            return True
    return False


def search_file(file_path: Path) -> List[Tuple[int, str, str]]:
    """
    Search file for old RAG patterns.

    Returns:
        List of (line_number, pattern, line_content) tuples
    """
    matches = []

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, start=1):
                for pattern in OLD_RAG_PATTERNS:
                    if re.search(pattern, line):
                        matches.append((line_num, pattern, line.strip()))
    except (UnicodeDecodeError, PermissionError):
        # Skip binary files and files we can't read
        pass

    return matches


def audit_codebase(root_dir: Path) -> dict:
    """
    Audit entire codebase for old RAG usage.

    Returns:
        Dict mapping file paths to list of matches
    """
    results = {}

    for root, dirs, files in os.walk(root_dir):
        # Skip excluded directories
        dirs[:] = [d for d in dirs if not should_exclude(os.path.join(root, d))]

        for file in files:
            if not file.endswith('.py'):
                continue

            file_path = Path(root) / file

            if should_exclude(str(file_path)):
                continue

            matches = search_file(file_path)
            if matches:
                results[file_path] = matches

    return results


def print_results(results: dict):
    """Print audit results in readable format."""
    if not results:
        print("✅ No usage of old RAG system found!")
        print("\nSafe to proceed with deletion of old RAG code.")
        return

    print("⚠️  Found usage of old RAG system:\n")

    total_matches = sum(len(matches) for matches in results.values())
    print(f"Total: {len(results)} files with {total_matches} matches\n")
    print("=" * 80)

    for file_path, matches in sorted(results.items()):
        print(f"\n📄 {file_path}")
        print("-" * 80)

        for line_num, pattern, line_content in matches:
            print(f"  Line {line_num}: {line_content}")
            print(f"  Pattern: {pattern}")
            print()

    print("=" * 80)
    print("\n⚠️  Action Required:")
    print("1. Update imports to use new unified RAG system:")
    print("   - src.rag.retriever → src.rag.unified.retriever")
    print("   - src.rag.indexer → src.rag.unified.imessage_indexer")
    print("2. Update MCP tool calls:")
    print("   - ask_messages() → search_knowledge(sources=['imessage'])")
    print("   - index_messages() → index_knowledge(source='imessage')")
    print("3. Re-run this script after updates")


def main():
    """Main entry point."""
    project_root = Path(__file__).parent.parent

    print("Auditing codebase for old RAG system usage...")
    print(f"Root directory: {project_root}\n")

    results = audit_codebase(project_root)
    print_results(results)


if __name__ == "__main__":
    main()

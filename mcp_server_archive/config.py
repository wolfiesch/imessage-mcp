# ============================================================================
# CHANGELOG (recent first, max 5 entries)
# 01/03/2026 - Extracted from server.py during MCP refactoring (Claude)
# ============================================================================
"""
Configuration module for the iMessage MCP server.

Handles path resolution, logging setup, and configuration loading.
All paths are resolved relative to PROJECT_ROOT to ensure the server
works correctly regardless of the working directory it's started from.
"""

import json
import logging
from pathlib import Path

# Project root directory (for resolving relative paths)
# MCP servers can be started from arbitrary working directories,
# so we always resolve paths relative to this file's parent
PROJECT_ROOT = Path(__file__).parent.parent

# Configure logging with absolute path
LOG_DIR = PROJECT_ROOT / "logs"
LOG_DIR.mkdir(exist_ok=True)  # Ensure log directory exists

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_DIR / 'mcp_server.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

# Load configuration
CONFIG_PATH = PROJECT_ROOT / "config" / "mcp_server.json"
with open(CONFIG_PATH) as f:
    CONFIG = json.load(f)


def resolve_path(path_str: str) -> str:
    """
    Resolve a config path relative to PROJECT_ROOT or expand ~.

    MCP servers run from arbitrary working directories, so all paths
    must be resolved relative to the project root or as absolute paths.

    Args:
        path_str: Path string from configuration

    Returns:
        Resolved absolute path as string
    """
    path = Path(path_str)
    if path_str.startswith("~"):
        return str(path.expanduser())
    elif path.is_absolute():
        return str(path)
    else:
        return str(PROJECT_ROOT / path)


def get_data_path(subpath: str = "") -> Path:
    """
    Get a path within the data directory.

    Args:
        subpath: Optional subdirectory or file within data/

    Returns:
        Path object for the data location
    """
    data_dir = PROJECT_ROOT / "data"
    data_dir.mkdir(exist_ok=True)
    if subpath:
        return data_dir / subpath
    return data_dir


def get_chroma_path() -> str:
    """Get the ChromaDB persistence directory path."""
    chroma_dir = get_data_path("chroma")
    chroma_dir.mkdir(exist_ok=True)
    return str(chroma_dir)


def get_contacts_config_path() -> str:
    """Get the path to contacts.json configuration file."""
    return str(PROJECT_ROOT / "config" / "contacts.json")

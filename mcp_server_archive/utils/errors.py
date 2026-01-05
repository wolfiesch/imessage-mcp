# ============================================================================
# CHANGELOG (recent first, max 5 entries)
# 01/03/2026 - Enhanced database error messages with FDA detection (Claude)
# 01/03/2026 - Created for MCP server refactoring (Claude)
# ============================================================================
"""
Error handling utilities for MCP tool handlers.

Provides standardized error handling for common error scenarios,
particularly for RAG and external dependencies.
"""

import logging
from mcp import types

logger = logging.getLogger(__name__)

# Common error patterns for permission issues
PERMISSION_ERROR_PATTERNS = [
    "unable to open database",
    "permission denied",
    "no such file or directory",
    "operation not permitted",
    "access denied",
    "authorization not granted",
]

FULL_DISK_ACCESS_HELP = """
📋 To grant Full Disk Access:

1. Open System Settings (or System Preferences on older macOS)
2. Go to Privacy & Security → Full Disk Access
3. Click the lock to make changes
4. Add Terminal (or your IDE) to the list
5. Toggle it ON
6. Restart Terminal/Claude Code

The Messages database is protected by macOS privacy controls.
Claude needs Full Disk Access to read your iMessage history.
"""


def handle_rag_error(
    e: Exception,
    operation: str = ""
) -> list[types.TextContent]:
    """
    Handle RAG-specific errors with helpful messages.

    Args:
        e: The exception that was raised
        operation: Description of what operation was being performed

    Returns:
        Formatted error response with helpful troubleshooting info
    """
    if isinstance(e, ImportError):
        return [types.TextContent(
            type="text",
            text=(
                "RAG dependencies not installed.\n\n"
                "Run: pip install chromadb openai\n\n"
                f"Error: {e}"
            )
        )]
    elif isinstance(e, ValueError):
        return [types.TextContent(
            type="text",
            text=(
                f"Configuration error: {e}\n\n"
                "Make sure OPENAI_API_KEY environment variable is set "
                "if using OpenAI embeddings, or configure local embeddings."
            )
        )]
    else:
        error_msg = f"Error {operation}: {e}" if operation else f"Error: {e}"
        logger.error(error_msg, exc_info=True)
        return [types.TextContent(
            type="text",
            text=error_msg
        )]


def is_permission_error(error: Exception) -> bool:
    """
    Check if an error is likely a permission/access error.

    Args:
        error: The exception to check

    Returns:
        True if this looks like a permission error
    """
    error_str = str(error).lower()
    return any(pattern in error_str for pattern in PERMISSION_ERROR_PATTERNS)


def handle_database_error(
    e: Exception,
    operation: str = ""
) -> list[types.TextContent]:
    """
    Handle database-related errors with smart detection.

    Detects permission errors vs other database errors and provides
    actionable troubleshooting steps.

    Args:
        e: The exception that was raised
        operation: Description of what operation was being performed

    Returns:
        Formatted error response with specific troubleshooting info
    """
    error_msg = f"Database error"
    if operation:
        error_msg += f" during {operation}"
    error_msg += f": {e}"

    logger.error(error_msg, exc_info=True)

    # Check if this is a permission error (most common issue)
    if is_permission_error(e):
        return [types.TextContent(
            type="text",
            text=(
                f"❌ Cannot access Messages database\n\n"
                f"Error: {e}\n"
                f"{FULL_DISK_ACCESS_HELP}"
            )
        )]

    # Check for database locked error
    error_str = str(e).lower()
    if "locked" in error_str or "busy" in error_str:
        return [types.TextContent(
            type="text",
            text=(
                f"⏳ Database is locked\n\n"
                f"Error: {e}\n\n"
                "The Messages database may be in use by another process.\n"
                "Try:\n"
                "1. Close Messages.app (Cmd+Q)\n"
                "2. Wait a few seconds and try again\n"
                "3. If using Time Machine or iCloud sync, wait for it to complete"
            )
        )]

    # Generic database error
    return [types.TextContent(
        type="text",
        text=(
            f"{error_msg}\n\n"
            "Possible causes:\n"
            "• Full Disk Access permission not granted (most common)\n"
            "• Messages database is locked by another process\n"
            "• Database file is corrupted\n"
            "• macOS privacy restrictions\n\n"
            "Try checking Full Disk Access permissions first."
        )
    )]


def handle_applescript_error(
    e: Exception,
    operation: str = ""
) -> list[types.TextContent]:
    """
    Handle AppleScript-related errors.

    Args:
        e: The exception that was raised
        operation: Description of what operation was being performed

    Returns:
        Formatted error response with troubleshooting steps
    """
    error_msg = f"AppleScript error"
    if operation:
        error_msg += f" during {operation}"
    error_msg += f": {e}"

    logger.error(error_msg, exc_info=True)

    return [types.TextContent(
        type="text",
        text=(
            f"{error_msg}\n\n"
            "Troubleshooting:\n"
            "- Ensure Messages.app is running\n"
            "- Check Automation permissions in System Settings → Privacy & Security\n"
            "- Verify the phone number or handle is correct"
        )
    )]

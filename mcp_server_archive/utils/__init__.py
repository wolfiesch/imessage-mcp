# ============================================================================
# CHANGELOG (recent first, max 5 entries)
# 01/03/2026 - Created utils module for MCP server refactoring (Claude)
# ============================================================================
"""
MCP Server Utilities

Shared validation, response formatting, and error handling utilities
for the iMessage MCP server.
"""

from .validation import (
    validate_positive_int,
    validate_non_empty_string,
    validate_limit,
    validate_enum,
    MAX_MESSAGE_LIMIT,
    MAX_SEARCH_RESULTS,
    MIN_LIMIT,
)

from .responses import (
    text_response,
    success_response,
    error_response,
    validation_error,
    contact_not_found,
    empty_result,
)

from .errors import handle_rag_error

__all__ = [
    # Validation
    "validate_positive_int",
    "validate_non_empty_string",
    "validate_limit",
    "validate_enum",
    "MAX_MESSAGE_LIMIT",
    "MAX_SEARCH_RESULTS",
    "MIN_LIMIT",
    # Responses
    "text_response",
    "success_response",
    "error_response",
    "validation_error",
    "contact_not_found",
    "empty_result",
    # Errors
    "handle_rag_error",
]

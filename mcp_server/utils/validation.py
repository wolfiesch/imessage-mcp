# ============================================================================
# CHANGELOG (recent first, max 5 entries)
# 01/03/2026 - Made limits configurable via env vars (Claude)
# 01/03/2026 - Extracted from server.py during MCP refactoring (Claude)
# ============================================================================
"""
Validation utilities for MCP tool arguments.

Provides standardized validation functions that return (value, error) tuples.
"""

import os
from typing import Optional
from mcp import types

# Validation constants - configurable via environment variables
# Set IMESSAGE_MAX_LIMIT to override (e.g., for full history analysis)
MAX_MESSAGE_LIMIT = int(os.getenv("IMESSAGE_MAX_LIMIT", "500"))
MAX_SEARCH_RESULTS = int(os.getenv("IMESSAGE_MAX_SEARCH", "500"))
MIN_LIMIT = 1  # Minimum limit value


def validate_positive_int(
    value,
    name: str,
    min_val: int = MIN_LIMIT,
    max_val: int = MAX_MESSAGE_LIMIT
) -> tuple[int | None, str | None]:
    """
    Validate that a value is a positive integer within bounds.

    Args:
        value: Value to validate
        name: Parameter name for error messages
        min_val: Minimum allowed value
        max_val: Maximum allowed value

    Returns:
        Tuple of (validated_value, error_message). If valid, error_message is None.
    """
    if value is None:
        return None, None

    try:
        int_value = int(value)
    except (TypeError, ValueError):
        return None, f"Invalid {name}: must be an integer, got {type(value).__name__}"

    if int_value < min_val:
        return None, f"Invalid {name}: must be at least {min_val}, got {int_value}"

    if int_value > max_val:
        return None, f"Invalid {name}: must be at most {max_val}, got {int_value}"

    return int_value, None


def validate_non_empty_string(value, name: str) -> tuple[str | None, str | None]:
    """
    Validate that a value is a non-empty string.

    Args:
        value: Value to validate
        name: Parameter name for error messages

    Returns:
        Tuple of (validated_value, error_message). If valid, error_message is None.
    """
    if value is None:
        return None, f"Missing required parameter: {name}"

    if not isinstance(value, str):
        return None, f"Invalid {name}: must be a string, got {type(value).__name__}"

    stripped = value.strip()
    if not stripped:
        return None, f"Invalid {name}: cannot be empty"

    return stripped, None


def validate_limit(
    arguments: dict,
    default: int = 20,
    max_val: int = MAX_MESSAGE_LIMIT
) -> tuple[int, str | None]:
    """
    Extract and validate limit from arguments dict.

    This is a convenience wrapper for the common pattern of extracting
    and validating a 'limit' parameter.

    Args:
        arguments: The arguments dict from the tool call
        default: Default value if not provided
        max_val: Maximum allowed value

    Returns:
        Tuple of (limit_value, error_message). Uses default if not provided.
    """
    limit_raw = arguments.get("limit", default)
    limit, error = validate_positive_int(limit_raw, "limit", max_val=max_val)
    if error:
        return default, error
    return limit if limit is not None else default, None


def validate_enum(
    value,
    name: str,
    allowed_values: list[str],
    default: Optional[str] = None
) -> tuple[str | None, str | None]:
    """
    Validate that a value is one of the allowed values.

    Args:
        value: Value to validate
        name: Parameter name for error messages
        allowed_values: List of valid values
        default: Default value if not provided

    Returns:
        Tuple of (validated_value, error_message).
    """
    if value is None:
        if default is not None:
            return default, None
        return None, f"Missing required parameter: {name}"

    if value not in allowed_values:
        return None, (
            f"Invalid {name}: must be one of {allowed_values}, "
            f"got '{value}'"
        )

    return value, None


def validate_days(
    arguments: dict,
    default: int = 30,
    max_val: int = 1460
) -> tuple[int, str | None]:
    """
    Extract and validate days parameter from arguments dict.

    Args:
        arguments: The arguments dict from the tool call
        default: Default number of days
        max_val: Maximum allowed days (~4 years)

    Returns:
        Tuple of (days_value, error_message).
    """
    days_raw = arguments.get("days", default)
    days, error = validate_positive_int(days_raw, "days", max_val=max_val)
    if error:
        return default, error
    return days if days is not None else default, None

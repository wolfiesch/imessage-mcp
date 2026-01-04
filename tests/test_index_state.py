"""
Unit tests for IndexState persistence and tracking.
"""
import pytest
from pathlib import Path
from datetime import datetime, timedelta
import sys

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "Texting"))

from src.rag.unified.index_state import IndexState


def test_index_state_persistence(tmp_path):
    """State persists across instances."""
    state_file = tmp_path / "state.json"

    # Create and update
    state1 = IndexState(state_file)
    now = datetime.now()
    state1.update_last_indexed("imessage", now)

    # Load in new instance
    state2 = IndexState(state_file)
    loaded_time = state2.get_last_indexed("imessage")

    assert loaded_time is not None
    # Compare with some tolerance for serialization
    assert abs((loaded_time - now).total_seconds()) < 1


def test_index_state_no_previous_state():
    """get_last_indexed returns None when no state exists."""
    state_file = Path("/tmp/nonexistent_state.json")
    if state_file.exists():
        state_file.unlink()

    state = IndexState(state_file)
    assert state.get_last_indexed("imessage") is None


def test_index_state_multiple_sources(tmp_path):
    """Can track multiple sources independently."""
    state_file = tmp_path / "state.json"
    state = IndexState(state_file)

    now = datetime.now()
    yesterday = now - timedelta(days=1)

    state.update_last_indexed("imessage", now)
    state.update_last_indexed("gmail", yesterday)

    assert state.get_last_indexed("imessage") == now
    assert abs((state.get_last_indexed("gmail") - yesterday).total_seconds()) < 1


def test_index_state_reset_single_source(tmp_path):
    """Can reset a single source."""
    state_file = tmp_path / "state.json"
    state = IndexState(state_file)

    now = datetime.now()
    state.update_last_indexed("imessage", now)
    state.update_last_indexed("gmail", now)

    # Reset just imessage
    state.reset("imessage")

    assert state.get_last_indexed("imessage") is None
    assert state.get_last_indexed("gmail") is not None


def test_index_state_reset_all(tmp_path):
    """Can reset all sources."""
    state_file = tmp_path / "state.json"
    state = IndexState(state_file)

    now = datetime.now()
    state.update_last_indexed("imessage", now)
    state.update_last_indexed("gmail", now)

    # Reset all
    state.reset()

    assert state.get_last_indexed("imessage") is None
    assert state.get_last_indexed("gmail") is None


def test_index_state_get_all_states(tmp_path):
    """get_all_states returns all tracked sources."""
    state_file = tmp_path / "state.json"
    state = IndexState(state_file)

    now = datetime.now()
    state.update_last_indexed("imessage", now)
    state.update_last_indexed("gmail", now)

    all_states = state.get_all_states()
    assert "imessage" in all_states
    assert "gmail" in all_states
    assert len(all_states) == 2

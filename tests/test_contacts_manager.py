"""
Unit tests for ContactsManager.

Sprint 1: Basic contact lookup tests
"""

import pytest
import json
import tempfile
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.contacts_manager import ContactsManager, Contact


@pytest.fixture
def temp_contacts_file():
    """Create temporary contacts configuration file."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        config = {
            "contacts": [
                {
                    "name": "John Doe",
                    "phone": "+14155551234",
                    "relationship_type": "friend",
                    "notes": "Test contact 1"
                },
                {
                    "name": "Jane Smith",
                    "phone": "4155555678",
                    "relationship_type": "colleague",
                    "notes": "Test contact 2"
                }
            ]
        }
        json.dump(config, f)
        temp_path = f.name

    yield temp_path

    # Cleanup
    Path(temp_path).unlink()


def test_load_contacts(temp_contacts_file):
    """Test loading contacts from config file."""
    manager = ContactsManager(temp_contacts_file)

    assert len(manager.contacts) == 2
    assert manager.contacts[0].name == "John Doe"
    assert manager.contacts[1].name == "Jane Smith"


def test_get_contact_by_name_exact_match(temp_contacts_file):
    """Test exact name matching."""
    manager = ContactsManager(temp_contacts_file)

    contact = manager.get_contact_by_name("John Doe")
    assert contact is not None
    assert contact.name == "John Doe"
    assert contact.phone == "+14155551234"


def test_get_contact_by_name_case_insensitive(temp_contacts_file):
    """Test case-insensitive name matching."""
    manager = ContactsManager(temp_contacts_file)

    contact = manager.get_contact_by_name("john doe")
    assert contact is not None
    assert contact.name == "John Doe"


def test_get_contact_by_name_partial_match(temp_contacts_file):
    """Test partial name matching."""
    manager = ContactsManager(temp_contacts_file)

    contact = manager.get_contact_by_name("John")
    assert contact is not None
    assert contact.name == "John Doe"


def test_get_contact_by_name_not_found(temp_contacts_file):
    """Test contact not found."""
    manager = ContactsManager(temp_contacts_file)

    contact = manager.get_contact_by_name("Unknown Person")
    assert contact is None


def test_get_contact_by_phone(temp_contacts_file):
    """Test phone number lookup."""
    manager = ContactsManager(temp_contacts_file)

    # Full number with +1
    contact = manager.get_contact_by_phone("+14155551234")
    assert contact is not None
    assert contact.name == "John Doe"

    # Without country code
    contact = manager.get_contact_by_phone("4155551234")
    assert contact is not None
    assert contact.name == "John Doe"


def test_get_contact_by_phone_without_country_code(temp_contacts_file):
    """Test phone lookup handles different formats."""
    manager = ContactsManager(temp_contacts_file)

    # Contact stored without +1, search with it
    contact = manager.get_contact_by_phone("+14155555678")
    assert contact is not None
    assert contact.name == "Jane Smith"


def test_list_contacts(temp_contacts_file):
    """Test listing all contacts."""
    manager = ContactsManager(temp_contacts_file)

    all_contacts = manager.list_contacts()
    assert len(all_contacts) == 2
    assert all_contacts[0].name == "John Doe"
    assert all_contacts[1].name == "Jane Smith"


def test_add_contact(temp_contacts_file):
    """Test adding a new contact."""
    manager = ContactsManager(temp_contacts_file)

    initial_count = len(manager.contacts)

    new_contact = manager.add_contact(
        name="New Person",
        phone="+14155559999",
        relationship_type="family",
        notes="Test add"
    )

    assert new_contact.name == "New Person"
    assert len(manager.contacts) == initial_count + 1

    # Verify it can be found
    found = manager.get_contact_by_name("New Person")
    assert found is not None
    assert found.phone == "+14155559999"


def test_contact_to_dict():
    """Test Contact serialization."""
    contact = Contact(
        name="Test User",
        phone="+11234567890",
        relationship_type="other",
        notes="Test note"
    )

    contact_dict = contact.to_dict()

    assert contact_dict["name"] == "Test User"
    assert contact_dict["phone"] == "+11234567890"
    assert contact_dict["relationship_type"] == "other"
    assert contact_dict["notes"] == "Test note"

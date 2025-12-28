"""
Contact management for iMessage MCP server.

Sprint 1: Basic contact lookup from JSON config
Sprint 2: macOS Contacts sync, fuzzy matching, DB integration
"""

import json
import logging
from pathlib import Path
from typing import Optional, List, Dict

logger = logging.getLogger(__name__)


class Contact:
    """Represents a contact with messaging information."""

    def __init__(
        self,
        name: str,
        phone: str,
        relationship_type: str = "other",
        notes: str = ""
    ):
        self.name = name
        self.phone = phone
        self.relationship_type = relationship_type
        self.notes = notes

    def __repr__(self):
        return f"Contact(name='{self.name}', phone='{self.phone}')"

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "phone": self.phone,
            "relationship_type": self.relationship_type,
            "notes": self.notes
        }


class ContactsManager:
    """
    Manages contact lookup and resolution.

    Sprint 1: Load from JSON config file
    Sprint 2: Sync with macOS Contacts and Life Planner database
    """

    def __init__(self, config_path: str = "config/contacts.json"):
        """
        Initialize contacts manager.

        Args:
            config_path: Path to contacts configuration file
        """
        self.config_path = Path(config_path)
        self.contacts: List[Contact] = []
        self._load_contacts()

    def _load_contacts(self):
        """Load contacts from configuration file."""
        if not self.config_path.exists():
            logger.warning(f"Contacts config not found: {self.config_path}")
            logger.warning("Creating empty contacts.json - please add your contacts")
            self._create_default_config()
            return

        try:
            with open(self.config_path) as f:
                data = json.load(f)

            contacts_data = data.get("contacts", [])
            self.contacts = [
                Contact(
                    name=c["name"],
                    phone=c["phone"],
                    relationship_type=c.get("relationship_type", "other"),
                    notes=c.get("notes", "")
                )
                for c in contacts_data
            ]

            logger.info(f"Loaded {len(self.contacts)} contacts from config")

        except Exception as e:
            logger.error(f"Error loading contacts: {e}")
            self.contacts = []

    def _create_default_config(self):
        """Create default contacts configuration file."""
        default_config = {
            "_comment": "Manual contact configuration for Sprint 1",
            "_instructions": "Add your contacts here. Format: +1XXXXXXXXXX",
            "contacts": []
        }

        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.config_path, 'w') as f:
            json.dump(default_config, f, indent=2)

        logger.info(f"Created default config at {self.config_path}")

    def get_contact_by_name(self, name: str) -> Optional[Contact]:
        """
        Get contact by exact name match.

        Args:
            name: Contact name to search for

        Returns:
            Contact object if found, None otherwise

        Note:
            Sprint 1: Exact match only
            Sprint 2: Will add fuzzy matching
        """
        # Exact match (case-insensitive)
        for contact in self.contacts:
            if contact.name.lower() == name.lower():
                logger.info(f"Found contact: {contact.name} -> {contact.phone}")
                return contact

        # Try partial match (contains)
        for contact in self.contacts:
            if name.lower() in contact.name.lower():
                logger.info(f"Partial match: {contact.name} -> {contact.phone}")
                return contact

        logger.warning(f"Contact not found: {name}")
        return None

    def get_contact_by_phone(self, phone: str) -> Optional[Contact]:
        """
        Get contact by phone number.

        Args:
            phone: Phone number to search for

        Returns:
            Contact object if found, None otherwise
        """
        # Normalize phone for comparison (remove non-digits)
        normalized_search = ''.join(c for c in phone if c.isdigit())

        for contact in self.contacts:
            normalized_contact = ''.join(c for c in contact.phone if c.isdigit())

            # Match if search phone is suffix of contact phone
            # (handles +1 country code differences)
            if (normalized_contact.endswith(normalized_search) or
                normalized_search.endswith(normalized_contact)):
                logger.info(f"Found contact by phone: {contact.name}")
                return contact

        logger.warning(f"No contact found for phone: {phone}")
        return None

    def list_contacts(self) -> List[Contact]:
        """
        Get all contacts.

        Returns:
            List of all Contact objects
        """
        return self.contacts

    def add_contact(
        self,
        name: str,
        phone: str,
        relationship_type: str = "other",
        notes: str = ""
    ) -> Contact:
        """
        Add a new contact (Sprint 1: manual only).

        Args:
            name: Contact name
            phone: Phone number
            relationship_type: Type of relationship
            notes: Optional notes

        Returns:
            Created Contact object

        Note:
            Sprint 1: Only updates JSON config
            Sprint 2: Will also update Life Planner database
        """
        contact = Contact(name, phone, relationship_type, notes)
        self.contacts.append(contact)

        # Save to config
        self._save_contacts()

        logger.info(f"Added contact: {name}")
        return contact

    def _save_contacts(self):
        """Save contacts back to configuration file."""
        try:
            with open(self.config_path) as f:
                data = json.load(f)

            data["contacts"] = [c.to_dict() for c in self.contacts]

            with open(self.config_path, 'w') as f:
                json.dump(data, f, indent=2)

            logger.info("Saved contacts to config")

        except Exception as e:
            logger.error(f"Error saving contacts: {e}")

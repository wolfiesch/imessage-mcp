#!/usr/bin/env python3
"""
Sync contacts from macOS Contacts.app to JSON configuration.

Sprint 2: Standalone sync without Life Planner DB dependency.

Usage:
    python scripts/sync_contacts.py
    python scripts/sync_contacts.py --output config/contacts.json
"""

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import List, Dict

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.contacts_sync import (
    MacOSContactsReader,
    MacOSContact,
    normalize_phone_number
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def convert_macos_contact_to_json(contact: MacOSContact) -> Dict:
    """
    Convert MacOSContact to JSON-serializable dict for config file.

    Args:
        contact: MacOSContact object

    Returns:
        Dictionary with contact data
    """
    # Get primary phone number (prefer mobile, then first available)
    primary_phone = None
    for phone in contact.phone_numbers:
        label = phone["label"].lower()
        if "mobile" in label or "iphone" in label:
            primary_phone = phone["value"]
            break

    # If no mobile, use first phone number
    if not primary_phone and contact.phone_numbers:
        primary_phone = contact.phone_numbers[0]["value"]

    # Normalize phone number
    if primary_phone:
        primary_phone = normalize_phone_number(primary_phone)

    # Determine relationship type (default to "other" for now)
    # [*TO-DO*] - Sprint 4: Use Life Planner contact data to set relationship type
    relationship_type = "other"

    return {
        "name": contact.full_name,
        "phone": primary_phone or "",
        "relationship_type": relationship_type,
        "notes": f"Synced from macOS Contacts (ID: {contact.identifier})",
        "macos_contact_id": contact.identifier,
        "all_phones": [
            {
                "label": p["label"],
                "value": normalize_phone_number(p["value"])
            }
            for p in contact.phone_numbers
        ],
        "emails": contact.email_addresses
    }


def sync_contacts(
    output_path: Path,
    filter_no_phone: bool = True,
    merge_existing: bool = True
) -> int:
    """
    Sync contacts from macOS Contacts to JSON file.

    Args:
        output_path: Path to output JSON file
        filter_no_phone: Skip contacts without phone numbers
        merge_existing: Merge with existing contacts (preserve manual edits)

    Returns:
        Number of contacts synced
    """
    logger.info("Starting contact sync from macOS Contacts...")

    # Read contacts from macOS
    try:
        reader = MacOSContactsReader()
        macos_contacts = reader.fetch_all_contacts()
        logger.info(f"Fetched {len(macos_contacts)} contacts from macOS Contacts")
    except Exception as e:
        logger.error(f"Failed to read macOS Contacts: {e}")
        logger.error("Make sure you've granted Contacts permission")
        return 0

    # Filter contacts
    if filter_no_phone:
        macos_contacts = [c for c in macos_contacts if c.phone_numbers]
        logger.info(
            f"Filtered to {len(macos_contacts)} contacts with phone numbers"
        )

    # Convert to JSON format
    new_contacts = [
        convert_macos_contact_to_json(c)
        for c in macos_contacts
    ]

    # Load existing contacts if merging
    existing_contacts = []
    if merge_existing and output_path.exists():
        try:
            with open(output_path) as f:
                data = json.load(f)
                existing_contacts = data.get("contacts", [])
                logger.info(f"Loaded {len(existing_contacts)} existing contacts")
        except Exception as e:
            logger.warning(f"Could not load existing contacts: {e}")

    # Merge contacts
    # Strategy: Keep existing contacts, add new ones, update changed ones
    merged_contacts = {}

    # Add existing contacts (keyed by macOS ID or name)
    for contact in existing_contacts:
        key = contact.get("macos_contact_id") or contact["name"]
        merged_contacts[key] = contact

    # Update/add new contacts
    for contact in new_contacts:
        key = contact.get("macos_contact_id") or contact["name"]

        if key in merged_contacts:
            # Update existing contact (preserve manual fields)
            existing = merged_contacts[key]

            # Update phone and emails from macOS
            existing["phone"] = contact["phone"]
            existing["all_phones"] = contact["all_phones"]
            existing["emails"] = contact["emails"]

            # Update name if changed
            existing["name"] = contact["name"]

            # Preserve relationship_type and notes if manually set
            if not existing.get("notes", "").startswith("Synced from"):
                # Keep existing notes
                pass
            else:
                existing["notes"] = contact["notes"]

            logger.debug(f"Updated contact: {contact['name']}")
        else:
            # New contact
            merged_contacts[key] = contact
            logger.info(f"Added new contact: {contact['name']}")

    # Convert back to list
    final_contacts = list(merged_contacts.values())

    # Sort by name
    final_contacts.sort(key=lambda c: c["name"])

    # Write to file
    output_path.parent.mkdir(parents=True, exist_ok=True)

    output_data = {
        "_comment": "Auto-synced from macOS Contacts (Sprint 2)",
        "_instructions": "You can manually edit this file. Changes to relationship_type and notes will be preserved on next sync.",
        "_last_sync": None,  # Will be set after successful write
        "contacts": final_contacts
    }

    try:
        with open(output_path, 'w') as f:
            json.dump(output_data, f, indent=2)
        logger.info(f"Synced {len(final_contacts)} contacts to {output_path}")
        return len(final_contacts)
    except Exception as e:
        logger.error(f"Failed to write contacts file: {e}")
        return 0


def main():
    """Main entry point for contact sync script."""
    parser = argparse.ArgumentParser(
        description="Sync contacts from macOS Contacts to JSON config"
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=Path("config/contacts.json"),
        help="Output JSON file path (default: config/contacts.json)"
    )
    parser.add_argument(
        "--include-no-phone",
        action="store_true",
        help="Include contacts without phone numbers"
    )
    parser.add_argument(
        "--no-merge",
        action="store_true",
        help="Don't merge with existing contacts (overwrite)"
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Verbose logging"
    )

    args = parser.parse_args()

    # Set log level
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Sync contacts
    count = sync_contacts(
        output_path=args.output,
        filter_no_phone=not args.include_no_phone,
        merge_existing=not args.no_merge
    )

    if count > 0:
        print(f"\n✅ Successfully synced {count} contacts to {args.output}")
        print(f"\nNext steps:")
        print(f"1. Review the synced contacts: cat {args.output}")
        print(f"2. Edit relationship_type and notes as needed")
        print(f"3. Restart MCP server to load updated contacts")
        return 0
    else:
        print("\n❌ Contact sync failed. Check logs for details.")
        return 1


if __name__ == "__main__":
    sys.exit(main())

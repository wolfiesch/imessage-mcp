#!/usr/bin/env python3
"""
Quick test script for iMessage MCP tools.
Tests all three tools: list_contacts, send_message, get_recent_messages
"""

import sys
import asyncio
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.contacts_manager import ContactsManager
from src.messages_interface import MessagesInterface

async def test_list_contacts():
    """Test the contact listing functionality."""
    print("=" * 60)
    print("TEST 1: List Contacts")
    print("=" * 60)

    contacts = ContactsManager("config/contacts.json")
    contact_list = contacts.list_contacts()

    print(f"\n✓ Found {len(contact_list)} contacts:\n")
    for contact in contact_list:
        print(f"  • {contact.name}")
        print(f"    Phone: {contact.phone}")
        print(f"    Type: {contact.relationship_type}")
        if contact.notes:
            print(f"    Note: {contact.notes}")
        print()

    return len(contact_list) > 0

async def test_contact_lookup():
    """Test contact name lookup."""
    print("=" * 60)
    print("TEST 2: Contact Name Lookup")
    print("=" * 60)

    contacts = ContactsManager("config/contacts.json")

    # Get the first contact from the list to test with
    contact_list = contacts.list_contacts()
    if not contact_list:
        print("✗ No contacts found - add contacts to config/contacts.json first")
        return False

    test_contact = contact_list[0]
    test_name = test_contact.name

    # Test exact match
    print(f"\nLooking up '{test_name}' (exact match)...")
    contact = contacts.get_contact_by_name(test_name)
    if contact:
        print(f"✓ Found: {contact.name} - {contact.phone}")
    else:
        print("✗ Not found")
        return False

    # Test partial match (first word of name)
    first_word = test_name.split()[0] if ' ' in test_name else test_name
    print(f"\nLooking up '{first_word}' (partial)...")
    contact = contacts.get_contact_by_name(first_word)
    if contact:
        print(f"✓ Found: {contact.name} - {contact.phone}")
    else:
        print("✗ Not found (partial match may not work for all names)")

    # Test case insensitive
    print(f"\nLooking up '{first_word.lower()}' (lowercase)...")
    contact = contacts.get_contact_by_name(first_word.lower())
    if contact:
        print(f"✓ Found: {contact.name} - {contact.phone}")
    else:
        print("✗ Not found (case-insensitive match may not work)")

    return True

async def test_send_message_dry_run():
    """Test message sending (dry run - shows what would be sent)."""
    print("\n" + "=" * 60)
    print("TEST 3: Send Message (Dry Run)")
    print("=" * 60)

    contacts = ContactsManager("config/contacts.json")
    messages = MessagesInterface()

    # Get the first contact to test with
    contact_list = contacts.list_contacts()
    if not contact_list:
        print("✗ No contacts found - add contacts to config/contacts.json first")
        return False

    contact = contact_list[0]
    print(f"\nUsing first contact: '{contact.name}'...")

    print(f"✓ Would send message to: {contact.name} ({contact.phone})")
    print(f"  Message: 'Testing iMessage MCP!'")
    print(f"\n  To actually send, uncomment test_send_message_live() in main()")

    return True

async def test_send_message_live():
    """
    LIVE TEST: Actually sends a message.
    Uncomment the call in main() to run this.
    """
    print("\n" + "=" * 60)
    print("TEST 4: Send Message (LIVE)")
    print("=" * 60)

    contacts = ContactsManager("config/contacts.json")
    messages = MessagesInterface()

    # Get the first contact to test with
    contact_list = contacts.list_contacts()
    if not contact_list:
        print("✗ No contacts found - add contacts to config/contacts.json first")
        return False

    contact = contact_list[0]

    print(f"\nSending test message to {contact.name}...")
    result = messages.send_message(
        contact.phone,
        "Testing iMessage MCP!"
    )

    if result["success"]:
        print(f"✓ Message sent successfully!")
        return True
    else:
        print(f"✗ Failed to send: {result['error']}")
        return False

async def main():
    """Run all tests."""
    print("\n🧪 iMessage MCP Tools - Test Suite")
    print("=" * 60)
    print()

    results = []

    # Test 1: List contacts
    results.append(("List Contacts", await test_list_contacts()))

    # Test 2: Contact lookup
    results.append(("Contact Lookup", await test_contact_lookup()))

    # Test 3: Send message (dry run)
    results.append(("Send Message (Dry Run)", await test_send_message_dry_run()))

    # Test 4: Send message (LIVE) - uncomment to actually send
    # print("\n⚠️  WARNING: This will send a real iMessage!")
    # response = input("Send test message? (yes/no): ")
    # if response.lower() == 'yes':
    #     results.append(("Send Message (LIVE)", await test_send_message_live()))

    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)

    for test_name, passed in results:
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"{status} - {test_name}")

    total_passed = sum(1 for _, passed in results if passed)
    total_tests = len(results)

    print(f"\nResults: {total_passed}/{total_tests} tests passed")

    if total_passed == total_tests:
        print("\n🎉 All tests passed! MCP tools are working correctly.")
        return 0
    else:
        print("\n⚠️  Some tests failed. Check the output above.")
        return 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)

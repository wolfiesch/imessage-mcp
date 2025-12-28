"""
Unit tests for contacts sync functionality (Sprint 2).

Tests:
- Fuzzy name matching
- Phone number normalization
- macOS Contacts reading (requires macOS)
"""

import pytest
from src.contacts_sync import (
    FuzzyNameMatcher,
    normalize_phone_number,
    compare_phone_numbers,
    MacOSContact
)


class TestFuzzyNameMatcher:
    """Test fuzzy name matching algorithm."""

    def test_exact_match(self):
        """Test exact name match returns 1.0."""
        matcher = FuzzyNameMatcher(threshold=0.85)
        score = matcher.calculate_similarity("John Doe", "John Doe")
        assert score == 1.0

    def test_case_insensitive(self):
        """Test case-insensitive matching."""
        matcher = FuzzyNameMatcher(threshold=0.85)
        score = matcher.calculate_similarity("John Doe", "john doe")
        assert score == 1.0

    def test_typo_matching(self):
        """Test matching with typos."""
        matcher = FuzzyNameMatcher(threshold=0.85)
        score = matcher.calculate_similarity("John Doe", "Jon Doe")
        assert score > 0.85, "Should match 'Jon Doe' to 'John Doe' (typo)"

    def test_partial_name_matching(self):
        """Test partial name matching."""
        matcher = FuzzyNameMatcher(threshold=0.80)
        score = matcher.calculate_similarity("John", "John Doe")
        assert score >= 0.80, "Should match 'John' to 'John Doe'"

    def test_nickname_matching(self):
        """Test nickname matching."""
        matcher = FuzzyNameMatcher(threshold=0.75)
        score = matcher.calculate_similarity("Mike Smith", "Michael Smith")
        # Note: This might not match perfectly without nickname dictionary
        # but should still score reasonably high
        assert score > 0.60, "Should partially match nickname"

    def test_word_order_matching(self):
        """Test matching with different word order."""
        matcher = FuzzyNameMatcher(threshold=0.85)
        score = matcher.calculate_similarity("Doe John", "John Doe")
        assert score >= 0.85, "Should match despite word order"

    def test_find_best_match(self):
        """Test finding best match from candidates."""
        matcher = FuzzyNameMatcher(threshold=0.85)
        candidates = ["John Doe", "Jane Smith", "John Smith", "Bob Johnson"]

        result = matcher.find_best_match("John Doe", candidates)
        assert result is not None
        best_match, score = result
        assert best_match == "John Doe"
        assert score == 1.0

    def test_find_best_match_typo(self):
        """Test finding best match with typo."""
        matcher = FuzzyNameMatcher(threshold=0.85)
        candidates = ["John Doe", "Jane Smith", "John Smith"]

        result = matcher.find_best_match("Jon Doe", candidates)
        assert result is not None
        best_match, score = result
        assert best_match == "John Doe"
        assert score > 0.85

    def test_no_match_below_threshold(self):
        """Test that low matches return None."""
        matcher = FuzzyNameMatcher(threshold=0.90)
        candidates = ["John Doe", "Jane Smith"]

        result = matcher.find_best_match("Bob Johnson", candidates)
        assert result is None, "Should not match unrelated names"

    def test_find_all_matches(self):
        """Test finding multiple matches."""
        matcher = FuzzyNameMatcher(threshold=0.80)
        candidates = [
            "John Doe",
            "John Smith",
            "Johnny Doe",
            "Jane Doe",
            "Bob Johnson"
        ]

        matches = matcher.find_all_matches("John Doe", candidates, limit=3)
        assert len(matches) > 0
        assert matches[0][0] == "John Doe"  # Best match first
        assert matches[0][1] == 1.0

        # Should include other "John" names
        names = [m[0] for m in matches]
        assert "John Smith" in names or "Johnny Doe" in names


class TestPhoneNumberNormalization:
    """Test phone number normalization."""

    def test_basic_us_number(self):
        """Test basic US number normalization."""
        assert normalize_phone_number("(415) 555-1234") == "14155551234"

    def test_us_number_with_country_code(self):
        """Test US number with +1 country code."""
        assert normalize_phone_number("+1 (415) 555-1234") == "14155551234"

    def test_dots_format(self):
        """Test number with dots as separators."""
        assert normalize_phone_number("415.555.1234") == "14155551234"

    def test_spaces_format(self):
        """Test number with spaces."""
        assert normalize_phone_number("415 555 1234") == "14155551234"

    def test_no_formatting(self):
        """Test plain number."""
        assert normalize_phone_number("4155551234") == "14155551234"

    def test_already_normalized(self):
        """Test already normalized number."""
        assert normalize_phone_number("14155551234") == "14155551234"

    def test_international_number(self):
        """Test international number (UK)."""
        # +44 20 7946 0958
        assert normalize_phone_number("+44 20 7946 0958") == "442079460958"

    def test_international_number_germany(self):
        """Test German number."""
        # +49 30 123456
        assert normalize_phone_number("+49 30 123456") == "4930123456"

    def test_empty_string(self):
        """Test empty string."""
        assert normalize_phone_number("") == ""

    def test_invalid_input(self):
        """Test invalid input (no digits)."""
        assert normalize_phone_number("abc-def-ghij") == ""


class TestPhoneNumberComparison:
    """Test phone number comparison."""

    def test_exact_match(self):
        """Test exact match."""
        assert compare_phone_numbers("14155551234", "14155551234")

    def test_format_differences(self):
        """Test different formats of same number."""
        assert compare_phone_numbers(
            "+1 (415) 555-1234",
            "415.555.1234"
        )

    def test_country_code_difference(self):
        """Test with/without country code."""
        assert compare_phone_numbers("14155551234", "4155551234")
        assert compare_phone_numbers("4155551234", "14155551234")

    def test_different_numbers(self):
        """Test different numbers don't match."""
        assert not compare_phone_numbers("14155551234", "14155555678")

    def test_empty_numbers(self):
        """Test empty numbers don't match."""
        assert not compare_phone_numbers("", "14155551234")
        assert not compare_phone_numbers("14155551234", "")
        assert not compare_phone_numbers("", "")


class TestMacOSContact:
    """Test MacOSContact class."""

    def test_full_name_both_names(self):
        """Test full name with given and family name."""
        contact = MacOSContact(
            identifier="123",
            given_name="John",
            family_name="Doe"
        )
        assert contact.full_name == "John Doe"

    def test_full_name_given_only(self):
        """Test full name with only given name."""
        contact = MacOSContact(
            identifier="123",
            given_name="John"
        )
        assert contact.full_name == "John"

    def test_full_name_family_only(self):
        """Test full name with only family name."""
        contact = MacOSContact(
            identifier="123",
            family_name="Doe"
        )
        assert contact.full_name == "Doe"

    def test_full_name_organization(self):
        """Test full name falls back to organization."""
        contact = MacOSContact(
            identifier="123",
            organization="Acme Corp"
        )
        assert contact.full_name == "Acme Corp"

    def test_full_name_unknown(self):
        """Test full name defaults to Unknown."""
        contact = MacOSContact(identifier="123")
        assert contact.full_name == "Unknown"

    def test_phone_numbers(self):
        """Test phone numbers storage."""
        contact = MacOSContact(
            identifier="123",
            given_name="John",
            phone_numbers=[
                {"label": "mobile", "value": "+14155551234"},
                {"label": "work", "value": "+14155555678"}
            ]
        )
        assert len(contact.phone_numbers) == 2
        assert contact.phone_numbers[0]["label"] == "mobile"

    def test_email_addresses(self):
        """Test email addresses storage."""
        contact = MacOSContact(
            identifier="123",
            given_name="John",
            email_addresses=[
                {"label": "work", "value": "john@example.com"}
            ]
        )
        assert len(contact.email_addresses) == 1
        assert contact.email_addresses[0]["value"] == "john@example.com"


# Integration test (requires macOS and permissions)
# Skip by default - run with: pytest --run-integration
class TestMacOSContactsReader:
    """Integration tests for macOS Contacts reader."""

    @pytest.mark.skip(reason="Requires macOS Contacts access - run manually")
    def test_fetch_all_contacts(self):
        """Test fetching all contacts from macOS."""
        from src.contacts_sync import MacOSContactsReader

        try:
            reader = MacOSContactsReader()
            contacts = reader.fetch_all_contacts()

            assert isinstance(contacts, list)
            assert len(contacts) > 0, "Should have at least one contact"

            # Check first contact structure
            contact = contacts[0]
            assert hasattr(contact, "identifier")
            assert hasattr(contact, "full_name")
            assert hasattr(contact, "phone_numbers")

        except RuntimeError as e:
            pytest.skip(f"Contacts access denied: {e}")

    @pytest.mark.skip(reason="Requires macOS Contacts access - run manually")
    def test_search_contacts(self):
        """Test searching contacts."""
        from src.contacts_sync import MacOSContactsReader

        try:
            reader = MacOSContactsReader()
            # Search for a common name
            results = reader.search_contacts("John")

            assert isinstance(results, list)
            # May or may not have results depending on contacts

        except RuntimeError as e:
            pytest.skip(f"Contacts access denied: {e}")


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v"])

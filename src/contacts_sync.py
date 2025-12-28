"""
macOS Contacts synchronization for iMessage MCP server.

Sprint 2: Reads contacts from macOS Contacts.app and syncs to local JSON store.
"""

import logging
from typing import List, Dict, Optional, Tuple
from pathlib import Path

try:
    from fuzzywuzzy import fuzz
    FUZZY_AVAILABLE = True
except ImportError:
    FUZZY_AVAILABLE = False
    logging.warning("fuzzywuzzy not available - fuzzy matching disabled")

logger = logging.getLogger(__name__)


class MacOSContact:
    """Represents a contact from macOS Contacts.app."""

    def __init__(
        self,
        identifier: str,
        given_name: str = "",
        family_name: str = "",
        organization: str = "",
        phone_numbers: List[Dict[str, str]] = None,
        email_addresses: List[Dict[str, str]] = None
    ):
        self.identifier = identifier
        self.given_name = given_name
        self.family_name = family_name
        self.organization = organization
        self.phone_numbers = phone_numbers or []
        self.email_addresses = email_addresses or []

    @property
    def full_name(self) -> str:
        """Get full name of contact."""
        parts = []
        if self.given_name:
            parts.append(self.given_name)
        if self.family_name:
            parts.append(self.family_name)

        if parts:
            return " ".join(parts)
        elif self.organization:
            return self.organization
        else:
            return "Unknown"

    def __repr__(self):
        return f"MacOSContact(name='{self.full_name}', phones={len(self.phone_numbers)})"


class MacOSContactsReader:
    """
    Reads contacts from macOS Contacts.app using PyObjC.

    Requires PyObjC to be installed (usually pre-installed on macOS).
    """

    def __init__(self):
        """Initialize the macOS Contacts reader."""
        self.contacts_store = None
        self._init_contacts_store()

    def _init_contacts_store(self):
        """Initialize access to macOS Contacts framework."""
        try:
            # Import PyObjC Contacts framework
            import Contacts

            # Create contacts store
            self.contacts_store = Contacts.CNContactStore.alloc().init()

            # Request access to contacts
            self._request_access()

            logger.info("macOS Contacts framework initialized")

        except ImportError as e:
            logger.error("PyObjC Contacts framework not available")
            logger.error("Install with: pip install pyobjc-framework-Contacts")
            raise RuntimeError("PyObjC Contacts framework required") from e

    def _request_access(self):
        """Request access to contacts (if not already granted)."""
        import Contacts

        # Check current authorization status
        status = Contacts.CNContactStore.authorizationStatusForEntityType_(
            Contacts.CNEntityTypeContacts
        )

        if status == Contacts.CNAuthorizationStatusAuthorized:
            logger.info("Contacts access already authorized")
            return

        # Request access
        logger.info("Requesting Contacts access...")

        # Note: This is async in real usage, but for simplicity we'll check status
        # The first time this runs, macOS will show a permission prompt
        # We can't block waiting for the response, so we just proceed
        # If denied, subsequent operations will fail

    def fetch_all_contacts(self) -> List[MacOSContact]:
        """
        Fetch all contacts from macOS Contacts.app.

        Returns:
            List of MacOSContact objects

        Raises:
            RuntimeError: If Contacts access is denied
        """
        import Contacts

        # Check authorization
        status = Contacts.CNContactStore.authorizationStatusForEntityType_(
            Contacts.CNEntityTypeContacts
        )

        if status == Contacts.CNAuthorizationStatusDenied:
            raise RuntimeError(
                "Contacts access denied. Grant permission in System Settings → "
                "Privacy & Security → Contacts"
            )

        # Define keys to fetch
        keys_to_fetch = [
            Contacts.CNContactIdentifierKey,
            Contacts.CNContactGivenNameKey,
            Contacts.CNContactFamilyNameKey,
            Contacts.CNContactOrganizationNameKey,
            Contacts.CNContactPhoneNumbersKey,
            Contacts.CNContactEmailAddressesKey,
        ]

        # Create fetch request
        fetch_request = Contacts.CNContactFetchRequest.alloc().initWithKeysToFetch_(
            keys_to_fetch
        )

        # Fetch contacts
        contacts = []
        error = None

        def contact_handler(contact, stop):
            """Handler called for each contact."""
            try:
                # Extract phone numbers
                phone_numbers = []
                for labeled_value in contact.phoneNumbers():
                    label = labeled_value.label() or "other"
                    phone_number = labeled_value.value()
                    phone_str = phone_number.stringValue()

                    # Clean up label (remove CN prefix)
                    if label.startswith("_$!<"):
                        label = label[4:-3]  # Remove "_$!<" and ">!$_"

                    phone_numbers.append({
                        "label": label,
                        "value": phone_str
                    })

                # Extract email addresses
                email_addresses = []
                for labeled_value in contact.emailAddresses():
                    label = labeled_value.label() or "other"
                    email = str(labeled_value.value())

                    # Clean up label
                    if label.startswith("_$!<"):
                        label = label[4:-3]

                    email_addresses.append({
                        "label": label,
                        "value": email
                    })

                # Create MacOSContact object
                mac_contact = MacOSContact(
                    identifier=contact.identifier(),
                    given_name=contact.givenName() or "",
                    family_name=contact.familyName() or "",
                    organization=contact.organizationName() or "",
                    phone_numbers=phone_numbers,
                    email_addresses=email_addresses
                )

                contacts.append(mac_contact)

            except Exception as e:
                logger.error(f"Error processing contact: {e}")

        # Execute fetch
        success = self.contacts_store.enumerateContactsWithFetchRequest_error_usingBlock_(
            fetch_request,
            None,  # error pointer
            contact_handler
        )

        if not success:
            logger.error("Failed to fetch contacts from macOS Contacts")
            raise RuntimeError("Failed to fetch contacts")

        logger.info(f"Fetched {len(contacts)} contacts from macOS Contacts")
        return contacts

    def search_contacts(self, name: str) -> List[MacOSContact]:
        """
        Search contacts by name.

        Args:
            name: Name to search for

        Returns:
            List of matching MacOSContact objects
        """
        import Contacts

        # Define keys to fetch
        keys_to_fetch = [
            Contacts.CNContactIdentifierKey,
            Contacts.CNContactGivenNameKey,
            Contacts.CNContactFamilyNameKey,
            Contacts.CNContactOrganizationNameKey,
            Contacts.CNContactPhoneNumbersKey,
            Contacts.CNContactEmailAddressesKey,
        ]

        # Create predicate for name search
        predicate = Contacts.CNContact.predicateForContactsMatchingName_(name)

        # Fetch matching contacts
        try:
            matching_contacts = self.contacts_store.unifiedContactsMatchingPredicate_keysToFetch_error_(
                predicate,
                keys_to_fetch,
                None  # error pointer
            )

            # Convert to MacOSContact objects
            results = []
            for contact in matching_contacts:
                # Extract phone numbers
                phone_numbers = []
                for labeled_value in contact.phoneNumbers():
                    label = labeled_value.label() or "other"
                    phone_number = labeled_value.value()
                    phone_str = phone_number.stringValue()

                    if label.startswith("_$!<"):
                        label = label[4:-3]

                    phone_numbers.append({
                        "label": label,
                        "value": phone_str
                    })

                # Extract email addresses
                email_addresses = []
                for labeled_value in contact.emailAddresses():
                    label = labeled_value.label() or "other"
                    email = str(labeled_value.value())

                    if label.startswith("_$!<"):
                        label = label[4:-3]

                    email_addresses.append({
                        "label": label,
                        "value": email
                    })

                mac_contact = MacOSContact(
                    identifier=contact.identifier(),
                    given_name=contact.givenName() or "",
                    family_name=contact.familyName() or "",
                    organization=contact.organizationName() or "",
                    phone_numbers=phone_numbers,
                    email_addresses=email_addresses
                )

                results.append(mac_contact)

            logger.info(f"Found {len(results)} contacts matching '{name}'")
            return results

        except Exception as e:
            logger.error(f"Error searching contacts: {e}")
            return []


class FuzzyNameMatcher:
    """
    Fuzzy name matching for contact resolution.

    Handles typos, nicknames, and partial matches with confidence scoring.
    """

    def __init__(self, threshold: float = 0.85):
        """
        Initialize fuzzy matcher.

        Args:
            threshold: Minimum similarity score (0-1) to consider a match
        """
        self.threshold = threshold

        if not FUZZY_AVAILABLE:
            logger.warning(
                "Fuzzy matching not available. Install with: "
                "pip install fuzzywuzzy python-Levenshtein"
            )

    def calculate_similarity(self, name1: str, name2: str) -> float:
        """
        Calculate similarity between two names.

        Args:
            name1: First name
            name2: Second name

        Returns:
            Similarity score from 0.0 (no match) to 1.0 (exact match)
        """
        if not FUZZY_AVAILABLE:
            # Fallback to simple comparison
            return 1.0 if name1.lower() == name2.lower() else 0.0

        # Normalize names
        name1_norm = name1.lower().strip()
        name2_norm = name2.lower().strip()

        # Exact match
        if name1_norm == name2_norm:
            return 1.0

        # Use multiple fuzzy matching strategies and take the best score
        scores = []

        # 1. Token sort ratio - handles word order differences
        # "John Doe" vs "Doe John" -> high score
        scores.append(fuzz.token_sort_ratio(name1_norm, name2_norm))

        # 2. Token set ratio - handles partial matches
        # "John Michael Doe" vs "John Doe" -> high score
        scores.append(fuzz.token_set_ratio(name1_norm, name2_norm))

        # 3. Partial ratio - handles substring matches
        # "John" vs "John Doe" -> high score
        scores.append(fuzz.partial_ratio(name1_norm, name2_norm))

        # 4. Simple ratio - basic Levenshtein distance
        scores.append(fuzz.ratio(name1_norm, name2_norm))

        # Return best score (normalized to 0-1)
        return max(scores) / 100.0

    def find_best_match(
        self,
        query: str,
        candidates: List[str]
    ) -> Optional[Tuple[str, float]]:
        """
        Find best matching name from a list of candidates.

        Args:
            query: Name to search for
            candidates: List of candidate names

        Returns:
            Tuple of (best_match, score) if found, None if no matches above threshold
        """
        if not candidates:
            return None

        # Calculate scores for all candidates
        scored = [
            (candidate, self.calculate_similarity(query, candidate))
            for candidate in candidates
        ]

        # Sort by score (descending)
        scored.sort(key=lambda x: x[1], reverse=True)

        # Return best match if above threshold
        best_match, best_score = scored[0]

        if best_score >= self.threshold:
            logger.info(
                f"Fuzzy match: '{query}' -> '{best_match}' "
                f"(score: {best_score:.2f})"
            )
            return (best_match, best_score)
        else:
            logger.debug(
                f"No match above threshold for '{query}' "
                f"(best: '{best_match}' with {best_score:.2f})"
            )
            return None

    def find_all_matches(
        self,
        query: str,
        candidates: List[str],
        limit: int = 5
    ) -> List[Tuple[str, float]]:
        """
        Find top N matching names from candidates.

        Args:
            query: Name to search for
            candidates: List of candidate names
            limit: Maximum number of matches to return

        Returns:
            List of (name, score) tuples, sorted by score descending
        """
        if not candidates:
            return []

        # Calculate scores for all candidates
        scored = [
            (candidate, self.calculate_similarity(query, candidate))
            for candidate in candidates
        ]

        # Filter by threshold and sort
        filtered = [
            (name, score) for name, score in scored
            if score >= self.threshold
        ]
        filtered.sort(key=lambda x: x[1], reverse=True)

        # Return top N
        return filtered[:limit]


def normalize_phone_number(phone: str, default_country_code: str = "1") -> str:
    """
    Normalize phone number to a standard format.

    Handles:
    - International formats: +1 (415) 555-1234
    - National formats: (415) 555-1234
    - Various separators: dots, dashes, spaces, parentheses
    - Extensions: ignored

    Args:
        phone: Phone number in any format
        default_country_code: Country code to add if not present (default: "1" for US)

    Returns:
        Normalized phone number (digits only, with country code)

    Examples:
        "+1 (415) 555-1234" -> "14155551234"
        "(415) 555-1234" -> "14155551234"
        "415.555.1234" -> "14155551234"
        "+44 20 7946 0958" -> "442079460958"
    """
    # Check if phone already has international prefix
    has_plus = phone.strip().startswith("+")

    # Extract digits only
    digits = ''.join(c for c in phone if c.isdigit())

    if not digits:
        return ""

    # If input had "+", it already has country code - don't add default
    if has_plus:
        return digits

    # Handle country codes for domestic format inputs
    if len(digits) == 10:
        # US/CA number without country code - add default
        return default_country_code + digits
    elif len(digits) == 11:
        # Could be US with country code (1) or international
        # If starts with 1, assume US
        if digits[0] == "1":
            return digits
        else:
            # International 11-digit number (keep as-is)
            return digits
    elif len(digits) > 11 or len(digits) < 10:
        # International number or special case - return as-is
        return digits
    else:
        # Should not reach here, but return as-is
        return digits


def compare_phone_numbers(phone1: str, phone2: str) -> bool:
    """
    Compare two phone numbers for equality.

    Handles different formats and country codes intelligently.

    Args:
        phone1: First phone number
        phone2: Second phone number

    Returns:
        True if numbers match, False otherwise
    """
    # Normalize both numbers
    norm1 = normalize_phone_number(phone1)
    norm2 = normalize_phone_number(phone2)

    if not norm1 or not norm2:
        return False

    # Exact match
    if norm1 == norm2:
        return True

    # Handle US country code differences
    # "14155551234" should match "4155551234"
    if norm1.startswith("1") and len(norm1) == 11:
        norm1_no_country = norm1[1:]
        if norm1_no_country == norm2:
            return True

    if norm2.startswith("1") and len(norm2) == 11:
        norm2_no_country = norm2[1:]
        if norm2_no_country == norm1:
            return True

    # No match
    return False

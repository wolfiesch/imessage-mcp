//! Contact manager - load and lookup contacts from JSON.
//!
//! CHANGELOG:
//! - 01/10/2026 - Added fuzzy matching with score threshold (Claude)
//! - 01/10/2026 - Initial stub (Claude)

use super::fuzzy;
use anyhow::{Context, Result};
use serde::{Deserialize, Serialize};
use std::path::{Path, PathBuf};

/// Default contacts.json path.
///
/// Tries multiple locations in order:
/// 1. IMESSAGE_CONTACTS_PATH env var
/// 2. Texting/config/contacts.json (relative to LIFE-PLANNER)
/// 3. Compile-time path from CARGO_MANIFEST_DIR
pub fn default_contacts_path() -> PathBuf {
    // 1. Check env var
    if let Ok(path) = std::env::var("IMESSAGE_CONTACTS_PATH") {
        return PathBuf::from(path);
    }

    // 2. Try Texting/config/contacts.json in LIFE-PLANNER
    if let Some(home) = dirs::home_dir() {
        let life_planner_path = home
            .join("LIFE-PLANNER")
            .join("Texting")
            .join("config")
            .join("contacts.json");
        if life_planner_path.exists() {
            return life_planner_path;
        }
    }

    // 3. Fallback to compile-time path
    let project_root = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .and_then(|p| p.parent())
        .map(|p| p.to_path_buf())
        .unwrap_or_else(|| PathBuf::from("."));

    project_root.join("config").join("contacts.json")
}

/// A contact from the contacts.json file.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Contact {
    pub name: String,
    pub phone: String,
    #[serde(default)]
    pub relationship_type: String,
    #[serde(default)]
    pub notes: Option<String>,
}

/// Wrapper for contacts.json format (has "contacts" key).
#[derive(Debug, Deserialize)]
struct ContactsFile {
    contacts: Vec<Contact>,
}

/// Manages contacts loaded from JSON file.
#[derive(Debug, Clone)]
pub struct ContactsManager {
    contacts: Vec<Contact>,
}

impl ContactsManager {
    /// Load contacts from a JSON file.
    ///
    /// Supports both formats:
    /// - `{"contacts": [...]}` (Python format)
    /// - `[...]` (flat array)
    pub fn load<P: AsRef<Path>>(path: P) -> Result<Self> {
        let content = std::fs::read_to_string(path.as_ref())
            .with_context(|| format!("Failed to read contacts file: {:?}", path.as_ref()))?;

        // Try wrapped format first ({"contacts": [...]})
        if let Ok(wrapper) = serde_json::from_str::<ContactsFile>(&content) {
            return Ok(Self {
                contacts: wrapper.contacts,
            });
        }

        // Fallback to flat array format
        let contacts: Vec<Contact> = serde_json::from_str(&content)
            .with_context(|| "Failed to parse contacts JSON")?;

        Ok(Self { contacts })
    }

    /// Load from default path.
    pub fn load_default() -> Result<Self> {
        Self::load(default_contacts_path())
    }

    /// Create an empty manager (for when contacts aren't available).
    pub fn empty() -> Self {
        Self { contacts: Vec::new() }
    }

    /// Get all contacts.
    pub fn all(&self) -> &[Contact] {
        &self.contacts
    }

    /// Find a contact by name (exact, case-insensitive).
    pub fn find_by_name(&self, name: &str) -> Option<&Contact> {
        let name_lower = name.to_lowercase();
        self.contacts
            .iter()
            .find(|c| c.name.to_lowercase() == name_lower)
    }

    /// Find a contact by phone number.
    pub fn find_by_phone(&self, phone: &str) -> Option<&Contact> {
        let normalized = normalize_phone(phone);
        self.contacts
            .iter()
            .find(|c| normalize_phone(&c.phone) == normalized)
    }

    /// Find contact with fuzzy matching.
    ///
    /// Order of matching:
    /// 1. Exact name match
    /// 2. Partial name match (name contains query)
    /// 3. Fuzzy match with score >= 0.85
    pub fn find_fuzzy(&self, name: &str) -> Option<&Contact> {
        // First try exact match
        if let Some(contact) = self.find_by_name(name) {
            return Some(contact);
        }

        // Then try partial match
        let name_lower = name.to_lowercase();
        if let Some(contact) = self.contacts.iter().find(|c| {
            c.name.to_lowercase().contains(&name_lower)
        }) {
            return Some(contact);
        }

        // Finally try fuzzy match with threshold
        let mut best_match: Option<(&Contact, f64)> = None;
        for contact in &self.contacts {
            let match_result = fuzzy::multi_match(name, &contact.name);
            if match_result.score >= fuzzy::DEFAULT_THRESHOLD {
                if best_match.as_ref().map_or(true, |(_, score)| match_result.score > *score) {
                    best_match = Some((contact, match_result.score));
                }
            }
        }

        best_match.map(|(c, _)| c)
    }

    /// Resolve a name or phone to a phone number.
    ///
    /// If input looks like a phone number, returns it normalized.
    /// Otherwise, tries to resolve as a contact name.
    pub fn resolve_to_phone(&self, name_or_phone: &str) -> Option<String> {
        // Check if it's already a phone number
        let digits: String = name_or_phone.chars().filter(|c| c.is_ascii_digit()).collect();
        if digits.len() >= 10 {
            // Looks like a phone number
            return Some(format!("+{}", digits));
        }

        // Try to resolve as contact name
        self.find_fuzzy(name_or_phone)
            .map(|c| c.phone.clone())
    }
}

/// Normalize phone number for comparison.
fn normalize_phone(phone: &str) -> String {
    phone
        .chars()
        .filter(|c| c.is_ascii_digit())
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_normalize_phone() {
        assert_eq!(normalize_phone("+1 (415) 555-1234"), "14155551234");
        assert_eq!(normalize_phone("+14155551234"), "14155551234");
    }
}

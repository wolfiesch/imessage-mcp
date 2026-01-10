//! Messaging commands: send, send-by-phone.
//!
//! CHANGELOG:
//! - 01/10/2026 - Implemented send and send_by_phone with AppleScript (Claude)
//! - 01/10/2026 - Initial stub implementation (Claude)

use crate::applescript;
use crate::contacts::manager::ContactsManager;
use crate::output::OutputControls;
use anyhow::{anyhow, Context, Result};
use serde_json::json;

/// Normalize a phone number for sending.
///
/// Strips non-digit characters and ensures + prefix for international format.
fn normalize_phone(phone: &str) -> String {
    let digits: String = phone.chars().filter(|c| c.is_ascii_digit()).collect();

    // If already has + prefix, keep it
    if phone.starts_with('+') {
        return phone.to_string();
    }

    // Add + prefix for 10+ digit numbers
    if digits.len() >= 10 {
        format!("+{}", digits)
    } else {
        digits
    }
}

/// Send a message to a contact by name.
///
/// Resolves the contact name to a phone number using fuzzy matching,
/// then sends the message via AppleScript.
pub fn send(contact: &str, message: &str, output: &OutputControls) -> Result<()> {
    // Load contacts
    let contacts = ContactsManager::load_default()
        .context("Failed to load contacts. Run 'python3 scripts/sync_contacts.py' first.")?;

    // Resolve contact to phone number
    let phone = contacts
        .resolve_to_phone(contact)
        .ok_or_else(|| anyhow!("Contact '{}' not found", contact))?;

    // Send via AppleScript
    applescript::send_imessage(&phone, message).context("Failed to send message")?;

    // Output result
    if output.json {
        output.print(&json!({
            "success": true,
            "contact": contact,
            "phone": phone,
            "message": message
        }));
    } else {
        println!("Message sent to {} ({})", contact, phone);
    }

    Ok(())
}

/// Send message directly to a phone number.
///
/// Normalizes the phone number and sends via AppleScript.
pub fn send_by_phone(phone: &str, message: &str, output: &OutputControls) -> Result<()> {
    let normalized = normalize_phone(phone);

    // Send via AppleScript
    match applescript::send_imessage(&normalized, message) {
        Ok(()) => {
            if output.json {
                output.print(&json!({
                    "success": true,
                    "phone": normalized,
                    "message": message
                }));
            } else {
                println!("Message sent to {}", normalized);
            }
            Ok(())
        }
        Err(e) => {
            if output.json {
                output.print(&json!({
                    "success": false,
                    "phone": normalized,
                    "error": e.to_string()
                }));
            } else {
                eprintln!("Failed to send message: {}", e);
            }
            Err(e)
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_normalize_phone_with_plus() {
        assert_eq!(normalize_phone("+14155551234"), "+14155551234");
    }

    #[test]
    fn test_normalize_phone_digits_only() {
        assert_eq!(normalize_phone("4155551234"), "+4155551234");
    }

    #[test]
    fn test_normalize_phone_formatted() {
        assert_eq!(normalize_phone("(415) 555-1234"), "+4155551234");
    }

    #[test]
    fn test_normalize_phone_with_country() {
        assert_eq!(normalize_phone("1-415-555-1234"), "+14155551234");
    }
}

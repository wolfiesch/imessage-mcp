//! Contact commands: contacts, add-contact.
//!
//! CHANGELOG:
//! - 01/10/2026 - Implemented list and add with JSON file I/O (Claude)
//! - 01/10/2026 - Initial stub implementation (Claude)

use crate::contacts::manager::{default_contacts_path, Contact, ContactsManager};
use crate::output::OutputControls;
use anyhow::{Context, Result};

/// List all contacts.
pub fn list(output: &OutputControls) -> Result<()> {
    let contacts = ContactsManager::load_default().unwrap_or_else(|_| ContactsManager::empty());

    let all = contacts.all();

    if output.json {
        // Convert slice to Vec for serialization
        let contacts_vec: Vec<&Contact> = all.iter().collect();
        output.print(&contacts_vec);
    } else {
        if all.is_empty() {
            println!("No contacts found.");
            println!("Run 'python3 scripts/sync_contacts.py' to sync from macOS Contacts.");
            return Ok(());
        }

        println!("Contacts ({}):", all.len());
        println!("{}", "-".repeat(50));
        for contact in all {
            let rel = if contact.relationship_type.is_empty() {
                String::new()
            } else {
                format!(" [{}]", contact.relationship_type)
            };
            println!("{}: {}{}", contact.name, contact.phone, rel);
        }
    }

    Ok(())
}

/// Add a new contact.
pub fn add(name: &str, phone: &str, relationship: &str, notes: Option<&str>) -> Result<()> {
    let path = default_contacts_path();

    // Load existing contacts or start with empty list
    let mut contacts: Vec<Contact> = if path.exists() {
        let content = std::fs::read_to_string(&path)
            .with_context(|| format!("Failed to read contacts file: {:?}", path))?;
        serde_json::from_str(&content).with_context(|| "Failed to parse contacts JSON")?
    } else {
        // Create parent directory if needed
        if let Some(parent) = path.parent() {
            std::fs::create_dir_all(parent)
                .with_context(|| format!("Failed to create directory: {:?}", parent))?;
        }
        Vec::new()
    };

    // Check for duplicate phone
    let normalized: String = phone.chars().filter(|c| c.is_ascii_digit()).collect();
    for existing in &contacts {
        let existing_normalized: String = existing
            .phone
            .chars()
            .filter(|c| c.is_ascii_digit())
            .collect();
        if existing_normalized == normalized {
            println!(
                "Contact with phone {} already exists: {}",
                phone, existing.name
            );
            return Ok(());
        }
    }

    // Add new contact
    let new_contact = Contact {
        name: name.to_string(),
        phone: phone.to_string(),
        relationship_type: relationship.to_string(),
        notes: notes.map(String::from),
    };

    contacts.push(new_contact);

    // Write back to file
    let json = serde_json::to_string_pretty(&contacts)?;
    std::fs::write(&path, json).with_context(|| format!("Failed to write contacts file: {:?}", path))?;

    println!("Added contact: {} ({})", name, phone);

    Ok(())
}

#[cfg(test)]
mod tests {
    // Tests would go here but require mocking file I/O
}

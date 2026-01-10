//! Discovery commands: handles, unknown, discover, scheduled.
//!
//! CHANGELOG:
//! - 01/10/2026 - Added contact caching (Phase 4A) - accepts Arc<ContactsManager> (Claude)
//! - 01/10/2026 - Initial stub implementation (Claude)
//! - 01/10/2026 - Implemented handles discovery command (Claude)
//! - 01/10/2026 - Implemented unknown senders command (Claude)
//! - 01/10/2026 - Implemented discover frequent texters command (Claude)
//! - 01/10/2026 - Implemented scheduled messages stub (not supported by Messages.db) (Claude)

use anyhow::Result;
use rusqlite;
use serde::Serialize;
use std::sync::Arc;

use crate::contacts::manager::ContactsManager;
use crate::db::{connection::open_db, queries};

#[derive(Debug, Serialize)]
struct Handle {
    handle: String,
    message_count: i64,
    last_message_date: String,
}

#[derive(Debug, Serialize)]
struct UnknownSender {
    handle: String,
    message_count: i64,
    last_message_date: String,
    sample_text: Option<String>,
}

/// List all phone/email handles from recent messages.
pub fn handles(days: u32, limit: u32, json: bool) -> Result<()> {
    let conn = open_db()?;
    let cutoff_cocoa = queries::days_ago_cocoa(days);

    // Query handles
    let mut stmt = conn.prepare(queries::DISCOVERY_HANDLES)?;
    let handle_rows = stmt.query_map([cutoff_cocoa, limit as i64], |row: &rusqlite::Row| {
        let handle: String = row.get(0)?;
        let message_count: i64 = row.get(1)?;
        let last_message_cocoa: i64 = row.get(2)?;

        // Convert Cocoa timestamp to ISO string
        let unix_ts = queries::cocoa_to_unix(last_message_cocoa);
        use std::time::{UNIX_EPOCH, Duration};
        let system_time = UNIX_EPOCH + Duration::from_secs(unix_ts as u64);
        let datetime: chrono::DateTime<chrono::Utc> = system_time.into();

        Ok(Handle {
            handle,
            message_count,
            last_message_date: datetime.to_rfc3339(),
        })
    })?;

    let handles: Vec<Handle> = handle_rows
        .filter_map(|r: rusqlite::Result<Handle>| r.ok())
        .collect();

    // Output
    if json {
        println!("{}", serde_json::to_string_pretty(&handles)?);
    } else {
        if handles.is_empty() {
            println!("No handles found.");
            return Ok(());
        }

        println!("Handles ({}):", handles.len());
        println!("{:-<60}", "");
        for h in &handles {
            println!("{}: {} messages (last: {})", h.handle, h.message_count, h.last_message_date);
        }
    }

    Ok(())
}

/// Find messages from senders not in contacts.
pub fn unknown(days: u32, limit: u32, json: bool, contacts: &Arc<ContactsManager>) -> Result<()> {
    let conn = open_db()?;
    let cutoff_cocoa = queries::days_ago_cocoa(days);

    // Query all handles with recent messages
    let mut stmt = conn.prepare(queries::DISCOVERY_UNKNOWN)?;
    let unknown_rows = stmt.query_map([cutoff_cocoa], |row: &rusqlite::Row| {
        let handle: String = row.get(0)?;
        let message_count: i64 = row.get(1)?;
        let last_message_cocoa: i64 = row.get(2)?;
        let sample_text: Option<String> = row.get(3)?;

        // Convert Cocoa timestamp to ISO string
        let unix_ts = queries::cocoa_to_unix(last_message_cocoa);
        use std::time::{UNIX_EPOCH, Duration};
        let system_time = UNIX_EPOCH + Duration::from_secs(unix_ts as u64);
        let datetime: chrono::DateTime<chrono::Utc> = system_time.into();

        Ok(UnknownSender {
            handle,
            message_count,
            last_message_date: datetime.to_rfc3339(),
            sample_text,
        })
    })?;

    // Filter out known contacts
    let unknown_senders: Vec<UnknownSender> = unknown_rows
        .filter_map(|r: rusqlite::Result<UnknownSender>| r.ok())
        .filter(|sender| contacts.find_by_phone(&sender.handle).is_none())
        .take(limit as usize)
        .collect();

    // Output
    if json {
        println!("{}", serde_json::to_string_pretty(&unknown_senders)?);
    } else {
        if unknown_senders.is_empty() {
            println!("No unknown senders found.");
            return Ok(());
        }

        println!("Unknown Senders ({}):", unknown_senders.len());
        println!("{:-<60}", "");
        for sender in &unknown_senders {
            println!("{}: {} messages (last: {})", sender.handle, sender.message_count, sender.last_message_date);
            if let Some(ref text) = sender.sample_text {
                let preview = if text.len() > 60 {
                    format!("{}...", &text[..60])
                } else {
                    text.clone()
                };
                println!("  Sample: {}", preview);
            }
        }
    }

    Ok(())
}

/// Discover frequent texters not in contacts.
pub fn discover(days: u32, limit: u32, min_messages: u32, json: bool, contacts: &Arc<ContactsManager>) -> Result<()> {
    let conn = open_db()?;
    let cutoff_cocoa = queries::days_ago_cocoa(days);

    // Query all handles with recent messages
    let mut stmt = conn.prepare(queries::DISCOVERY_UNKNOWN)?;
    let unknown_rows = stmt.query_map([cutoff_cocoa], |row: &rusqlite::Row| {
        let handle: String = row.get(0)?;
        let message_count: i64 = row.get(1)?;
        let last_message_cocoa: i64 = row.get(2)?;
        let sample_text: Option<String> = row.get(3)?;

        // Convert Cocoa timestamp to ISO string
        let unix_ts = queries::cocoa_to_unix(last_message_cocoa);
        use std::time::{UNIX_EPOCH, Duration};
        let system_time = UNIX_EPOCH + Duration::from_secs(unix_ts as u64);
        let datetime: chrono::DateTime<chrono::Utc> = system_time.into();

        Ok(UnknownSender {
            handle,
            message_count,
            last_message_date: datetime.to_rfc3339(),
            sample_text,
        })
    })?;

    // Filter out known contacts and apply min_messages threshold
    let mut frequent_texters: Vec<UnknownSender> = unknown_rows
        .filter_map(|r: rusqlite::Result<UnknownSender>| r.ok())
        .filter(|sender| {
            contacts.find_by_phone(&sender.handle).is_none()
                && sender.message_count >= min_messages as i64
        })
        .collect();

    // Sort by message count descending (most active first)
    frequent_texters.sort_by(|a, b| b.message_count.cmp(&a.message_count));
    frequent_texters.truncate(limit as usize);

    // Output
    if json {
        println!("{}", serde_json::to_string_pretty(&frequent_texters)?);
    } else {
        if frequent_texters.is_empty() {
            println!("No frequent texters found (min {} messages).", min_messages);
            return Ok(());
        }

        println!("Frequent Texters Not in Contacts ({}):", frequent_texters.len());
        println!("{:-<60}", "");
        println!("Suggestion: Consider adding these contacts");
        println!();
        for sender in &frequent_texters {
            println!("{}: {} messages (last: {})", sender.handle, sender.message_count, sender.last_message_date);
            if let Some(ref text) = sender.sample_text {
                let preview = if text.len() > 60 {
                    format!("{}...", &text[..60])
                } else {
                    text.clone()
                };
                println!("  Sample: {}", preview);
            }
        }
    }

    Ok(())
}

/// Get scheduled messages (pending sends).
///
/// Note: Scheduled messages are not available in the Messages.db schema.
/// macOS Messages.app stores scheduled messages in memory or a separate
/// system location not accessible via the chat.db database.
pub fn scheduled(json: bool) -> Result<()> {
    if json {
        println!("{{\"scheduled_messages\": [], \"note\": \"Scheduled messages are not available in Messages.db schema\"}}");
    } else {
        println!("Scheduled Messages:");
        println!("{:-<60}", "");
        println!("No scheduled messages available.");
        println!();
        println!("Note: Scheduled messages are not stored in the Messages.db");
        println!("database and cannot be queried through this CLI.");
    }
    Ok(())
}

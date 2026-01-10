//! Group commands: groups, group-messages.
//!
//! CHANGELOG:
//! - 01/10/2026 - Initial stub implementation (Claude)
//! - 01/10/2026 - Implemented list groups command (Claude)
//! - 01/10/2026 - Implemented group messages command (Claude)

use anyhow::Result;
use rusqlite;
use serde::Serialize;

use crate::db::{blob_parser, connection::open_db, queries};

#[derive(Debug, Serialize)]
struct GroupChat {
    group_id: String,
    display_name: Option<String>,
    participants: Vec<String>,
    participant_count: usize,
    last_message_date: Option<String>,
    message_count: i64,
}

#[derive(Debug, Serialize)]
struct GroupMessage {
    message_id: i64,
    guid: String,
    text: String,
    is_from_me: bool,
    date: String,
    sender_handle: Option<String>,
    group_name: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    group_id: Option<String>,
}

/// List all group chats.
pub fn list(limit: u32, json: bool) -> Result<()> {
    let conn = open_db()?;

    // Query group chats
    let mut stmt = conn.prepare(queries::LIST_GROUPS)?;
    let chat_rows = stmt.query_map([limit as i64], |row: &rusqlite::Row| {
        Ok((
            row.get::<_, i64>(0)?,        // ROWID
            row.get::<_, String>(1)?,     // chat_identifier
            row.get::<_, Option<String>>(2)?, // display_name
            row.get::<_, Option<i64>>(3)?,    // last_date
            row.get::<_, i64>(4)?,        // msg_count
        ))
    })?;

    let mut groups = Vec::new();

    for row_result in chat_rows {
        let (chat_rowid, chat_identifier, display_name, last_date_cocoa, msg_count): (i64, String, Option<String>, Option<i64>, i64) = row_result?;

        // Get participants for this chat
        let mut participants_stmt = conn.prepare(queries::GROUP_PARTICIPANTS)?;
        let participant_rows = participants_stmt.query_map([chat_rowid], |row: &rusqlite::Row| {
            row.get::<_, String>(0)
        })?;

        let participants: Vec<String> = participant_rows
            .filter_map(|r: rusqlite::Result<String>| r.ok())
            .collect();

        // Only include if it has multiple participants (group chat)
        if participants.len() < 2 {
            continue;
        }

        // Convert Cocoa timestamp to ISO string
        let last_message_date = last_date_cocoa.map(|cocoa_ns| {
            let unix_ts = queries::cocoa_to_unix(cocoa_ns);
            // Convert to ISO 8601 string
            use std::time::{UNIX_EPOCH, Duration};
            let system_time = UNIX_EPOCH + Duration::from_secs(unix_ts as u64);
            let datetime: chrono::DateTime<chrono::Utc> = system_time.into();
            datetime.to_rfc3339()
        });

        groups.push(GroupChat {
            group_id: chat_identifier,
            display_name,
            participants: participants.clone(),
            participant_count: participants.len(),
            last_message_date,
            message_count: msg_count,
        });
    }

    // Output
    if json {
        println!("{}", serde_json::to_string_pretty(&groups)?);
    } else {
        if groups.is_empty() {
            println!("No group chats found.");
            return Ok(());
        }

        println!("Group Chats ({}):", groups.len());
        println!("{:-<60}", "");
        for g in &groups {
            let name = g.display_name.as_deref().unwrap_or(&g.group_id);
            println!("{} ({} members, {} messages)", name, g.participant_count, g.message_count);
            println!("  ID: {}", g.group_id);
            if let Some(ref date) = g.last_message_date {
                println!("  Last message: {}", date);
            }
            println!();
        }
    }

    Ok(())
}

/// Get messages from a group chat.
pub fn messages(group_id: Option<&str>, participant: Option<&str>, limit: u32, json: bool) -> Result<()> {
    let conn = open_db()?;

    let messages: Vec<GroupMessage> = if let Some(gid) = group_id {
        // Query by group_id
        let mut stmt = conn.prepare(queries::GROUP_MESSAGES)?;
        let msg_rows = stmt.query_map([gid, limit.to_string().as_str()], |row: &rusqlite::Row| {
            let message_id: i64 = row.get(0)?;
            let guid: String = row.get(1)?;
            let text_col: Option<String> = row.get(2)?;
            let blob_col: Option<Vec<u8>> = row.get(3)?;
            let is_from_me: bool = row.get(4)?;
            let date_cocoa: i64 = row.get(5)?;
            let sender_handle: Option<String> = row.get(6)?;
            let group_name: Option<String> = row.get(7)?;

            // Extract text from blob or use text column
            let text = if let Some(blob) = blob_col {
                blob_parser::extract_text_from_blob(&blob)
                    .ok()
                    .flatten()
                    .or(text_col)
                    .unwrap_or_else(|| "[message content not available]".to_string())
            } else {
                text_col.unwrap_or_else(|| "[message content not available]".to_string())
            };

            // Convert Cocoa timestamp to ISO string
            let unix_ts = queries::cocoa_to_unix(date_cocoa);
            use std::time::{UNIX_EPOCH, Duration};
            let system_time = UNIX_EPOCH + Duration::from_secs(unix_ts as u64);
            let datetime: chrono::DateTime<chrono::Utc> = system_time.into();

            Ok(GroupMessage {
                message_id,
                guid,
                text,
                is_from_me,
                date: datetime.to_rfc3339(),
                sender_handle,
                group_name,
                group_id: None,
            })
        })?;

        msg_rows.filter_map(|r: rusqlite::Result<GroupMessage>| r.ok()).collect()
    } else if let Some(participant) = participant {
        // Query by participant
        let mut stmt = conn.prepare(queries::GROUP_MESSAGES_BY_PARTICIPANT)?;
        let msg_rows = stmt.query_map([participant, limit.to_string().as_str()], |row: &rusqlite::Row| {
            let message_id: i64 = row.get(0)?;
            let guid: String = row.get(1)?;
            let text_col: Option<String> = row.get(2)?;
            let blob_col: Option<Vec<u8>> = row.get(3)?;
            let is_from_me: bool = row.get(4)?;
            let date_cocoa: i64 = row.get(5)?;
            let sender_handle: Option<String> = row.get(6)?;
            let group_name: Option<String> = row.get(7)?;
            let group_id: String = row.get(8)?;

            // Extract text from blob or use text column
            let text = if let Some(blob) = blob_col {
                blob_parser::extract_text_from_blob(&blob)
                    .ok()
                    .flatten()
                    .or(text_col)
                    .unwrap_or_else(|| "[message content not available]".to_string())
            } else {
                text_col.unwrap_or_else(|| "[message content not available]".to_string())
            };

            // Convert Cocoa timestamp to ISO string
            let unix_ts = queries::cocoa_to_unix(date_cocoa);
            use std::time::{UNIX_EPOCH, Duration};
            let system_time = UNIX_EPOCH + Duration::from_secs(unix_ts as u64);
            let datetime: chrono::DateTime<chrono::Utc> = system_time.into();

            Ok(GroupMessage {
                message_id,
                guid,
                text,
                is_from_me,
                date: datetime.to_rfc3339(),
                sender_handle,
                group_name,
                group_id: Some(group_id),
            })
        })?;

        msg_rows.filter_map(|r: rusqlite::Result<GroupMessage>| r.ok()).collect()
    } else {
        return Err(anyhow::anyhow!("Either group_id or participant must be specified"));
    };

    // Output
    if json {
        println!("{}", serde_json::to_string_pretty(&messages)?);
    } else {
        if messages.is_empty() {
            println!("No group messages found.");
            return Ok(());
        }

        println!("Group Messages ({}):", messages.len());
        println!("{:-<80}", "");
        for msg in &messages {
            let sender = if msg.is_from_me {
                "Me".to_string()
            } else {
                msg.sender_handle.as_deref().unwrap_or("Unknown").to_string()
            };
            println!("[{}] {}: {}", msg.date, sender, msg.text);
            if let Some(ref gid) = msg.group_id {
                println!("  Group: {} ({})", msg.group_name.as_deref().unwrap_or(""), gid);
            }
        }
    }

    Ok(())
}

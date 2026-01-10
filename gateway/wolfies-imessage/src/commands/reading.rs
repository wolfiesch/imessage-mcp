//! Reading commands: find, messages, recent, unread, text-search, bundle, etc.
//!
//! CHANGELOG:
//! - 01/10/2026 - Implemented recent command with actual DB queries (Claude)
//! - 01/10/2026 - Initial stub implementation (Claude)

use crate::db::{blob_parser, connection, queries};
use crate::output::OutputControls;
use anyhow::{Context, Result};
use chrono::{DateTime, TimeZone, Utc};
use serde::Serialize;
use serde_json::json;

/// Message struct for serialization.
#[derive(Debug, Serialize)]
pub struct Message {
    pub text: String,
    pub date: Option<String>,
    pub is_from_me: bool,
    pub phone: String,
    pub is_group_chat: bool,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub group_id: Option<String>,
}

/// Convert Cocoa timestamp (nanoseconds since 2001-01-01) to ISO string.
fn cocoa_to_iso(cocoa_ns: i64) -> Option<String> {
    if cocoa_ns == 0 {
        return None;
    }
    let unix_secs = queries::cocoa_to_unix(cocoa_ns);
    Utc.timestamp_opt(unix_secs, 0)
        .single()
        .map(|dt: DateTime<Utc>| dt.to_rfc3339())
}

/// Check if a chat identifier indicates a group chat.
fn is_group_chat_identifier(chat_id: Option<&str>) -> bool {
    match chat_id {
        None => false,
        Some(id) => {
            // Group chats start with 'chat' followed by digits
            if id.starts_with("chat") && id[4..].chars().all(|c| c.is_ascii_digit()) {
                return true;
            }
            // Or contain comma-separated handles
            id.contains(',')
        }
    }
}

/// Extract message text from text column or attributedBody blob.
fn get_message_text(text: Option<String>, attributed_body: Option<Vec<u8>>) -> String {
    if let Some(t) = text {
        if !t.is_empty() {
            return t;
        }
    }

    if let Some(blob) = attributed_body {
        if let Ok(Some(extracted)) = blob_parser::extract_text_from_blob(&blob) {
            return extracted;
        }
    }

    "[message content not available]".to_string()
}

/// Get recent conversations across all contacts.
pub fn recent(limit: u32, output: &OutputControls) -> Result<()> {
    let conn = connection::open_db().context("Failed to open Messages database")?;

    let mut stmt = conn
        .prepare(
            r#"
            SELECT
                message.text,
                message.attributedBody,
                message.date,
                message.is_from_me,
                handle.id,
                message.cache_roomnames
            FROM message
            LEFT JOIN handle ON message.handle_id = handle.ROWID
            ORDER BY message.date DESC
            LIMIT ?1
            "#,
        )
        .context("Failed to prepare query")?;

    let rows = stmt
        .query_map([limit], |row| {
            Ok((
                row.get::<_, Option<String>>(0)?,   // text
                row.get::<_, Option<Vec<u8>>>(1)?,  // attributedBody
                row.get::<_, i64>(2)?,              // date
                row.get::<_, i32>(3)?,              // is_from_me
                row.get::<_, Option<String>>(4)?,   // handle.id
                row.get::<_, Option<String>>(5)?,   // cache_roomnames
            ))
        })
        .context("Failed to execute query")?;

    let mut messages: Vec<Message> = Vec::new();

    for row_result in rows {
        let (text, attributed_body, date_cocoa, is_from_me, handle_id, cache_roomnames) =
            row_result.context("Failed to read row")?;

        // Extract message text
        let message_text = if let Some(t) = text {
            if !t.is_empty() {
                t
            } else if let Some(blob) = attributed_body {
                blob_parser::extract_text_from_blob(&blob)
                    .ok()
                    .flatten()
                    .unwrap_or_else(|| "[message content not available]".to_string())
            } else {
                "[message content not available]".to_string()
            }
        } else if let Some(blob) = attributed_body {
            blob_parser::extract_text_from_blob(&blob)
                .ok()
                .flatten()
                .unwrap_or_else(|| "[message content not available]".to_string())
        } else {
            "[message content not available]".to_string()
        };

        let is_group = is_group_chat_identifier(cache_roomnames.as_deref());

        messages.push(Message {
            text: message_text,
            date: cocoa_to_iso(date_cocoa),
            is_from_me: is_from_me != 0,
            phone: handle_id.unwrap_or_else(|| "unknown".to_string()),
            is_group_chat: is_group,
            group_id: if is_group { cache_roomnames } else { None },
        });
    }

    if output.json {
        output.print(&messages);
    } else {
        if messages.is_empty() {
            println!("No recent conversations found.");
            return Ok(());
        }

        println!("Recent Conversations ({} messages):", messages.len());
        println!("{}", "-".repeat(60));

        for msg in &messages {
            let sender = if msg.is_from_me { "Me" } else { &msg.phone };
            let text_preview: String = msg.text.chars().take(80).collect();
            let date = msg.date.as_deref().unwrap_or("");
            println!("[{}] {}: {}", date, sender, text_preview);
        }
    }

    Ok(())
}

/// Find messages with a contact (keyword search).
pub fn find(
    contact: &str,
    query: Option<&str>,
    limit: u32,
    output: &OutputControls,
) -> Result<()> {
    use crate::contacts::manager::ContactsManager;

    let conn = connection::open_db().context("Failed to open Messages database")?;

    // Load contacts for name resolution
    let contacts = ContactsManager::load_default().unwrap_or_else(|_| ContactsManager::empty());

    // Resolve contact to phone number
    let phone = match contacts.resolve_to_phone(contact) {
        Some(p) => p,
        None => {
            // If no contact match, try using input directly as phone pattern
            contact.to_string()
        }
    };

    // Build query - search messages with this contact, optionally filtered by text
    let sql = match query {
        Some(_) => r#"
            SELECT
                message.text,
                message.attributedBody,
                message.date,
                message.is_from_me,
                handle.id,
                message.cache_roomnames
            FROM message
            JOIN handle ON message.handle_id = handle.ROWID
            WHERE handle.id LIKE ?1
              AND (message.text LIKE ?2 OR message.attributedBody IS NOT NULL)
            ORDER BY message.date DESC
            LIMIT ?3
        "#,
        None => r#"
            SELECT
                message.text,
                message.attributedBody,
                message.date,
                message.is_from_me,
                handle.id,
                message.cache_roomnames
            FROM message
            JOIN handle ON message.handle_id = handle.ROWID
            WHERE handle.id LIKE ?1
            ORDER BY message.date DESC
            LIMIT ?3
        "#,
    };

    let mut stmt = conn.prepare(sql).context("Failed to prepare query")?;

    // Build parameters
    let phone_pattern = format!("%{}%", phone.chars().filter(|c| c.is_ascii_digit()).collect::<String>());
    let query_pattern = query.map(|q| format!("%{}%", q)).unwrap_or_default();

    let rows: Vec<_> = if query.is_some() {
        stmt.query_map(
            rusqlite::params![phone_pattern, query_pattern, limit],
            |row| {
                Ok((
                    row.get::<_, Option<String>>(0)?,
                    row.get::<_, Option<Vec<u8>>>(1)?,
                    row.get::<_, i64>(2)?,
                    row.get::<_, i32>(3)?,
                    row.get::<_, Option<String>>(4)?,
                    row.get::<_, Option<String>>(5)?,
                ))
            },
        )?
        .collect()
    } else {
        stmt.query_map(
            rusqlite::params![phone_pattern, "", limit],
            |row| {
                Ok((
                    row.get::<_, Option<String>>(0)?,
                    row.get::<_, Option<Vec<u8>>>(1)?,
                    row.get::<_, i64>(2)?,
                    row.get::<_, i32>(3)?,
                    row.get::<_, Option<String>>(4)?,
                    row.get::<_, Option<String>>(5)?,
                ))
            },
        )?
        .collect()
    };

    let mut messages: Vec<Message> = Vec::new();

    for row_result in rows {
        let (text, attributed_body, date_cocoa, is_from_me, handle_id, cache_roomnames) =
            row_result.context("Failed to read row")?;

        let message_text = get_message_text(text, attributed_body);

        // Filter by query if provided
        if let Some(q) = query {
            if !message_text.to_lowercase().contains(&q.to_lowercase()) {
                continue;
            }
        }

        let is_group = is_group_chat_identifier(cache_roomnames.as_deref());

        messages.push(Message {
            text: message_text,
            date: cocoa_to_iso(date_cocoa),
            is_from_me: is_from_me != 0,
            phone: handle_id.unwrap_or_else(|| "unknown".to_string()),
            is_group_chat: is_group,
            group_id: if is_group { cache_roomnames } else { None },
        });
    }

    if output.json {
        output.print(&messages);
    } else {
        if messages.is_empty() {
            println!("No messages found for '{}'{}", contact,
                query.map(|q| format!(" matching '{}'", q)).unwrap_or_default());
            return Ok(());
        }

        println!("Messages with '{}' ({} found):", contact, messages.len());
        println!("{}", "-".repeat(60));

        for msg in &messages {
            let sender = if msg.is_from_me { "Me" } else { &msg.phone };
            let text_preview: String = msg.text.chars().take(80).collect();
            let date = msg.date.as_deref().unwrap_or("");
            println!("[{}] {}: {}", date, sender, text_preview);
        }
    }

    Ok(())
}

/// Get messages with a specific contact.
pub fn messages(contact: &str, limit: u32, output: &OutputControls) -> Result<()> {
    // Delegate to find with no query
    find(contact, None, limit, output)
}

/// Get unread messages.
pub fn unread(limit: u32, output: &OutputControls) -> Result<()> {
    let conn = connection::open_db().context("Failed to open Messages database")?;

    let mut stmt = conn
        .prepare(
            r#"
            SELECT
                message.text,
                message.attributedBody,
                message.date,
                message.is_from_me,
                handle.id,
                message.cache_roomnames
            FROM message
            LEFT JOIN handle ON message.handle_id = handle.ROWID
            WHERE message.is_from_me = 0
              AND message.date_read = 0
              AND message.is_read = 0
            ORDER BY message.date DESC
            LIMIT ?1
            "#,
        )
        .context("Failed to prepare query")?;

    let rows = stmt
        .query_map([limit], |row| {
            Ok((
                row.get::<_, Option<String>>(0)?,
                row.get::<_, Option<Vec<u8>>>(1)?,
                row.get::<_, i64>(2)?,
                row.get::<_, i32>(3)?,
                row.get::<_, Option<String>>(4)?,
                row.get::<_, Option<String>>(5)?,
            ))
        })
        .context("Failed to execute query")?;

    let mut messages: Vec<Message> = Vec::new();

    for row_result in rows {
        let (text, attributed_body, date_cocoa, is_from_me, handle_id, cache_roomnames) =
            row_result.context("Failed to read row")?;

        let message_text = text.filter(|t| !t.is_empty()).unwrap_or_else(|| {
            attributed_body
                .as_ref()
                .and_then(|blob| blob_parser::extract_text_from_blob(blob).ok().flatten())
                .unwrap_or_else(|| "[message content not available]".to_string())
        });

        let is_group = is_group_chat_identifier(cache_roomnames.as_deref());

        messages.push(Message {
            text: message_text,
            date: cocoa_to_iso(date_cocoa),
            is_from_me: is_from_me != 0,
            phone: handle_id.unwrap_or_else(|| "unknown".to_string()),
            is_group_chat: is_group,
            group_id: if is_group { cache_roomnames } else { None },
        });
    }

    if output.json {
        output.print(&messages);
    } else {
        if messages.is_empty() {
            println!("No unread messages.");
            return Ok(());
        }

        println!("Unread Messages ({}):", messages.len());
        println!("{}", "-".repeat(60));

        for msg in &messages {
            let text_preview: String = msg.text.chars().take(150).collect();
            println!("{}: {}", msg.phone, text_preview);
        }
    }

    Ok(())
}

/// Fast text search across all messages.
pub fn text_search(
    query: &str,
    _contact: Option<&str>,
    limit: u32,
    _days: Option<u32>,
    _since: Option<&str>,
    output: &OutputControls,
) -> Result<()> {
    let conn = connection::open_db().context("Failed to open Messages database")?;

    let mut stmt = conn
        .prepare(
            r#"
            SELECT
                message.text,
                message.attributedBody,
                message.date,
                message.is_from_me,
                handle.id,
                message.cache_roomnames
            FROM message
            LEFT JOIN handle ON message.handle_id = handle.ROWID
            WHERE message.text LIKE '%' || ?1 || '%'
            ORDER BY message.date DESC
            LIMIT ?2
            "#,
        )
        .context("Failed to prepare query")?;

    let rows = stmt
        .query_map(rusqlite::params![query, limit], |row| {
            Ok((
                row.get::<_, Option<String>>(0)?,
                row.get::<_, Option<Vec<u8>>>(1)?,
                row.get::<_, i64>(2)?,
                row.get::<_, i32>(3)?,
                row.get::<_, Option<String>>(4)?,
                row.get::<_, Option<String>>(5)?,
            ))
        })
        .context("Failed to execute query")?;

    let mut messages: Vec<Message> = Vec::new();

    for row_result in rows {
        let (text, attributed_body, date_cocoa, is_from_me, handle_id, cache_roomnames) =
            row_result.context("Failed to read row")?;

        let message_text = text.filter(|t| !t.is_empty()).unwrap_or_else(|| {
            attributed_body
                .as_ref()
                .and_then(|blob| blob_parser::extract_text_from_blob(blob).ok().flatten())
                .unwrap_or_else(|| "[message content not available]".to_string())
        });

        let is_group = is_group_chat_identifier(cache_roomnames.as_deref());

        messages.push(Message {
            text: message_text,
            date: cocoa_to_iso(date_cocoa),
            is_from_me: is_from_me != 0,
            phone: handle_id.unwrap_or_else(|| "unknown".to_string()),
            is_group_chat: is_group,
            group_id: if is_group { cache_roomnames } else { None },
        });
    }

    if output.json {
        output.print(&messages);
    } else {
        if messages.is_empty() {
            println!("No matches found for: \"{}\"", query);
            return Ok(());
        }

        println!("Matches ({}) for: \"{}\"", messages.len(), query);
        println!("{}", "-".repeat(60));

        for msg in &messages {
            let sender = if msg.is_from_me { "Me" } else { &msg.phone };
            let text_preview: String = msg.text.chars().take(100).collect();
            println!("[{}] {}: {}", msg.date.as_deref().unwrap_or(""), sender, text_preview);
        }
    }

    Ok(())
}

/// Run a canonical LLM workload bundle.
#[allow(clippy::too_many_arguments)]
pub fn bundle(
    contact: Option<&str>,
    query: Option<&str>,
    _days: Option<u32>,
    _since: Option<&str>,
    unread_limit: u32,
    recent_limit: u32,
    _search_limit: u32,
    _messages_limit: u32,
    _search_scoped_to_contact: bool,
    include: Option<&str>,
    output: &OutputControls,
) -> Result<()> {
    // Parse include sections
    let sections: Vec<&str> = include
        .map(|s| s.split(',').map(|p| p.trim()).collect())
        .unwrap_or_else(|| vec!["meta", "unread_count", "unread_messages", "recent"]);

    let mut bundle_result = serde_json::Map::new();

    // Meta section
    if sections.contains(&"meta") {
        bundle_result.insert(
            "meta".to_string(),
            json!({
                "version": "1.0",
                "timestamp": Utc::now().to_rfc3339(),
            }),
        );
    }

    // Unread count
    if sections.contains(&"unread_count") {
        let conn = connection::open_db()?;
        let count: i64 = conn.query_row(
            "SELECT COUNT(*) FROM message WHERE is_from_me = 0 AND date_read = 0 AND is_read = 0",
            [],
            |row| row.get(0),
        )?;
        bundle_result.insert("unread_count".to_string(), json!(count));
    }

    // Recent messages
    if sections.contains(&"recent") {
        let conn = connection::open_db()?;
        let mut stmt = conn.prepare(
            r#"
            SELECT message.text, message.date, message.is_from_me, handle.id, message.cache_roomnames
            FROM message
            LEFT JOIN handle ON message.handle_id = handle.ROWID
            ORDER BY message.date DESC
            LIMIT ?1
            "#,
        )?;

        let rows: Vec<serde_json::Value> = stmt
            .query_map([recent_limit], |row| {
                Ok(json!({
                    "text": row.get::<_, Option<String>>(0)?.unwrap_or_default(),
                    "date": cocoa_to_iso(row.get::<_, i64>(1)?),
                    "is_from_me": row.get::<_, i32>(2)? != 0,
                    "phone": row.get::<_, Option<String>>(3)?.unwrap_or_else(|| "unknown".to_string()),
                }))
            })?
            .filter_map(|r| r.ok())
            .collect();

        bundle_result.insert("recent".to_string(), json!(rows));
    }

    // Unread messages
    if sections.contains(&"unread_messages") {
        let conn = connection::open_db()?;
        let mut stmt = conn.prepare(
            r#"
            SELECT message.text, message.date, message.is_from_me, handle.id
            FROM message
            LEFT JOIN handle ON message.handle_id = handle.ROWID
            WHERE message.is_from_me = 0 AND message.date_read = 0 AND message.is_read = 0
            ORDER BY message.date DESC
            LIMIT ?1
            "#,
        )?;

        let rows: Vec<serde_json::Value> = stmt
            .query_map([unread_limit], |row| {
                Ok(json!({
                    "text": row.get::<_, Option<String>>(0)?.unwrap_or_default(),
                    "date": cocoa_to_iso(row.get::<_, i64>(1)?),
                    "is_from_me": row.get::<_, i32>(2)? != 0,
                    "phone": row.get::<_, Option<String>>(3)?.unwrap_or_else(|| "unknown".to_string()),
                }))
            })?
            .filter_map(|r| r.ok())
            .collect();

        bundle_result.insert("unread_messages".to_string(), json!(rows));
    }

    // Search section
    if sections.contains(&"search") {
        if let Some(q) = query {
            let conn = connection::open_db()?;
            let mut stmt = conn.prepare(
                r#"
                SELECT message.text, message.date, message.is_from_me, handle.id
                FROM message
                LEFT JOIN handle ON message.handle_id = handle.ROWID
                WHERE message.text LIKE '%' || ?1 || '%'
                ORDER BY message.date DESC
                LIMIT 20
                "#,
            )?;

            let rows: Vec<serde_json::Value> = stmt
                .query_map([q], |row| {
                    Ok(json!({
                        "text": row.get::<_, Option<String>>(0)?.unwrap_or_default(),
                        "date": cocoa_to_iso(row.get::<_, i64>(1)?),
                        "is_from_me": row.get::<_, i32>(2)? != 0,
                        "phone": row.get::<_, Option<String>>(3)?.unwrap_or_else(|| "unknown".to_string()),
                    }))
                })?
                .filter_map(|r| r.ok())
                .collect();

            bundle_result.insert("search".to_string(), json!(rows));
        }
    }

    // Contact-specific messages
    if sections.contains(&"contact_messages") {
        if let Some(_c) = contact {
            // [*INCOMPLETE*] Need contacts manager to resolve name → phone
            bundle_result.insert("contact_messages".to_string(), json!([]));
        }
    }

    if output.json {
        output.print(&bundle_result);
    } else {
        println!("{}", serde_json::to_string_pretty(&bundle_result)?);
    }

    Ok(())
}

/// Get attachments (photos, videos, files).
pub fn attachments(
    _contact: Option<&str>,
    _mime_type: Option<&str>,
    limit: u32,
    json_out: bool,
) -> Result<()> {
    let conn = connection::open_db()?;

    let mut stmt = conn.prepare(
        r#"
        SELECT
            attachment.filename,
            attachment.mime_type,
            attachment.total_bytes,
            attachment.transfer_name,
            message.date
        FROM attachment
        JOIN message_attachment_join ON attachment.ROWID = message_attachment_join.attachment_id
        JOIN message ON message_attachment_join.message_id = message.ROWID
        ORDER BY message.date DESC
        LIMIT ?1
        "#,
    )?;

    let attachments: Vec<serde_json::Value> = stmt
        .query_map([limit], |row| {
            Ok(json!({
                "filename": row.get::<_, Option<String>>(0)?,
                "mime_type": row.get::<_, Option<String>>(1)?,
                "total_bytes": row.get::<_, Option<i64>>(2)?,
                "transfer_name": row.get::<_, Option<String>>(3)?,
                "date": cocoa_to_iso(row.get::<_, i64>(4)?),
            }))
        })?
        .filter_map(|r| r.ok())
        .collect();

    if json_out {
        println!("{}", serde_json::to_string(&attachments)?);
    } else {
        if attachments.is_empty() {
            println!("No attachments found.");
            return Ok(());
        }

        println!("Attachments ({}):", attachments.len());
        println!("{}", "-".repeat(60));
        for a in &attachments {
            let name = a["filename"].as_str().or(a["transfer_name"].as_str()).unwrap_or("Unknown");
            let mime = a["mime_type"].as_str().unwrap_or("unknown");
            let size = a["total_bytes"].as_i64().unwrap_or(0);
            let size_str = if size > 0 {
                format!("{:.1}KB", size as f64 / 1024.0)
            } else {
                "N/A".to_string()
            };
            println!("{} ({}, {})", name, mime, size_str);
        }
    }

    Ok(())
}

/// Get reactions (tapbacks) from messages.
pub fn reactions(_contact: Option<&str>, limit: u32, json_out: bool) -> Result<()> {
    let conn = connection::open_db()?;

    // Reactions have associated_message_guid and associated_message_type > 1999
    let mut stmt = conn.prepare(
        r#"
        SELECT
            message.text,
            message.associated_message_guid,
            message.associated_message_type,
            message.date,
            message.is_from_me,
            handle.id
        FROM message
        LEFT JOIN handle ON message.handle_id = handle.ROWID
        WHERE message.associated_message_type >= 2000
          AND message.associated_message_type < 3000
        ORDER BY message.date DESC
        LIMIT ?1
        "#,
    )?;

    let reactions: Vec<serde_json::Value> = stmt
        .query_map([limit], |row| {
            let reaction_type = row.get::<_, i32>(2)?;
            let emoji = match reaction_type {
                2000 => "❤️",
                2001 => "👍",
                2002 => "👎",
                2003 => "😂",
                2004 => "‼️",
                2005 => "❓",
                _ => "?",
            };
            Ok(json!({
                "reaction_emoji": emoji,
                "reaction_type": reaction_type,
                "associated_guid": row.get::<_, Option<String>>(1)?,
                "date": cocoa_to_iso(row.get::<_, i64>(3)?),
                "is_from_me": row.get::<_, i32>(4)? != 0,
                "reactor_handle": row.get::<_, Option<String>>(5)?,
            }))
        })?
        .filter_map(|r| r.ok())
        .collect();

    if json_out {
        println!("{}", serde_json::to_string(&reactions)?);
    } else {
        if reactions.is_empty() {
            println!("No reactions found.");
            return Ok(());
        }

        println!("Reactions ({}):", reactions.len());
        println!("{}", "-".repeat(60));
        for r in &reactions {
            let emoji = r["reaction_emoji"].as_str().unwrap_or("?");
            let reactor = if r["is_from_me"].as_bool().unwrap_or(false) {
                "Me"
            } else {
                r["reactor_handle"].as_str().unwrap_or("Unknown")
            };
            println!("{} by {}", emoji, reactor);
        }
    }

    Ok(())
}

/// Extract URLs shared in conversations.
pub fn links(_contact: Option<&str>, _days: Option<u32>, _all_time: bool, limit: u32, json_out: bool) -> Result<()> {
    let conn = connection::open_db()?;

    // Simple URL extraction from message text using LIKE patterns
    let mut stmt = conn.prepare(
        r#"
        SELECT
            message.text,
            message.date,
            message.is_from_me,
            handle.id
        FROM message
        LEFT JOIN handle ON message.handle_id = handle.ROWID
        WHERE message.text LIKE '%http%'
        ORDER BY message.date DESC
        LIMIT ?1
        "#,
    )?;

    let url_regex = regex::Regex::new(r#"https?://[^\s<>"]+"#).ok();

    let mut links: Vec<serde_json::Value> = Vec::new();

    let rows = stmt.query_map([limit], |row| {
        Ok((
            row.get::<_, Option<String>>(0)?,
            row.get::<_, i64>(1)?,
            row.get::<_, i32>(2)?,
            row.get::<_, Option<String>>(3)?,
        ))
    })?;

    for row_result in rows {
        let (text, date, is_from_me, handle_id) = row_result?;
        if let Some(text) = text {
            if let Some(ref re) = url_regex {
                for url_match in re.find_iter(&text) {
                    links.push(json!({
                        "url": url_match.as_str(),
                        "date": cocoa_to_iso(date),
                        "is_from_me": is_from_me != 0,
                        "sender_handle": handle_id.clone(),
                    }));
                }
            }
        }
    }

    if json_out {
        println!("{}", serde_json::to_string(&links)?);
    } else {
        if links.is_empty() {
            println!("No links found.");
            return Ok(());
        }

        println!("Shared Links ({}):", links.len());
        println!("{}", "-".repeat(60));
        for link in &links {
            println!("{}", link["url"].as_str().unwrap_or(""));
        }
    }

    Ok(())
}

/// Get voice messages with file paths.
pub fn voice(_contact: Option<&str>, limit: u32, json_out: bool) -> Result<()> {
    let conn = connection::open_db()?;

    let mut stmt = conn.prepare(
        r#"
        SELECT
            attachment.filename,
            attachment.total_bytes,
            message.date,
            message.is_from_me,
            handle.id
        FROM attachment
        JOIN message_attachment_join ON attachment.ROWID = message_attachment_join.attachment_id
        JOIN message ON message_attachment_join.message_id = message.ROWID
        LEFT JOIN handle ON message.handle_id = handle.ROWID
        WHERE attachment.mime_type LIKE 'audio/%'
        ORDER BY message.date DESC
        LIMIT ?1
        "#,
    )?;

    let voice_msgs: Vec<serde_json::Value> = stmt
        .query_map([limit], |row| {
            Ok(json!({
                "attachment_path": row.get::<_, Option<String>>(0)?,
                "size_bytes": row.get::<_, Option<i64>>(1)?,
                "date": cocoa_to_iso(row.get::<_, i64>(2)?),
                "is_from_me": row.get::<_, i32>(3)? != 0,
                "sender_handle": row.get::<_, Option<String>>(4)?,
            }))
        })?
        .filter_map(|r| r.ok())
        .collect();

    if json_out {
        println!("{}", serde_json::to_string(&voice_msgs)?);
    } else {
        if voice_msgs.is_empty() {
            println!("No voice messages found.");
            return Ok(());
        }

        println!("Voice Messages ({}):", voice_msgs.len());
        println!("{}", "-".repeat(60));
        for v in &voice_msgs {
            let path = v["attachment_path"].as_str().unwrap_or("N/A");
            println!("{}", path);
        }
    }

    Ok(())
}

/// Get messages in a reply thread.
pub fn thread(guid: &str, limit: u32, json_out: bool) -> Result<()> {
    let conn = connection::open_db()?;

    let mut stmt = conn.prepare(
        r#"
        SELECT
            message.text,
            message.date,
            message.is_from_me,
            handle.id,
            message.thread_originator_guid
        FROM message
        LEFT JOIN handle ON message.handle_id = handle.ROWID
        WHERE message.thread_originator_guid = ?1
           OR message.guid = ?1
        ORDER BY message.date ASC
        LIMIT ?2
        "#,
    )?;

    let thread_msgs: Vec<serde_json::Value> = stmt
        .query_map(rusqlite::params![guid, limit], |row| {
            Ok(json!({
                "text": row.get::<_, Option<String>>(0)?,
                "date": cocoa_to_iso(row.get::<_, i64>(1)?),
                "is_from_me": row.get::<_, i32>(2)? != 0,
                "sender_handle": row.get::<_, Option<String>>(3)?,
                "is_thread_originator": row.get::<_, Option<String>>(4)?.is_none(),
            }))
        })?
        .filter_map(|r| r.ok())
        .collect();

    if json_out {
        println!("{}", serde_json::to_string(&thread_msgs)?);
    } else {
        if thread_msgs.is_empty() {
            println!("No thread messages found.");
            return Ok(());
        }

        println!("Thread Messages ({}):", thread_msgs.len());
        println!("{}", "-".repeat(60));
        for m in &thread_msgs {
            let sender = if m["is_from_me"].as_bool().unwrap_or(false) {
                "Me"
            } else {
                m["sender_handle"].as_str().unwrap_or("Unknown")
            };
            let text = m["text"].as_str().unwrap_or("[media]");
            println!("{}: {}", sender, text);
        }
    }

    Ok(())
}

/// Get conversation formatted for AI summarization.
#[allow(clippy::too_many_arguments)]
pub fn summary(
    _contact: &str,
    _days: Option<u32>,
    _start: Option<&str>,
    _end: Option<&str>,
    _limit: u32,
    _offset: u32,
    _order: &str,
    json_out: bool,
) -> Result<()> {
    // [*INCOMPLETE*] Needs contact resolution
    eprintln!("[TODO] summary: needs contact resolution");
    if json_out {
        println!("{{}}");
    }
    Ok(())
}

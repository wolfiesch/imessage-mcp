//! Analytics commands: analytics, followup.
//!
//! CHANGELOG:
//! - 01/10/2026 - Refactored to use shared db::helpers (Phase 5) (Claude)
//! - 01/10/2026 - Added parallel query execution (Phase 4B) with rayon (Claude)
//! - 01/10/2026 - Added contact caching (Phase 4A) - accepts Arc<ContactsManager> (Claude)
//! - 01/10/2026 - Initial stub implementation (Claude)
//! - 01/10/2026 - Implemented analytics command (Claude)
//! - 01/10/2026 - Implemented follow-up detection command (Claude)

use anyhow::Result;
use rayon::prelude::*;
use serde::Serialize;
use std::sync::Arc;

use crate::contacts::manager::ContactsManager;
use crate::db::{connection::open_db, helpers, queries};

#[derive(Debug, Serialize)]
struct Analytics {
    total_messages: i64,
    sent_count: i64,
    received_count: i64,
    avg_daily_messages: f64,
    busiest_hour: Option<i64>,
    busiest_day: Option<String>,
    top_contacts: Vec<helpers::TopContact>,
    attachment_count: i64,
    reaction_count: i64,
    analysis_period_days: u32,
}

#[derive(Debug, Clone, Serialize)]
struct UnansweredQuestion {
    phone: String,
    contact_name: Option<String>,
    text: String,
    date: String,
    days_ago: i64,
}

#[derive(Debug, Clone, Serialize)]
struct StaleConversation {
    phone: String,
    contact_name: Option<String>,
    last_text: Option<String>,
    last_date: String,
    days_ago: i64,
}

#[derive(Debug, Serialize)]
struct FollowUpReport {
    unanswered_questions: Vec<UnansweredQuestion>,
    stale_conversations: Vec<StaleConversation>,
    total_items: usize,
}

// ============================================================================
// Main analytics command with parallel execution
// ============================================================================

/// Get conversation analytics.
pub fn analytics(contact: Option<&str>, days: u32, json: bool, contacts: &Arc<ContactsManager>) -> Result<()> {
    let cutoff_cocoa = queries::days_ago_cocoa(days);

    // Resolve contact to phone if provided
    let phone = if let Some(contact_name) = contact {
        let contact = contacts.find_by_name(contact_name)
            .ok_or_else(|| anyhow::anyhow!("Contact '{}' not found", contact_name))?;
        Some(contact.phone.clone())
    } else {
        None
    };

    // Execute 6 queries in parallel using rayon
    // Each query opens its own connection (simple approach)
    let phone_ref = phone.as_deref();

    let ((total, sent, received), ((busiest_hour, busiest_day), (top_contacts, (attachment_count, reaction_count)))) = rayon::join(
        || {
            // Query 1: Message counts
            let conn = open_db().expect("Failed to open DB");
            helpers::query_message_counts(&conn, cutoff_cocoa, phone_ref).expect("Query failed")
        },
        || rayon::join(
            || rayon::join(
                || {
                    // Query 2: Busiest hour
                    let conn = open_db().expect("Failed to open DB");
                    helpers::query_busiest_hour(&conn, cutoff_cocoa, phone_ref).expect("Query failed")
                },
                || {
                    // Query 3: Busiest day
                    let conn = open_db().expect("Failed to open DB");
                    helpers::query_busiest_day(&conn, cutoff_cocoa, phone_ref).expect("Query failed")
                }
            ),
            || rayon::join(
                || {
                    // Query 4: Top contacts (only if no phone filter)
                    if phone_ref.is_none() {
                        let conn = open_db().expect("Failed to open DB");
                        helpers::query_top_contacts(&conn, cutoff_cocoa).expect("Query failed")
                    } else {
                        Vec::new()
                    }
                },
                || rayon::join(
                    || {
                        // Query 5: Attachments
                        let conn = open_db().expect("Failed to open DB");
                        helpers::query_attachments(&conn, cutoff_cocoa, phone_ref).expect("Query failed")
                    },
                    || {
                        // Query 6: Reactions
                        let conn = open_db().expect("Failed to open DB");
                        helpers::query_reactions(&conn, cutoff_cocoa, phone_ref).expect("Query failed")
                    }
                )
            )
        )
    );

    // Convert busiest day number to name
    let busiest_day_name = busiest_day.and_then(|d| {
        helpers::day_number_to_name(d).map(|s| s.to_string())
    });

    // Build analytics struct
    let avg_daily = if days > 0 {
        (total as f64) / (days as f64)
    } else {
        0.0
    };

    let analytics = Analytics {
        total_messages: total,
        sent_count: sent,
        received_count: received,
        avg_daily_messages: (avg_daily * 10.0).round() / 10.0, // Round to 1 decimal
        busiest_hour,
        busiest_day: busiest_day_name,
        top_contacts,
        attachment_count,
        reaction_count,
        analysis_period_days: days,
    };

    // Output
    if json {
        println!("{}", serde_json::to_string_pretty(&analytics)?);
    } else {
        println!("Conversation Analytics:");
        println!("{:-<40}", "");
        println!("total_messages: {}", analytics.total_messages);
        println!("sent_count: {}", analytics.sent_count);
        println!("received_count: {}", analytics.received_count);
        println!("avg_daily_messages: {:.1}", analytics.avg_daily_messages);
        if let Some(hour) = analytics.busiest_hour {
            println!("busiest_hour: {}", hour);
        }
        if let Some(ref day) = analytics.busiest_day {
            println!("busiest_day: {}", day);
        }
        if !analytics.top_contacts.is_empty() {
            println!("top_contacts:");
            for tc in &analytics.top_contacts {
                println!("  {}: {} messages", tc.phone, tc.message_count);
            }
        }
        println!("attachment_count: {}", analytics.attachment_count);
        println!("reaction_count: {}", analytics.reaction_count);
        println!("analysis_period_days: {}", analytics.analysis_period_days);
    }

    Ok(())
}

/// Detect messages needing follow-up.
pub fn followup(days: u32, stale: u32, json: bool, contacts: &Arc<ContactsManager>) -> Result<()> {
    let cutoff_cocoa = queries::days_ago_cocoa(days);
    let stale_threshold_ns = (stale as i64) * 24 * 3600 * 1_000_000_000; // Convert days to nanoseconds

    // Helper to calculate days ago from Cocoa timestamp
    let days_ago_from_cocoa = |cocoa_ns: i64| -> i64 {
        use std::time::{SystemTime, UNIX_EPOCH};
        let now = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .expect("Time went backwards")
            .as_secs() as i64;
        let msg_unix = queries::cocoa_to_unix(cocoa_ns);
        (now - msg_unix) / 86400
    };

    // Clone contacts for parallel execution
    let contacts_clone = Arc::clone(contacts);

    // Execute 2 queries in parallel using rayon
    let (unanswered_questions, stale_conversations) = rayon::join(
        || {
            // Query 1: Unanswered questions
            let conn = open_db().expect("Failed to open DB");
            let mut stmt = conn.prepare(queries::FOLLOWUP_UNANSWERED_QUESTIONS)
                .expect("Failed to prepare query");
            let question_rows = stmt.query_map([cutoff_cocoa, stale_threshold_ns], |row: &rusqlite::Row| {
                let _rowid: i64 = row.get(0)?;
                let text: Option<String> = row.get(1)?;
                let date_cocoa: i64 = row.get(2)?;
                let phone: Option<String> = row.get(3)?;

                // Convert Cocoa timestamp to ISO string
                let unix_ts = queries::cocoa_to_unix(date_cocoa);
                use std::time::{UNIX_EPOCH, Duration};
                let system_time = UNIX_EPOCH + Duration::from_secs(unix_ts as u64);
                let datetime: chrono::DateTime<chrono::Utc> = system_time.into();

                Ok((
                    phone.unwrap_or_else(|| "Unknown".to_string()),
                    text.unwrap_or_else(|| "[no text]".to_string()),
                    datetime.to_rfc3339(),
                    days_ago_from_cocoa(date_cocoa),
                ))
            }).expect("Query failed");

            question_rows
                .filter_map(|r: rusqlite::Result<(String, String, String, i64)>| r.ok())
                .map(|(phone, text, date, days_ago)| {
                    let contact_name = contacts.find_by_phone(&phone).map(|c| c.name.clone());
                    UnansweredQuestion {
                        phone,
                        contact_name,
                        text,
                        date,
                        days_ago,
                    }
                })
                .collect::<Vec<_>>()
        },
        || {
            // Query 2: Stale conversations
            let conn = open_db().expect("Failed to open DB");
            let mut stmt = conn.prepare(queries::FOLLOWUP_STALE_CONVERSATIONS)
                .expect("Failed to prepare query");
            let stale_rows = stmt.query_map([cutoff_cocoa, stale_threshold_ns], |row: &rusqlite::Row| {
                let phone: Option<String> = row.get(0)?;
                let last_date_cocoa: i64 = row.get(1)?;
                let last_text: Option<String> = row.get(2)?;
                let _last_from_me: bool = row.get(3)?;

                // Convert Cocoa timestamp to ISO string
                let unix_ts = queries::cocoa_to_unix(last_date_cocoa);
                use std::time::{UNIX_EPOCH, Duration};
                let system_time = UNIX_EPOCH + Duration::from_secs(unix_ts as u64);
                let datetime: chrono::DateTime<chrono::Utc> = system_time.into();

                Ok((
                    phone.unwrap_or_else(|| "Unknown".to_string()),
                    last_text,
                    datetime.to_rfc3339(),
                    days_ago_from_cocoa(last_date_cocoa),
                ))
            }).expect("Query failed");

            stale_rows
                .filter_map(|r: rusqlite::Result<(String, Option<String>, String, i64)>| r.ok())
                .map(|(phone, last_text, last_date, days_ago)| {
                    let contact_name = contacts_clone.find_by_phone(&phone).map(|c| c.name.clone());
                    StaleConversation {
                        phone,
                        contact_name,
                        last_text,
                        last_date,
                        days_ago,
                    }
                })
                .collect::<Vec<_>>()
        }
    );

    let report = FollowUpReport {
        unanswered_questions: unanswered_questions.clone(),
        stale_conversations: stale_conversations.clone(),
        total_items: unanswered_questions.len() + stale_conversations.len(),
    };

    // Output
    if json {
        println!("{}", serde_json::to_string_pretty(&report)?);
    } else {
        println!("Follow-Up Report:");
        println!("{:-<60}", "");
        println!("Total items needing attention: {}", report.total_items);
        println!();

        if !unanswered_questions.is_empty() {
            println!("Unanswered Questions ({}):", unanswered_questions.len());
            println!("{:-<60}", "");
            for q in &unanswered_questions {
                let contact = q.contact_name.as_deref().unwrap_or(&q.phone);
                println!("[{} days ago] {}", q.days_ago, contact);
                let preview = if q.text.len() > 80 {
                    format!("{}...", &q.text[..80])
                } else {
                    q.text.clone()
                };
                println!("  Q: {}", preview);
            }
            println!();
        }

        if !stale_conversations.is_empty() {
            println!("Stale Conversations ({}):", stale_conversations.len());
            println!("{:-<60}", "");
            for s in &stale_conversations {
                let contact = s.contact_name.as_deref().unwrap_or(&s.phone);
                println!("[{} days ago] {}", s.days_ago, contact);
                if let Some(ref text) = s.last_text {
                    let preview = if text.len() > 80 {
                        format!("{}...", &text[..80])
                    } else {
                        text.clone()
                    };
                    println!("  Last: {}", preview);
                }
            }
        }

        if report.total_items == 0 {
            println!("No follow-ups needed. Great job staying on top of messages!");
        }
    }

    Ok(())
}

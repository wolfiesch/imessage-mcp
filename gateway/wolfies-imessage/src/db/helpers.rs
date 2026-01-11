//! Database query helpers - shared between CLI commands and daemon service.
//!
//! These functions accept `&Connection` to work with both CLI (fresh connection)
//! and daemon mode (hot cached connection).
//!
//! CHANGELOG:
//! - 01/10/2026 - Initial extraction from analytics.rs (Phase 5) (Claude)

use anyhow::Result;
use rusqlite::{self, Connection};
use serde::Serialize;

use super::queries;

// ============================================================================
// Data Structures
// ============================================================================

#[derive(Debug, Clone, Serialize)]
pub struct TopContact {
    pub phone: String,
    pub message_count: i64,
}

#[derive(Debug, Clone, Serialize)]
pub struct RecentMessage {
    pub text: Option<String>,
    pub date: String,
    pub is_from_me: bool,
    pub phone: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct UnreadMessage {
    pub text: Option<String>,
    pub date: String,
    pub phone: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct HandleInfo {
    pub handle: String,
    pub message_count: i64,
    pub last_date: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct UnknownSender {
    pub handle: String,
    pub message_count: i64,
    pub last_date: String,
    pub sample_text: Option<String>,
}

#[derive(Debug, Clone, Serialize)]
pub struct UnansweredQuestion {
    pub phone: String,
    pub text: String,
    pub date: String,
    pub days_ago: i64,
}

#[derive(Debug, Clone, Serialize)]
pub struct StaleConversation {
    pub phone: String,
    pub last_text: Option<String>,
    pub last_date: String,
    pub days_ago: i64,
}

// ============================================================================
// Analytics Query Helpers
// ============================================================================

/// Query message counts (total, sent, received).
pub fn query_message_counts(
    conn: &Connection,
    cutoff_cocoa: i64,
    phone: Option<&str>,
) -> Result<(i64, i64, i64)> {
    if let Some(p) = phone {
        let mut stmt = conn.prepare(queries::ANALYTICS_MESSAGE_COUNTS_PHONE)?;
        let params: &[&dyn rusqlite::ToSql] = &[&cutoff_cocoa, &p];
        let row = stmt
            .query_row(params, |row: &rusqlite::Row| {
                Ok((
                    row.get::<_, i64>(0).unwrap_or(0),
                    row.get::<_, i64>(1).unwrap_or(0),
                    row.get::<_, i64>(2).unwrap_or(0),
                ))
            })
            .unwrap_or((0, 0, 0));
        Ok(row)
    } else {
        let mut stmt = conn.prepare(queries::ANALYTICS_MESSAGE_COUNTS)?;
        let row = stmt
            .query_row(&[&cutoff_cocoa], |row: &rusqlite::Row| {
                Ok((
                    row.get::<_, i64>(0).unwrap_or(0),
                    row.get::<_, i64>(1).unwrap_or(0),
                    row.get::<_, i64>(2).unwrap_or(0),
                ))
            })
            .unwrap_or((0, 0, 0));
        Ok(row)
    }
}

/// Query busiest hour of day.
pub fn query_busiest_hour(
    conn: &Connection,
    cutoff_cocoa: i64,
    phone: Option<&str>,
) -> Result<Option<i64>> {
    if let Some(p) = phone {
        let mut stmt = conn.prepare(queries::ANALYTICS_BUSIEST_HOUR_PHONE)?;
        let params: &[&dyn rusqlite::ToSql] = &[&cutoff_cocoa, &p];
        Ok(stmt
            .query_row(params, |row: &rusqlite::Row| row.get::<_, i64>(0))
            .ok())
    } else {
        let mut stmt = conn.prepare(queries::ANALYTICS_BUSIEST_HOUR)?;
        Ok(stmt
            .query_row(&[&cutoff_cocoa], |row: &rusqlite::Row| row.get::<_, i64>(0))
            .ok())
    }
}

/// Query busiest day of week (returns 0-6 for Sunday-Saturday).
pub fn query_busiest_day(
    conn: &Connection,
    cutoff_cocoa: i64,
    phone: Option<&str>,
) -> Result<Option<i64>> {
    if let Some(p) = phone {
        let mut stmt = conn.prepare(queries::ANALYTICS_BUSIEST_DAY_PHONE)?;
        let params: &[&dyn rusqlite::ToSql] = &[&cutoff_cocoa, &p];
        Ok(stmt
            .query_row(params, |row: &rusqlite::Row| row.get::<_, i64>(0))
            .ok())
    } else {
        let mut stmt = conn.prepare(queries::ANALYTICS_BUSIEST_DAY)?;
        Ok(stmt
            .query_row(&[&cutoff_cocoa], |row: &rusqlite::Row| row.get::<_, i64>(0))
            .ok())
    }
}

/// Query top contacts by message volume.
pub fn query_top_contacts(conn: &Connection, cutoff_cocoa: i64) -> Result<Vec<TopContact>> {
    let mut stmt = conn.prepare(queries::ANALYTICS_TOP_CONTACTS)?;
    let rows = stmt.query_map(&[&cutoff_cocoa], |row: &rusqlite::Row| {
        Ok(TopContact {
            phone: row.get(0)?,
            message_count: row.get(1)?,
        })
    })?;
    Ok(rows
        .filter_map(|r: rusqlite::Result<TopContact>| r.ok())
        .collect())
}

/// Query attachment count (optimized - skips attachment table join).
pub fn query_attachments(
    conn: &Connection,
    cutoff_cocoa: i64,
    phone: Option<&str>,
) -> Result<i64> {
    if let Some(p) = phone {
        let mut stmt = conn.prepare(queries::ANALYTICS_ATTACHMENTS_FAST_PHONE)?;
        let params: &[&dyn rusqlite::ToSql] = &[&cutoff_cocoa, &p];
        Ok(stmt
            .query_row(params, |row: &rusqlite::Row| row.get::<_, i64>(0))
            .unwrap_or(0))
    } else {
        let mut stmt = conn.prepare(queries::ANALYTICS_ATTACHMENTS_FAST)?;
        Ok(stmt
            .query_row(&[&cutoff_cocoa], |row: &rusqlite::Row| row.get::<_, i64>(0))
            .unwrap_or(0))
    }
}

/// Query reaction count.
pub fn query_reactions(conn: &Connection, cutoff_cocoa: i64, phone: Option<&str>) -> Result<i64> {
    if let Some(p) = phone {
        let mut stmt = conn.prepare(queries::ANALYTICS_REACTIONS_PHONE)?;
        let params: &[&dyn rusqlite::ToSql] = &[&cutoff_cocoa, &p];
        Ok(stmt
            .query_row(params, |row: &rusqlite::Row| row.get::<_, i64>(0))
            .unwrap_or(0))
    } else {
        let mut stmt = conn.prepare(queries::ANALYTICS_REACTIONS)?;
        Ok(stmt
            .query_row(&[&cutoff_cocoa], |row: &rusqlite::Row| row.get::<_, i64>(0))
            .unwrap_or(0))
    }
}

/// Convert day number (0-6) to day name.
pub fn day_number_to_name(day: i64) -> Option<&'static str> {
    const DAYS: [&str; 7] = [
        "Sunday",
        "Monday",
        "Tuesday",
        "Wednesday",
        "Thursday",
        "Friday",
        "Saturday",
    ];
    if day >= 0 && day < 7 {
        Some(DAYS[day as usize])
    } else {
        None
    }
}

// ============================================================================
// Optimized Combined Analytics (Single Query)
// ============================================================================

/// Combined analytics result - all stats from single query.
/// Includes attachment count (uses cache_has_attachments column).
#[derive(Debug, Clone)]
pub struct CombinedAnalytics {
    pub total: i64,
    pub sent: i64,
    pub received: i64,
    pub reactions: i64,
    pub attachments: i64,
    pub busiest_hour: Option<i64>,
    pub busiest_day: Option<i64>,
}

/// Query all analytics stats in a single optimized query.
/// Combines: message_counts, reactions, attachments, busiest_hour, busiest_day.
/// Reduces from 3 queries to 1 for faster performance.
pub fn query_analytics_combined(
    conn: &Connection,
    cutoff_cocoa: i64,
    phone: Option<&str>,
) -> Result<CombinedAnalytics> {
    if let Some(p) = phone {
        let mut stmt = conn.prepare(queries::ANALYTICS_COMBINED_PHONE)?;
        let params: &[&dyn rusqlite::ToSql] = &[&cutoff_cocoa, &p];
        stmt.query_row(params, |row| {
            Ok(CombinedAnalytics {
                total: row.get::<_, Option<i64>>(0)?.unwrap_or(0),
                sent: row.get::<_, Option<i64>>(1)?.unwrap_or(0),
                received: row.get::<_, Option<i64>>(2)?.unwrap_or(0),
                reactions: row.get::<_, Option<i64>>(3)?.unwrap_or(0),
                attachments: row.get::<_, Option<i64>>(4)?.unwrap_or(0),
                busiest_hour: row.get(5)?,
                busiest_day: row.get(6)?,
            })
        })
        .map_err(|e| anyhow::anyhow!("Combined analytics query failed: {}", e))
    } else {
        let mut stmt = conn.prepare(queries::ANALYTICS_COMBINED)?;
        stmt.query_row([&cutoff_cocoa], |row| {
            Ok(CombinedAnalytics {
                total: row.get::<_, Option<i64>>(0)?.unwrap_or(0),
                sent: row.get::<_, Option<i64>>(1)?.unwrap_or(0),
                received: row.get::<_, Option<i64>>(2)?.unwrap_or(0),
                reactions: row.get::<_, Option<i64>>(3)?.unwrap_or(0),
                attachments: row.get::<_, Option<i64>>(4)?.unwrap_or(0),
                busiest_hour: row.get(5)?,
                busiest_day: row.get(6)?,
            })
        })
        .map_err(|e| anyhow::anyhow!("Combined analytics query failed: {}", e))
    }
}

// ============================================================================
// Reading Query Helpers
// ============================================================================

/// Query recent messages.
pub fn query_recent_messages(
    conn: &Connection,
    cutoff_cocoa: i64,
    limit: u32,
) -> Result<Vec<RecentMessage>> {
    let mut stmt = conn.prepare(queries::RECENT_MESSAGES)?;

    let rows = stmt.query_map([&cutoff_cocoa, &(limit as i64)], |row: &rusqlite::Row| {
        let date_cocoa: i64 = row.get(1)?;
        Ok(RecentMessage {
            text: row.get(0)?,
            date: cocoa_to_iso(date_cocoa),
            is_from_me: row.get::<_, i32>(2)? == 1,
            phone: row.get::<_, Option<String>>(3)?.unwrap_or_else(|| "Unknown".to_string()),
        })
    })?;

    Ok(rows.filter_map(|r| r.ok()).collect())
}

/// Query unread messages.
pub fn query_unread_messages(conn: &Connection, limit: u32) -> Result<Vec<UnreadMessage>> {
    let mut stmt = conn.prepare(queries::UNREAD_MESSAGES)?;

    let rows = stmt.query_map([&(limit as i64)], |row: &rusqlite::Row| {
        let date_cocoa: i64 = row.get(5)?;
        Ok(UnreadMessage {
            text: row.get(2)?,
            date: cocoa_to_iso(date_cocoa),
            phone: row.get::<_, Option<String>>(6)?.unwrap_or_else(|| "Unknown".to_string()),
        })
    })?;

    Ok(rows.filter_map(|r| r.ok()).collect())
}

// ============================================================================
// Discovery Query Helpers
// ============================================================================

/// Query handles (all senders).
pub fn query_handles(
    conn: &Connection,
    cutoff_cocoa: i64,
    limit: u32,
) -> Result<Vec<HandleInfo>> {
    let mut stmt = conn.prepare(queries::DISCOVERY_HANDLES)?;

    let rows = stmt.query_map([&cutoff_cocoa, &(limit as i64)], |row: &rusqlite::Row| {
        let last_date_cocoa: i64 = row.get(2)?;
        Ok(HandleInfo {
            handle: row.get(0)?,
            message_count: row.get(1)?,
            last_date: cocoa_to_iso(last_date_cocoa),
        })
    })?;

    Ok(rows.filter_map(|r| r.ok()).collect())
}

/// Query unknown senders (handles not matched to contacts).
/// Returns all handles; caller should filter against contacts list.
pub fn query_unknown_senders(conn: &Connection, cutoff_cocoa: i64) -> Result<Vec<UnknownSender>> {
    let mut stmt = conn.prepare(queries::DISCOVERY_UNKNOWN)?;

    let rows = stmt.query_map([&cutoff_cocoa], |row: &rusqlite::Row| {
        let last_date_cocoa: i64 = row.get(2)?;
        Ok(UnknownSender {
            handle: row.get(0)?,
            message_count: row.get(1)?,
            last_date: cocoa_to_iso(last_date_cocoa),
            sample_text: row.get(3)?,
        })
    })?;

    Ok(rows.filter_map(|r| r.ok()).collect())
}

// ============================================================================
// Follow-Up Query Helpers
// ============================================================================

/// Query unanswered questions.
pub fn query_unanswered_questions(
    conn: &Connection,
    cutoff_cocoa: i64,
    stale_threshold_ns: i64,
) -> Result<Vec<UnansweredQuestion>> {
    let mut stmt = conn.prepare(queries::FOLLOWUP_UNANSWERED_QUESTIONS)?;

    let rows =
        stmt.query_map([cutoff_cocoa, stale_threshold_ns], |row: &rusqlite::Row| {
            let _rowid: i64 = row.get(0)?;
            let text: Option<String> = row.get(1)?;
            let date_cocoa: i64 = row.get(2)?;
            let phone: Option<String> = row.get(3)?;

            Ok(UnansweredQuestion {
                phone: phone.unwrap_or_else(|| "Unknown".to_string()),
                text: text.unwrap_or_else(|| "[no text]".to_string()),
                date: cocoa_to_iso(date_cocoa),
                days_ago: days_ago_from_cocoa(date_cocoa),
            })
        })?;

    Ok(rows.filter_map(|r| r.ok()).collect())
}

/// Query stale conversations.
pub fn query_stale_conversations(
    conn: &Connection,
    cutoff_cocoa: i64,
    stale_threshold_ns: i64,
) -> Result<Vec<StaleConversation>> {
    let mut stmt = conn.prepare(queries::FOLLOWUP_STALE_CONVERSATIONS)?;

    let rows =
        stmt.query_map([cutoff_cocoa, stale_threshold_ns], |row: &rusqlite::Row| {
            let phone: Option<String> = row.get(0)?;
            let last_date_cocoa: i64 = row.get(1)?;
            let last_text: Option<String> = row.get(2)?;
            let _last_from_me: bool = row.get(3)?;

            Ok(StaleConversation {
                phone: phone.unwrap_or_else(|| "Unknown".to_string()),
                last_text,
                last_date: cocoa_to_iso(last_date_cocoa),
                days_ago: days_ago_from_cocoa(last_date_cocoa),
            })
        })?;

    Ok(rows.filter_map(|r| r.ok()).collect())
}

// ============================================================================
// Utility Functions
// ============================================================================

/// Convert Cocoa timestamp (nanoseconds since 2001-01-01) to ISO 8601 string.
pub fn cocoa_to_iso(cocoa_ns: i64) -> String {
    use std::time::{Duration, UNIX_EPOCH};

    let unix_ts = queries::cocoa_to_unix(cocoa_ns);
    if unix_ts < 0 {
        return "1970-01-01T00:00:00Z".to_string();
    }

    let system_time = UNIX_EPOCH + Duration::from_secs(unix_ts as u64);
    let datetime: chrono::DateTime<chrono::Utc> = system_time.into();
    datetime.to_rfc3339()
}

/// Calculate days ago from Cocoa timestamp.
/// Handles clock adjustments gracefully instead of panicking.
pub fn days_ago_from_cocoa(cocoa_ns: i64) -> i64 {
    use std::time::{SystemTime, UNIX_EPOCH};

    // Handle potential clock adjustment gracefully
    let now = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs() as i64;

    let msg_unix = queries::cocoa_to_unix(cocoa_ns);
    // Ensure non-negative result even if clock is adjusted
    ((now - msg_unix) / 86400).max(0)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_day_number_to_name() {
        assert_eq!(day_number_to_name(0), Some("Sunday"));
        assert_eq!(day_number_to_name(6), Some("Saturday"));
        assert_eq!(day_number_to_name(7), None);
        assert_eq!(day_number_to_name(-1), None);
    }

    #[test]
    fn test_cocoa_to_iso() {
        // Known timestamp: 2025-01-01 00:00:00 UTC
        let cocoa = 757_382_400_000_000_000i64;
        let iso = cocoa_to_iso(cocoa);
        assert!(iso.starts_with("2025-01-01"));
    }
}

//! SQL queries for Messages.db.
//!
//! CHANGELOG:
//! - 01/10/2026 - Initial stub with query constants (Claude)

/// Query to get recent messages from a specific phone number.
pub const MESSAGES_BY_PHONE: &str = r#"
SELECT
    m.ROWID,
    m.guid,
    m.text,
    m.attributedBody,
    m.is_from_me,
    m.date,
    m.date_read,
    m.date_delivered,
    h.id as handle_id,
    c.chat_identifier
FROM message m
LEFT JOIN handle h ON m.handle_id = h.ROWID
LEFT JOIN chat_message_join cmj ON m.ROWID = cmj.message_id
LEFT JOIN chat c ON cmj.chat_id = c.ROWID
WHERE h.id = ?1
ORDER BY m.date DESC
LIMIT ?2
"#;

/// Query to get recent conversations.
pub const RECENT_CONVERSATIONS: &str = r#"
SELECT
    h.id as handle_id,
    MAX(m.date) as last_date,
    m.text,
    m.attributedBody,
    m.is_from_me,
    c.chat_identifier,
    c.display_name
FROM message m
LEFT JOIN handle h ON m.handle_id = h.ROWID
LEFT JOIN chat_message_join cmj ON m.ROWID = cmj.message_id
LEFT JOIN chat c ON cmj.chat_id = c.ROWID
GROUP BY h.id
ORDER BY last_date DESC
LIMIT ?1
"#;

/// Query to get unread messages.
pub const UNREAD_MESSAGES: &str = r#"
SELECT
    m.ROWID,
    m.guid,
    m.text,
    m.attributedBody,
    m.is_from_me,
    m.date,
    h.id as handle_id,
    c.chat_identifier,
    c.display_name
FROM message m
LEFT JOIN handle h ON m.handle_id = h.ROWID
LEFT JOIN chat_message_join cmj ON m.ROWID = cmj.message_id
LEFT JOIN chat c ON cmj.chat_id = c.ROWID
WHERE m.is_from_me = 0
  AND m.date_read = 0
  AND m.is_read = 0
ORDER BY m.date DESC
LIMIT ?1
"#;

/// Query to search messages by text.
pub const TEXT_SEARCH: &str = r#"
SELECT
    m.ROWID,
    m.guid,
    m.text,
    m.attributedBody,
    m.is_from_me,
    m.date,
    h.id as handle_id,
    c.chat_identifier
FROM message m
LEFT JOIN handle h ON m.handle_id = h.ROWID
LEFT JOIN chat_message_join cmj ON m.ROWID = cmj.message_id
LEFT JOIN chat c ON cmj.chat_id = c.ROWID
WHERE m.text LIKE '%' || ?1 || '%'
ORDER BY m.date DESC
LIMIT ?2
"#;

/// Query to list all group chats.
pub const LIST_GROUPS: &str = r#"
SELECT
    c.ROWID,
    c.chat_identifier,
    c.display_name,
    (SELECT MAX(m.date) FROM message m
     JOIN chat_message_join cmj ON m.ROWID = cmj.message_id
     WHERE cmj.chat_id = c.ROWID) as last_date,
    (SELECT COUNT(*) FROM chat_message_join cmj
     WHERE cmj.chat_id = c.ROWID) as msg_count
FROM chat c
WHERE c.chat_identifier LIKE 'chat%'
   OR (c.display_name IS NOT NULL AND c.display_name != '')
ORDER BY last_date DESC
LIMIT ?1
"#;

/// Query to get participants for a specific chat.
pub const GROUP_PARTICIPANTS: &str = r#"
SELECT h.id
FROM handle h
JOIN chat_handle_join chj ON h.ROWID = chj.handle_id
WHERE chj.chat_id = ?1
"#;

/// Query to get messages from a group chat by chat_identifier.
pub const GROUP_MESSAGES: &str = r#"
SELECT
    m.ROWID,
    m.guid,
    m.text,
    m.attributedBody,
    m.is_from_me,
    m.date,
    h.id as sender_handle,
    c.display_name as group_name
FROM message m
JOIN chat_message_join cmj ON m.ROWID = cmj.message_id
JOIN chat c ON cmj.chat_id = c.ROWID
LEFT JOIN handle h ON m.handle_id = h.ROWID
WHERE c.chat_identifier = ?1
ORDER BY m.date DESC
LIMIT ?2
"#;

/// Query to get group messages filtered by participant.
pub const GROUP_MESSAGES_BY_PARTICIPANT: &str = r#"
SELECT
    m.ROWID,
    m.guid,
    m.text,
    m.attributedBody,
    m.is_from_me,
    m.date,
    h.id as sender_handle,
    c.display_name as group_name,
    c.chat_identifier
FROM message m
JOIN chat_message_join cmj ON m.ROWID = cmj.message_id
JOIN chat c ON cmj.chat_id = c.ROWID
LEFT JOIN handle h ON m.handle_id = h.ROWID
WHERE h.id LIKE '%' || ?1 || '%'
  AND (c.chat_identifier LIKE 'chat%' OR c.display_name IS NOT NULL)
ORDER BY m.date DESC
LIMIT ?2
"#;

// ============================================================================
// ANALYTICS QUERIES
// ============================================================================

/// Get message counts (total, sent, received) for analytics.
/// Parameters: ?1 = cutoff_cocoa (date threshold), ?2 = phone filter (optional)
pub const ANALYTICS_MESSAGE_COUNTS: &str = r#"
SELECT
    COUNT(*) as total,
    SUM(CASE WHEN m.is_from_me = 1 THEN 1 ELSE 0 END) as sent,
    SUM(CASE WHEN m.is_from_me = 0 THEN 1 ELSE 0 END) as received
FROM message m
LEFT JOIN handle h ON m.handle_id = h.ROWID
WHERE m.date >= ?1
  AND (m.associated_message_type IS NULL OR m.associated_message_type = 0)
"#;

/// Get message counts with phone filter.
pub const ANALYTICS_MESSAGE_COUNTS_PHONE: &str = r#"
SELECT
    COUNT(*) as total,
    SUM(CASE WHEN m.is_from_me = 1 THEN 1 ELSE 0 END) as sent,
    SUM(CASE WHEN m.is_from_me = 0 THEN 1 ELSE 0 END) as received
FROM message m
LEFT JOIN handle h ON m.handle_id = h.ROWID
WHERE m.date >= ?1
  AND h.id LIKE '%' || ?2 || '%'
  AND (m.associated_message_type IS NULL OR m.associated_message_type = 0)
"#;

/// Get busiest hour of day.
pub const ANALYTICS_BUSIEST_HOUR: &str = r#"
SELECT
    CAST((m.date / 1000000000 / 3600) % 24 AS INTEGER) as hour,
    COUNT(*) as count
FROM message m
LEFT JOIN handle h ON m.handle_id = h.ROWID
WHERE m.date >= ?1
GROUP BY hour
ORDER BY count DESC
LIMIT 1
"#;

/// Get busiest hour with phone filter.
pub const ANALYTICS_BUSIEST_HOUR_PHONE: &str = r#"
SELECT
    CAST((m.date / 1000000000 / 3600) % 24 AS INTEGER) as hour,
    COUNT(*) as count
FROM message m
LEFT JOIN handle h ON m.handle_id = h.ROWID
WHERE m.date >= ?1
  AND h.id LIKE '%' || ?2 || '%'
GROUP BY hour
ORDER BY count DESC
LIMIT 1
"#;

/// Get busiest day of week.
pub const ANALYTICS_BUSIEST_DAY: &str = r#"
SELECT
    CAST((m.date / 1000000000 / 86400 + 1) % 7 AS INTEGER) as dow,
    COUNT(*) as count
FROM message m
LEFT JOIN handle h ON m.handle_id = h.ROWID
WHERE m.date >= ?1
GROUP BY dow
ORDER BY count DESC
LIMIT 1
"#;

/// Get busiest day with phone filter.
pub const ANALYTICS_BUSIEST_DAY_PHONE: &str = r#"
SELECT
    CAST((m.date / 1000000000 / 86400 + 1) % 7 AS INTEGER) as dow,
    COUNT(*) as count
FROM message m
LEFT JOIN handle h ON m.handle_id = h.ROWID
WHERE m.date >= ?1
  AND h.id LIKE '%' || ?2 || '%'
GROUP BY dow
ORDER BY count DESC
LIMIT 1
"#;

/// Get top 10 contacts by message volume.
pub const ANALYTICS_TOP_CONTACTS: &str = r#"
SELECT
    h.id,
    COUNT(*) as msg_count
FROM message m
JOIN handle h ON m.handle_id = h.ROWID
WHERE m.date >= ?1
  AND (m.associated_message_type IS NULL OR m.associated_message_type = 0)
GROUP BY h.id
ORDER BY msg_count DESC
LIMIT 10
"#;

/// Get attachment count.
pub const ANALYTICS_ATTACHMENTS: &str = r#"
SELECT COUNT(DISTINCT a.ROWID)
FROM attachment a
JOIN message_attachment_join maj ON a.ROWID = maj.attachment_id
JOIN message m ON maj.message_id = m.ROWID
LEFT JOIN handle h ON m.handle_id = h.ROWID
WHERE m.date >= ?1
"#;

/// Get attachment count with phone filter.
pub const ANALYTICS_ATTACHMENTS_PHONE: &str = r#"
SELECT COUNT(DISTINCT a.ROWID)
FROM attachment a
JOIN message_attachment_join maj ON a.ROWID = maj.attachment_id
JOIN message m ON maj.message_id = m.ROWID
LEFT JOIN handle h ON m.handle_id = h.ROWID
WHERE m.date >= ?1
  AND h.id LIKE '%' || ?2 || '%'
"#;

/// Get reaction count.
pub const ANALYTICS_REACTIONS: &str = r#"
SELECT COUNT(*)
FROM message m
LEFT JOIN handle h ON m.handle_id = h.ROWID
WHERE m.date >= ?1
  AND m.associated_message_type BETWEEN 2000 AND 3005
"#;

/// Get reaction count with phone filter.
pub const ANALYTICS_REACTIONS_PHONE: &str = r#"
SELECT COUNT(*)
FROM message m
LEFT JOIN handle h ON m.handle_id = h.ROWID
WHERE m.date >= ?1
  AND h.id LIKE '%' || ?2 || '%'
  AND m.associated_message_type BETWEEN 2000 AND 3005
"#;

/// Query all reactions with details.
pub const QUERY_REACTIONS: &str = r#"
SELECT
    m.ROWID,
    m.guid,
    m.text,
    m.associated_message_guid,
    m.associated_message_type,
    m.date,
    h.id as handle_id,
    m.is_from_me
FROM message m
LEFT JOIN handle h ON m.handle_id = h.ROWID
WHERE m.associated_message_type IN (2000, 2001, 2002, 2003, 2004, 2005, 3000, 3001, 3002, 3003, 3004, 3005)
ORDER BY m.date DESC
LIMIT ?1
"#;

/// Query reactions with phone filter.
pub const QUERY_REACTIONS_PHONE: &str = r#"
SELECT
    m.ROWID,
    m.guid,
    m.text,
    m.associated_message_guid,
    m.associated_message_type,
    m.date,
    h.id as handle_id,
    m.is_from_me
FROM message m
LEFT JOIN handle h ON m.handle_id = h.ROWID
WHERE m.associated_message_type IN (2000, 2001, 2002, 2003, 2004, 2005, 3000, 3001, 3002, 3003, 3004, 3005)
  AND h.id LIKE '%' || ?1 || '%'
ORDER BY m.date DESC
LIMIT ?2
"#;

// ============================================================================
// FOLLOW-UP DETECTION QUERIES
// ============================================================================

/// Find unanswered questions from received messages.
/// Parameters: ?1 = cutoff_cocoa (days ago), ?2 = stale_threshold_ns (nanoseconds)
pub const FOLLOWUP_UNANSWERED_QUESTIONS: &str = r#"
SELECT
    m.ROWID,
    m.text,
    m.date,
    h.id as phone
FROM message m
LEFT JOIN handle h ON m.handle_id = h.ROWID
WHERE m.is_from_me = 0
  AND m.date >= ?1
  AND (m.text LIKE '%?%' OR m.text LIKE '%when%' OR m.text LIKE '%what%'
       OR m.text LIKE '%where%' OR m.text LIKE '%how%' OR m.text LIKE '%why%'
       OR m.text LIKE '%can you%' OR m.text LIKE '%could you%')
  AND NOT EXISTS (
    SELECT 1 FROM message m2
    WHERE m2.handle_id = m.handle_id
      AND m2.is_from_me = 1
      AND m2.date > m.date
      AND m2.date < (m.date + ?2)
  )
ORDER BY m.date DESC
LIMIT 50
"#;

/// Find stale conversations (no reply after N days).
/// Parameters: ?1 = cutoff_cocoa (days ago), ?2 = stale_threshold_ns (nanoseconds)
pub const FOLLOWUP_STALE_CONVERSATIONS: &str = r#"
SELECT
    h.id as phone,
    MAX(m.date) as last_date,
    (SELECT m2.text FROM message m2
     WHERE m2.handle_id = h.ROWID
     ORDER BY m2.date DESC LIMIT 1) as last_text,
    (SELECT m2.is_from_me FROM message m2
     WHERE m2.handle_id = h.ROWID
     ORDER BY m2.date DESC LIMIT 1) as last_from_me
FROM message m
LEFT JOIN handle h ON m.handle_id = h.ROWID
WHERE m.date >= ?1
  AND m.is_from_me = 0
GROUP BY h.id
HAVING MAX(m.date) < (strftime('%s', 'now') - 978307200) * 1000000000 - ?2
  AND last_from_me = 0
ORDER BY last_date DESC
LIMIT 50
"#;

// ============================================================================
// DISCOVERY QUERIES
// ============================================================================

/// List all unique handles from recent messages.
pub const DISCOVERY_HANDLES: &str = r#"
SELECT DISTINCT
    h.id as handle,
    COUNT(m.ROWID) as message_count,
    MAX(m.date) as last_message_date
FROM handle h
JOIN message m ON m.handle_id = h.ROWID
WHERE m.date >= ?1
GROUP BY h.id
ORDER BY last_message_date DESC
LIMIT ?2
"#;

/// Find messages from unknown senders (not in contacts).
/// Returns all handles with message counts and sample text.
pub const DISCOVERY_UNKNOWN: &str = r#"
SELECT DISTINCT
    h.id as handle,
    COUNT(m.ROWID) as message_count,
    MAX(m.date) as last_message_date,
    (SELECT m2.text FROM message m2
     WHERE m2.handle_id = h.ROWID AND m2.text IS NOT NULL
     ORDER BY m2.date DESC LIMIT 1) as sample_text
FROM handle h
JOIN message m ON m.handle_id = h.ROWID
WHERE m.date >= ?1
  AND m.is_from_me = 0
GROUP BY h.id
ORDER BY last_message_date DESC
"#;

/// Cocoa epoch offset (2001-01-01 in Unix time).
pub const COCOA_EPOCH_OFFSET: i64 = 978_307_200;

/// Convert Cocoa nanoseconds timestamp to Unix timestamp.
pub fn cocoa_to_unix(cocoa_ns: i64) -> i64 {
    (cocoa_ns / 1_000_000_000) + COCOA_EPOCH_OFFSET
}

/// Calculate Cocoa timestamp for N days ago.
/// Returns nanoseconds since Cocoa epoch (2001-01-01).
pub fn days_ago_cocoa(days: u32) -> i64 {
    use std::time::{SystemTime, UNIX_EPOCH};

    let now = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .expect("Time went backwards");

    let seconds_ago = days as u64 * 86400;
    let cutoff_unix = now.as_secs().saturating_sub(seconds_ago) as i64;
    let cutoff_cocoa = cutoff_unix - COCOA_EPOCH_OFFSET;

    cutoff_cocoa * 1_000_000_000
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_cocoa_to_unix() {
        // 2025-01-01 00:00:00 UTC in Cocoa time
        let cocoa = 757_382_400_000_000_000i64;
        let unix = cocoa_to_unix(cocoa);
        // Should be around 1735689600 (2025-01-01)
        assert!(unix > 1735689500 && unix < 1735689700);
    }
}

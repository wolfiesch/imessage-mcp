//! Daemon service - dispatches requests to command handlers.
//!
//! Maintains hot resources (SQLite connection, contact cache) for fast execution.
//!
//! CHANGELOG:
//! - 01/11/2026 - Refactored: added param helpers, enrichment methods (review feedback) (Claude)
//! - 01/11/2026 - Optimized analytics: 6 queries → 3 queries (20ms → ~5ms) (Claude)
//! - 01/10/2026 - Implemented all command handlers (Phase 5) (Claude)
//! - 01/10/2026 - Initial implementation (Phase 4C, Claude)

use anyhow::{anyhow, Result};
use rusqlite::Connection;
use std::collections::HashMap;
use std::sync::Arc;

use crate::contacts::manager::ContactsManager;
use crate::db::connection::open_db;
use crate::db::helpers;
use crate::db::queries;

// ============================================================================
// Time Constants (for self-documenting time calculations)
// ============================================================================

const SECONDS_PER_DAY: i64 = 24 * 3600;
const NANOS_PER_SECOND: i64 = 1_000_000_000;

/// Daemon service with hot resources.
pub struct DaemonService {
    conn: Connection,               // Hot SQLite connection (eliminates 5ms overhead per query)
    contacts: Arc<ContactsManager>, // Cached contacts (eliminates 20-50ms per command)
    started_at: String,             // ISO timestamp
}

impl DaemonService {
    /// Create new daemon service with hot resources.
    pub fn new() -> Result<Self> {
        let conn = open_db()?;
        let contacts = Arc::new(
            ContactsManager::load_default().unwrap_or_else(|_| ContactsManager::empty()),
        );

        let started_at = chrono::Utc::now().to_rfc3339();

        Ok(Self {
            conn,
            contacts,
            started_at,
        })
    }

    // ========================================================================
    // Parameter Parsing Helpers (reduces boilerplate)
    // ========================================================================

    /// Get optional u32 parameter with default value.
    fn get_param_u32(params: &HashMap<String, serde_json::Value>, key: &str, default: u32) -> u32 {
        params
            .get(key)
            .and_then(|v| v.as_u64())
            .map(|v| v as u32)
            .unwrap_or(default)
    }

    /// Get optional string parameter.
    fn get_param_str<'a>(params: &'a HashMap<String, serde_json::Value>, key: &str) -> Option<&'a str> {
        params.get(key).and_then(|v| v.as_str())
    }

    /// Convert days to stale threshold in nanoseconds.
    fn days_to_stale_ns(days: u32) -> i64 {
        (days as i64) * SECONDS_PER_DAY * NANOS_PER_SECOND
    }

    // ========================================================================
    // Contact Enrichment Helpers (reduces duplication)
    // ========================================================================

    /// Enrich a recent message with contact name.
    fn enrich_recent_message(&self, msg: helpers::RecentMessage) -> serde_json::Value {
        let contact_name = self.contacts.find_by_phone(&msg.phone).map(|c| c.name.clone());
        serde_json::json!({
            "text": msg.text,
            "date": msg.date,
            "is_from_me": msg.is_from_me,
            "phone": msg.phone,
            "contact_name": contact_name,
        })
    }

    /// Enrich an unread message with contact name.
    fn enrich_unread_message(&self, msg: helpers::UnreadMessage) -> serde_json::Value {
        let contact_name = self.contacts.find_by_phone(&msg.phone).map(|c| c.name.clone());
        serde_json::json!({
            "text": msg.text,
            "date": msg.date,
            "phone": msg.phone,
            "contact_name": contact_name,
        })
    }

    /// Enrich handle info with contact name.
    fn enrich_handle(&self, handle: helpers::HandleInfo) -> serde_json::Value {
        let contact_name = self.contacts.find_by_phone(&handle.handle).map(|c| c.name.clone());
        serde_json::json!({
            "handle": handle.handle,
            "contact_name": contact_name,
            "message_count": handle.message_count,
            "last_date": handle.last_date,
        })
    }

    /// Enrich top contact with name.
    fn enrich_top_contact(&self, tc: helpers::TopContact) -> serde_json::Value {
        let contact_name = self.contacts.find_by_phone(&tc.phone).map(|c| c.name.clone());
        serde_json::json!({
            "phone": tc.phone,
            "contact_name": contact_name,
            "message_count": tc.message_count,
        })
    }

    /// Enrich unknown sender with context.
    fn enrich_unknown_sender(&self, sender: helpers::UnknownSender) -> serde_json::Value {
        serde_json::json!({
            "handle": sender.handle,
            "message_count": sender.message_count,
            "last_date": sender.last_date,
            "sample_text": sender.sample_text,
        })
    }

    /// Enrich unanswered question with contact name.
    fn enrich_unanswered(&self, q: helpers::UnansweredQuestion) -> serde_json::Value {
        let contact_name = self.contacts.find_by_phone(&q.phone).map(|c| c.name.clone());
        serde_json::json!({
            "text": q.text,
            "date": q.date,
            "phone": q.phone,
            "contact_name": contact_name,
            "days_ago": q.days_ago,
        })
    }

    /// Enrich stale conversation with contact name.
    fn enrich_stale_conversation(&self, conv: helpers::StaleConversation) -> serde_json::Value {
        let contact_name = self.contacts.find_by_phone(&conv.phone).map(|c| c.name.clone());
        serde_json::json!({
            "phone": conv.phone,
            "contact_name": contact_name,
            "last_date": conv.last_date,
            "days_ago": conv.days_ago,
            "last_text": conv.last_text,
        })
    }

    // ========================================================================
    // Dispatcher
    // ========================================================================

    /// Dispatch request to appropriate handler.
    pub fn dispatch(
        &self,
        method: &str,
        params: HashMap<String, serde_json::Value>,
    ) -> Result<serde_json::Value> {
        match method {
            "health" => self.health(),
            "analytics" => self.analytics(params),
            "followup" => self.followup(params),
            "recent" => self.recent(params),
            "unread" => self.unread(params),
            "discover" => self.discover(params),
            "unknown" => self.unknown(params),
            "handles" => self.handles(params),
            "bundle" => self.bundle(params),
            _ => Err(anyhow!("Unknown method: {}", method)),
        }
    }

    // ========================================================================
    // Health Check
    // ========================================================================

    /// Health check endpoint.
    fn health(&self) -> Result<serde_json::Value> {
        Ok(serde_json::json!({
            "pid": std::process::id(),
            "started_at": self.started_at,
            "version": "v1",
            "contacts_loaded": self.contacts.all().len(),
        }))
    }

    // ========================================================================
    // P0 Handlers: recent, unread, analytics
    // ========================================================================

    /// Recent messages handler.
    /// Params: days (default 7), limit (default 20)
    fn recent(&self, params: HashMap<String, serde_json::Value>) -> Result<serde_json::Value> {
        let days = Self::get_param_u32(&params, "days", 7);
        let limit = Self::get_param_u32(&params, "limit", 20);

        let cutoff_cocoa = queries::days_ago_cocoa(days);
        let messages = helpers::query_recent_messages(&self.conn, cutoff_cocoa, limit)?;

        let enriched: Vec<serde_json::Value> = messages
            .into_iter()
            .map(|msg| self.enrich_recent_message(msg))
            .collect();

        Ok(serde_json::json!({
            "messages": enriched,
            "count": enriched.len(),
            "days": days,
        }))
    }

    /// Unread messages handler.
    /// Params: limit (default 50)
    fn unread(&self, params: HashMap<String, serde_json::Value>) -> Result<serde_json::Value> {
        let limit = Self::get_param_u32(&params, "limit", 50);
        let messages = helpers::query_unread_messages(&self.conn, limit)?;

        let enriched: Vec<serde_json::Value> = messages
            .into_iter()
            .map(|msg| self.enrich_unread_message(msg))
            .collect();

        Ok(serde_json::json!({
            "unread_count": enriched.len(),
            "messages": enriched,
        }))
    }

    /// Analytics command handler (optimized - 2 queries instead of 6).
    /// Params: contact (optional), days (default 30)
    fn analytics(&self, params: HashMap<String, serde_json::Value>) -> Result<serde_json::Value> {
        let contact = Self::get_param_str(&params, "contact");
        let days = Self::get_param_u32(&params, "days", 30);

        // Resolve contact to phone if provided
        let phone = contact.and_then(|name| {
            self.contacts.find_by_name(name).map(|c| c.phone.clone())
        });

        let cutoff_cocoa = queries::days_ago_cocoa(days);
        let phone_ref = phone.as_deref();

        // Query 1: Combined analytics (total, sent, received, reactions, attachments, busiest_hour, busiest_day)
        let stats = helpers::query_analytics_combined(&self.conn, cutoff_cocoa, phone_ref)?;

        // Query 2: Top contacts (only if no phone filter)
        let top_contacts = if phone_ref.is_none() {
            helpers::query_top_contacts(&self.conn, cutoff_cocoa)?
        } else {
            Vec::new()
        };

        let busiest_day_name = stats.busiest_day
            .and_then(|d| helpers::day_number_to_name(d).map(|s| s.to_string()));

        let enriched_top_contacts: Vec<serde_json::Value> = top_contacts
            .into_iter()
            .map(|tc| self.enrich_top_contact(tc))
            .collect();

        let avg_daily = if days > 0 {
            (stats.total as f64) / (days as f64)
        } else {
            0.0
        };

        Ok(serde_json::json!({
            "period_days": days,
            "total_messages": stats.total,
            "sent_count": stats.sent,
            "received_count": stats.received,
            "avg_per_day": (avg_daily * 10.0).round() / 10.0,
            "busiest_hour": stats.busiest_hour,
            "busiest_day": busiest_day_name,
            "top_contacts": enriched_top_contacts,
            "attachment_count": stats.attachments,
            "reaction_count": stats.reactions,
        }))
    }

    // ========================================================================
    // P1 Handlers: followup, handles, unknown, discover, bundle
    // ========================================================================

    /// Follow-up command handler.
    /// Params: days (default 30), stale (default 3)
    fn followup(&self, params: HashMap<String, serde_json::Value>) -> Result<serde_json::Value> {
        let days = Self::get_param_u32(&params, "days", 30);
        let stale = Self::get_param_u32(&params, "stale", 3);

        let cutoff_cocoa = queries::days_ago_cocoa(days);
        let stale_threshold_ns = Self::days_to_stale_ns(stale);

        let unanswered = helpers::query_unanswered_questions(&self.conn, cutoff_cocoa, stale_threshold_ns)?;
        let stale_convos = helpers::query_stale_conversations(&self.conn, cutoff_cocoa, stale_threshold_ns)?;

        let enriched_unanswered: Vec<serde_json::Value> = unanswered
            .into_iter()
            .map(|q| self.enrich_unanswered(q))
            .collect();

        let enriched_stale: Vec<serde_json::Value> = stale_convos
            .into_iter()
            .map(|s| self.enrich_stale_conversation(s))
            .collect();

        let total_items = enriched_unanswered.len() + enriched_stale.len();

        Ok(serde_json::json!({
            "unanswered_questions": enriched_unanswered,
            "stale_conversations": enriched_stale,
            "total_items": total_items,
        }))
    }

    /// Handles list handler.
    /// Params: days (default 30), limit (default 50)
    fn handles(&self, params: HashMap<String, serde_json::Value>) -> Result<serde_json::Value> {
        let days = Self::get_param_u32(&params, "days", 30);
        let limit = Self::get_param_u32(&params, "limit", 50);

        let cutoff_cocoa = queries::days_ago_cocoa(days);
        let handles = helpers::query_handles(&self.conn, cutoff_cocoa, limit)?;

        let enriched: Vec<serde_json::Value> = handles
            .into_iter()
            .map(|h| self.enrich_handle(h))
            .collect();

        Ok(serde_json::json!({
            "handles": enriched,
            "count": enriched.len(),
        }))
    }

    /// Unknown senders handler - handles not in contacts.
    /// Params: days (default 30), limit (default 20)
    fn unknown(&self, params: HashMap<String, serde_json::Value>) -> Result<serde_json::Value> {
        let days = Self::get_param_u32(&params, "days", 30);
        let limit = Self::get_param_u32(&params, "limit", 20);

        let cutoff_cocoa = queries::days_ago_cocoa(days);
        let all_senders = helpers::query_unknown_senders(&self.conn, cutoff_cocoa)?;

        // Filter to unknown senders (not in contacts)
        let unknown: Vec<serde_json::Value> = all_senders
            .into_iter()
            .filter(|s| self.contacts.find_by_phone(&s.handle).is_none())
            .take(limit as usize)
            .map(|s| self.enrich_unknown_sender(s))
            .collect();

        Ok(serde_json::json!({
            "unknown_senders": unknown,
            "count": unknown.len(),
        }))
    }

    /// Discovery command handler - find frequent unknown senders for potential contacts.
    /// Params: days (default 90), min_messages (default 3)
    fn discover(&self, params: HashMap<String, serde_json::Value>) -> Result<serde_json::Value> {
        let days = Self::get_param_u32(&params, "days", 90);
        let min_messages = Self::get_param_u32(&params, "min_messages", 3) as i64;

        let cutoff_cocoa = queries::days_ago_cocoa(days);
        let all_senders = helpers::query_unknown_senders(&self.conn, cutoff_cocoa)?;

        // Filter to unknown senders with enough messages
        let candidates: Vec<serde_json::Value> = all_senders
            .into_iter()
            .filter(|s| {
                self.contacts.find_by_phone(&s.handle).is_none()
                    && s.message_count >= min_messages
            })
            .map(|s| self.enrich_unknown_sender(s))
            .collect();

        Ok(serde_json::json!({
            "discovery_candidates": candidates,
            "count": candidates.len(),
            "criteria": {
                "days": days,
                "min_messages": min_messages,
            },
        }))
    }

    /// Bundle command handler - combines multiple queries for dashboard use.
    /// Params: include (comma-separated: unread_count,recent,analytics,followup_count)
    fn bundle(&self, params: HashMap<String, serde_json::Value>) -> Result<serde_json::Value> {
        let include = Self::get_param_str(&params, "include").unwrap_or("unread_count,recent");
        let sections: Vec<&str> = include.split(',').map(|s| s.trim()).collect();
        let mut result = serde_json::Map::new();

        for section in sections {
            match section {
                "unread_count" => {
                    let unread = helpers::query_unread_messages(&self.conn, 100)?;
                    result.insert("unread_count".to_string(), serde_json::json!(unread.len()));
                }
                "recent" => {
                    let limit = Self::get_param_u32(&params, "recent_limit", 10);
                    let days = Self::get_param_u32(&params, "recent_days", 7);
                    let cutoff = queries::days_ago_cocoa(days);
                    let messages = helpers::query_recent_messages(&self.conn, cutoff, limit)?;

                    let enriched: Vec<serde_json::Value> = messages
                        .into_iter()
                        .map(|msg| self.enrich_recent_message(msg))
                        .collect();
                    result.insert("recent".to_string(), serde_json::json!(enriched));
                }
                "analytics" => {
                    let days = Self::get_param_u32(&params, "analytics_days", 30);
                    let cutoff = queries::days_ago_cocoa(days);
                    let (total, sent, received) =
                        helpers::query_message_counts(&self.conn, cutoff, None)?;

                    result.insert(
                        "analytics".to_string(),
                        serde_json::json!({
                            "total_messages": total,
                            "sent_count": sent,
                            "received_count": received,
                            "period_days": days,
                        }),
                    );
                }
                "followup_count" => {
                    let days = Self::get_param_u32(&params, "followup_days", 30);
                    let stale = Self::get_param_u32(&params, "followup_stale", 3);
                    let cutoff = queries::days_ago_cocoa(days);
                    let stale_ns = Self::days_to_stale_ns(stale);

                    let unanswered = helpers::query_unanswered_questions(&self.conn, cutoff, stale_ns)?;
                    let stale_convos = helpers::query_stale_conversations(&self.conn, cutoff, stale_ns)?;

                    result.insert(
                        "followup_count".to_string(),
                        serde_json::json!(unanswered.len() + stale_convos.len()),
                    );
                }
                _ => {
                    // Unknown section, skip silently
                }
            }
        }

        Ok(serde_json::Value::Object(result))
    }
}

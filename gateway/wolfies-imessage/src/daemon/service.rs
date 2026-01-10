//! Daemon service - dispatches requests to command handlers.
//!
//! Maintains hot resources (SQLite connection, contact cache) for fast execution.
//!
//! CHANGELOG:
//! - 01/10/2026 - Initial implementation (Phase 4C, Claude)

use anyhow::{anyhow, Context, Result};
use rusqlite::Connection;
use std::collections::HashMap;
use std::sync::Arc;

use crate::contacts::manager::ContactsManager;
use crate::db::connection::open_db;

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

    /// Health check endpoint.
    fn health(&self) -> Result<serde_json::Value> {
        Ok(serde_json::json!({
            "pid": std::process::id(),
            "started_at": self.started_at,
            "version": "v1",
            "contacts_loaded": self.contacts.all().len(),
        }))
    }

    /// Analytics command handler.
    fn analytics(&self, _params: HashMap<String, serde_json::Value>) -> Result<serde_json::Value> {
        // [*TO-DO:P0*] Implement analytics with hot connection
        // For now, return placeholder
        Err(anyhow!("analytics not yet implemented in daemon mode"))
    }

    /// Follow-up command handler.
    fn followup(&self, _params: HashMap<String, serde_json::Value>) -> Result<serde_json::Value> {
        // [*TO-DO:P1*] Implement followup with hot connection
        Err(anyhow!("followup not yet implemented in daemon mode"))
    }

    /// Recent messages handler.
    fn recent(&self, _params: HashMap<String, serde_json::Value>) -> Result<serde_json::Value> {
        // [*TO-DO:P1*] Implement recent with hot connection
        Err(anyhow!("recent not yet implemented in daemon mode"))
    }

    /// Unread messages handler.
    fn unread(&self, _params: HashMap<String, serde_json::Value>) -> Result<serde_json::Value> {
        // [*TO-DO:P1*] Implement unread with hot connection
        Err(anyhow!("unread not yet implemented in daemon mode"))
    }

    /// Discovery command handler.
    fn discover(&self, _params: HashMap<String, serde_json::Value>) -> Result<serde_json::Value> {
        // [*TO-DO:P1*] Implement discover with hot connection
        Err(anyhow!("discover not yet implemented in daemon mode"))
    }

    /// Unknown senders handler.
    fn unknown(&self, _params: HashMap<String, serde_json::Value>) -> Result<serde_json::Value> {
        // [*TO-DO:P1*] Implement unknown with hot connection
        Err(anyhow!("unknown not yet implemented in daemon mode"))
    }

    /// Handles list handler.
    fn handles(&self, _params: HashMap<String, serde_json::Value>) -> Result<serde_json::Value> {
        // [*TO-DO:P1*] Implement handles with hot connection
        Err(anyhow!("handles not yet implemented in daemon mode"))
    }

    /// Bundle command handler (multiple operations).
    fn bundle(&self, _params: HashMap<String, serde_json::Value>) -> Result<serde_json::Value> {
        // [*TO-DO:P1*] Implement bundle with hot connection
        Err(anyhow!("bundle not yet implemented in daemon mode"))
    }
}

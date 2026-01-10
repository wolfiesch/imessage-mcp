//! SQLite connection management for Messages.db.
//!
//! CHANGELOG:
//! - 01/10/2026 - Initial stub (Claude)

use anyhow::{Context, Result};
use rusqlite::Connection;
use std::path::PathBuf;

/// Default Messages.db path.
pub fn default_db_path() -> PathBuf {
    dirs::home_dir()
        .unwrap_or_else(|| PathBuf::from("."))
        .join("Library")
        .join("Messages")
        .join("chat.db")
}

/// Open a read-only connection to Messages.db.
pub fn open_db() -> Result<Connection> {
    let db_path = default_db_path();

    // [*INCOMPLETE*] Check for security-scoped bookmark first
    // Status: Opens default path only
    // Remaining: Integrate with bookmark storage from db_access.py

    Connection::open_with_flags(
        &db_path,
        rusqlite::OpenFlags::SQLITE_OPEN_READ_ONLY | rusqlite::OpenFlags::SQLITE_OPEN_NO_MUTEX,
    )
    .with_context(|| format!("Failed to open Messages database at {:?}", db_path))
}

/// Check if we have access to the Messages database.
pub fn check_access() -> bool {
    open_db().is_ok()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_default_db_path() {
        let path = default_db_path();
        assert!(path.ends_with("Library/Messages/chat.db"));
    }
}

//! Database module for SQLite access to Messages.db.
//!
//! CHANGELOG:
//! - 01/10/2026 - Added helpers module for shared query functions (Phase 5) (Claude)
//! - 01/10/2026 - Initial module structure (Claude)

pub mod blob_parser;
pub mod connection;
pub mod helpers;
pub mod queries;

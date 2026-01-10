//! Setup command for configuring database access.
//!
//! CHANGELOG:
//! - 01/10/2026 - Initial stub implementation (Claude)

use anyhow::Result;

/// Run the setup command to configure database access.
pub fn run(yes: bool, force: bool, json: bool) -> Result<()> {
    // [*INCOMPLETE*] Implement file picker and bookmark storage
    // Status: Stub only
    // Remaining: Port NSOpenPanel from file_picker.py, security-scoped bookmarks
    eprintln!("[TODO] setup: yes={}, force={}", yes, force);
    if json {
        println!(r#"{{"success": false, "error": "Not implemented yet"}}"#);
    } else {
        println!("Setup command not yet implemented in Rust.");
        println!("Use the Python CLI for setup: python3 gateway/imessage_client.py setup");
    }
    Ok(())
}

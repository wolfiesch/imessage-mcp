//! AppleScript execution for sending iMessages.
//!
//! Uses osascript to communicate with Messages.app.
//!
//! CHANGELOG:
//! - 01/10/2026 - Initial implementation (Claude)

use anyhow::{anyhow, Result};
use std::process::Command;
use std::time::Duration;

/// Escape a string for safe inclusion in AppleScript.
///
/// CRITICAL: Order matters!
/// 1. Escape backslashes FIRST
/// 2. Then escape quotes
///
/// This prevents injection attacks where user data breaks the string context.
pub fn escape_applescript_string(s: &str) -> String {
    s.replace('\\', "\\\\") // Backslashes FIRST
        .replace('"', "\\\"") // Then quotes
}

/// Send an iMessage via Messages.app.
///
/// Uses AppleScript to target the iMessage service and send to a participant.
///
/// # Arguments
/// * `phone` - Phone number or email (will be escaped)
/// * `message` - Message text (will be escaped)
///
/// # Returns
/// * `Ok(())` on success
/// * `Err` with AppleScript error on failure
pub fn send_imessage(phone: &str, message: &str) -> Result<()> {
    let safe_phone = escape_applescript_string(phone);
    let safe_msg = escape_applescript_string(message);

    let script = format!(
        r#"
tell application "Messages"
    set targetService to 1st account whose service type = iMessage
    set targetBuddy to participant "{}" of targetService
    send "{}" to targetBuddy
end tell
"#,
        safe_phone, safe_msg
    );

    let output = Command::new("osascript")
        .arg("-e")
        .arg(&script)
        .output()?;

    if output.status.success() {
        Ok(())
    } else {
        let stderr = String::from_utf8_lossy(&output.stderr);
        Err(anyhow!(
            "AppleScript failed: {}",
            stderr.trim().to_string()
        ))
    }
}

/// Send an iMessage with timeout (for potentially slow operations).
///
/// Note: This is a simple wrapper - actual timeout requires async or threads.
/// For now, we trust osascript to complete in reasonable time.
pub fn send_imessage_with_timeout(phone: &str, message: &str, _timeout: Duration) -> Result<()> {
    // TODO: Implement actual timeout using threads or async
    // For now, delegate to standard send
    send_imessage(phone, message)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_escape_simple() {
        assert_eq!(escape_applescript_string("Hello"), "Hello");
    }

    #[test]
    fn test_escape_quotes() {
        assert_eq!(escape_applescript_string(r#"Say "Hi""#), r#"Say \"Hi\""#);
    }

    #[test]
    fn test_escape_backslash() {
        assert_eq!(escape_applescript_string(r"Path\to\file"), r"Path\\to\\file");
    }

    #[test]
    fn test_escape_both() {
        // Backslash-quote combination: \"hi\"
        assert_eq!(
            escape_applescript_string(r#"Say \"Hi\""#),
            r#"Say \\\"Hi\\\""#
        );
    }

    #[test]
    fn test_escape_order_matters() {
        // Input: "hi" with backslash before quote
        // Correct: \\ first, then \"
        let input = r#"\"test\""#;
        let expected = r#"\\\"test\\\""#;
        assert_eq!(escape_applescript_string(input), expected);
    }
}

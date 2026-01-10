//! Parser for attributedBody binary blobs in Messages.db.
//!
//! macOS Messages stores text in two formats:
//! - `text` column: Plain text (older messages)
//! - `attributedBody` column: Binary blob (macOS Ventura+)
//!
//! The blob is typically NSKeyedArchiver format (bplist) or streamtyped format.
//!
//! CHANGELOG:
//! - 01/10/2026 - Implemented full blob parsing (Claude)
//! - 01/10/2026 - Initial stub (Claude)

use anyhow::Result;
use plist::Value;

/// Extract text from an attributedBody blob.
///
/// Handles multiple formats:
/// 1. NSKeyedArchiver bplist format
/// 2. Streamtyped format (NSString markers)
/// 3. Fallback regex extraction
pub fn extract_text_from_blob(blob: &[u8]) -> Result<Option<String>> {
    if blob.is_empty() {
        return Ok(None);
    }

    // Find bplist header (may not be at start of blob)
    if let Some(bplist_start) = find_subsequence(blob, b"bplist") {
        if let Ok(Some(text)) = parse_bplist(&blob[bplist_start..]) {
            return Ok(Some(text));
        }
    }

    // Try streamtyped format
    if let Some(text) = parse_streamtyped(blob) {
        return Ok(Some(text));
    }

    // Fallback: try to extract any readable text
    Ok(extract_readable_text(blob))
}

/// Find a subsequence in a byte slice.
fn find_subsequence(haystack: &[u8], needle: &[u8]) -> Option<usize> {
    haystack
        .windows(needle.len())
        .position(|window| window == needle)
}

/// Parse NSKeyedArchiver bplist format.
///
/// NSKeyedArchiver stores data with a $objects array containing the actual values.
fn parse_bplist(blob: &[u8]) -> Result<Option<String>> {
    // Parse the binary plist
    let plist: Value = plist::from_bytes(blob)?;

    // NSKeyedArchiver format has $objects array containing the data
    if let Value::Dictionary(dict) = &plist {
        if let Some(Value::Array(objects)) = dict.get("$objects") {
            // Collect text candidates
            let mut text_candidates: Vec<String> = Vec::new();

            for obj in objects {
                match obj {
                    Value::String(s) => {
                        // Skip class names and metadata
                        if !s.starts_with("NS")
                            && !s.starts_with('$')
                            && !s.is_empty()
                        {
                            text_candidates.push(s.clone());
                        }
                    }
                    Value::Dictionary(d) => {
                        // Sometimes text is in NS.string key
                        if let Some(Value::String(s)) = d.get("NS.string") {
                            text_candidates.push(s.clone());
                        }
                        // Or in NS.bytes
                        if let Some(Value::Data(data)) = d.get("NS.bytes") {
                            if let Ok(s) = String::from_utf8(data.clone()) {
                                text_candidates.push(s);
                            }
                        }
                    }
                    _ => {}
                }
            }

            // Return the first substantial text found
            for text in text_candidates {
                let trimmed = text.trim();
                if !trimmed.is_empty() {
                    return Ok(Some(trimmed.to_string()));
                }
            }
        }

        // Fallback: try to find readable text in plist values
        for (_, value) in dict {
            if let Value::String(s) = value {
                if !s.is_empty() && !s.starts_with("NS") {
                    return Ok(Some(s.clone()));
                }
            }
        }
    }

    Ok(None)
}

/// Parse streamtyped format (macOS Messages format).
///
/// Format:
/// - Header: streamtyped + class hierarchy
/// - After "NSString" marker: control bytes + '+' + length byte + actual text
/// - Text ends before control sequences (0x86, 0x84, etc.)
fn parse_streamtyped(blob: &[u8]) -> Option<String> {
    // Method 1: Find NSString marker
    if let Some(nsstring_idx) = find_subsequence(blob, b"NSString") {
        // Look for the '+' marker which precedes the text
        let search_range = &blob[nsstring_idx..];
        if let Some(plus_offset) = find_subsequence(search_range, b"+") {
            if plus_offset < 20 {
                // Skip the '+' and the length byte
                let text_start_abs = nsstring_idx + plus_offset + 2;
                if text_start_abs < blob.len() {
                    let text_bytes = extract_until_control(&blob[text_start_abs..]);
                    if let Some(text) = try_decode_text(text_bytes) {
                        if !text.is_empty() {
                            return Some(text);
                        }
                    }
                }
            }
        }
    }

    // Method 2: Try NSMutableString
    if let Some(nsmut_idx) = find_subsequence(blob, b"NSMutableString") {
        let search_range = &blob[nsmut_idx..];
        if let Some(plus_offset) = find_subsequence(search_range, b"+") {
            let text_start_abs = nsmut_idx + plus_offset + 2;
            if text_start_abs < blob.len() {
                let text_bytes = extract_until_control(&blob[text_start_abs..]);
                if let Some(text) = try_decode_text(text_bytes) {
                    if !text.is_empty() {
                        return Some(text);
                    }
                }
            }
        }
    }

    None
}

/// Extract bytes until a control character is encountered.
fn extract_until_control(blob: &[u8]) -> &[u8] {
    let mut end = 0;
    while end < blob.len() {
        let byte = blob[end];
        // Stop at control sequences commonly ending the text
        if byte == 0x86 || byte == 0x84 || byte == 0x00 {
            break;
        }
        // Also check for 'i' followed by 'I' or 'N' (common end pattern)
        if byte == b'i' && end + 1 < blob.len() {
            let next = blob[end + 1];
            if next == 0x49 || next == 0x4e {
                break;
            }
        }
        end += 1;
    }
    &blob[..end]
}

/// Try to decode bytes as UTF-8 text.
fn try_decode_text(bytes: &[u8]) -> Option<String> {
    // First try strict UTF-8
    if let Ok(text) = String::from_utf8(bytes.to_vec()) {
        let trimmed = text.trim();
        if !trimmed.is_empty() {
            return Some(trimmed.to_string());
        }
    }

    // Fallback: lossy decode
    let text = String::from_utf8_lossy(bytes);
    let trimmed = text.trim();
    if !trimmed.is_empty() {
        return Some(trimmed.to_string());
    }

    None
}

/// Fallback: extract any readable text from blob.
///
/// Decodes as UTF-8 and looks for substantial printable runs that aren't metadata.
fn extract_readable_text(blob: &[u8]) -> Option<String> {
    let text = String::from_utf8_lossy(blob);

    // Skip patterns that indicate metadata
    let skip_patterns = [
        "NSString",
        "NSObject",
        "NSMutable",
        "NSDictionary",
        "NSAttributed",
        "streamtyped",
        "__kIM",
        "NSNumber",
        "NSValue",
    ];

    // Find printable runs (at least 3 chars, excluding control chars)
    let mut best_candidate: Option<String> = None;
    let mut current_run = String::new();

    for ch in text.chars() {
        if ch.is_ascii_graphic() || ch == ' ' {
            current_run.push(ch);
        } else if !current_run.is_empty() {
            if current_run.len() >= 3 {
                let should_skip = skip_patterns.iter().any(|p| current_run.contains(p));
                if !should_skip {
                    let cleaned = current_run.trim_matches('+').trim();
                    if cleaned.len() >= 2 {
                        // Prefer longer runs
                        if best_candidate.as_ref().map_or(true, |b| cleaned.len() > b.len()) {
                            best_candidate = Some(cleaned.to_string());
                        }
                    }
                }
            }
            current_run.clear();
        }
    }

    // Check final run
    if current_run.len() >= 3 {
        let should_skip = skip_patterns.iter().any(|p| current_run.contains(p));
        if !should_skip {
            let cleaned = current_run.trim_matches('+').trim();
            if cleaned.len() >= 2 {
                if best_candidate.as_ref().map_or(true, |b| cleaned.len() > b.len()) {
                    best_candidate = Some(cleaned.to_string());
                }
            }
        }
    }

    best_candidate
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_empty_blob() {
        let result = extract_text_from_blob(&[]).unwrap();
        assert_eq!(result, None);
    }

    #[test]
    fn test_streamtyped_nsstring() {
        // Simulated streamtyped blob with NSString marker
        let mut blob: Vec<u8> = b"streamtyped".to_vec();
        blob.extend_from_slice(b"NSString");
        blob.extend_from_slice(&[0x01, 0x94, 0x84, 0x01, b'+', 0x05]); // control bytes + length
        blob.extend_from_slice(b"Hello"); // actual text
        blob.extend_from_slice(&[0x86, 0x84]); // end markers

        let result = extract_text_from_blob(&blob).unwrap();
        assert_eq!(result, Some("Hello".to_string()));
    }

    #[test]
    fn test_find_subsequence() {
        assert_eq!(find_subsequence(b"hello world", b"world"), Some(6));
        assert_eq!(find_subsequence(b"hello", b"world"), None);
        assert_eq!(find_subsequence(b"NSString test", b"NSString"), Some(0));
    }
}

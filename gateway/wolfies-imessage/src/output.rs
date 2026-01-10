//! Output formatting and control utilities.
//!
//! CHANGELOG:
//! - 01/10/2026 - Initial implementation (Claude)

use serde::Serialize;
use serde_json::{json, Value};

/// Output control settings from CLI flags.
#[derive(Debug, Clone, Default)]
pub struct OutputControls {
    pub json: bool,
    pub compact: bool,
    pub minimal: bool,
    pub fields: Option<String>,
    pub max_text_chars: Option<u32>,
}

impl OutputControls {
    /// Emit data according to output controls.
    pub fn emit<T: Serialize>(&self, data: &T) -> String {
        let value = serde_json::to_value(data).unwrap_or(json!(null));

        // Apply field filtering if specified
        let filtered = if let Some(ref fields) = self.fields {
            filter_fields(&value, fields)
        } else if self.minimal {
            // Minimal preset includes common fields
            value
        } else {
            value
        };

        // Apply text truncation if specified
        let truncated = if let Some(max_chars) = self.max_text_chars {
            truncate_text_fields(&filtered, max_chars as usize)
        } else {
            filtered
        };

        // Format output
        if self.compact || self.minimal {
            serde_json::to_string(&truncated).unwrap_or_else(|_| "{}".to_string())
        } else {
            serde_json::to_string_pretty(&truncated).unwrap_or_else(|_| "{}".to_string())
        }
    }

    /// Print data to stdout according to output controls.
    pub fn print<T: Serialize>(&self, data: &T) {
        println!("{}", self.emit(data));
    }
}

/// Filter JSON value to only include specified fields.
fn filter_fields(value: &Value, fields: &str) -> Value {
    let field_list: Vec<&str> = fields.split(',').map(|s| s.trim()).collect();

    match value {
        Value::Array(arr) => {
            Value::Array(arr.iter().map(|v| filter_fields(v, fields)).collect())
        }
        Value::Object(map) => {
            let mut filtered = serde_json::Map::new();
            for field in &field_list {
                if let Some(v) = map.get(*field) {
                    filtered.insert(field.to_string(), v.clone());
                }
            }
            Value::Object(filtered)
        }
        _ => value.clone(),
    }
}

/// Truncate string fields in JSON value.
fn truncate_text_fields(value: &Value, max_chars: usize) -> Value {
    match value {
        Value::String(s) if s.len() > max_chars => {
            Value::String(format!("{}...", &s[..max_chars]))
        }
        Value::Array(arr) => {
            Value::Array(arr.iter().map(|v| truncate_text_fields(v, max_chars)).collect())
        }
        Value::Object(map) => {
            let mut truncated = serde_json::Map::new();
            for (k, v) in map {
                truncated.insert(k.clone(), truncate_text_fields(v, max_chars));
            }
            Value::Object(truncated)
        }
        _ => value.clone(),
    }
}

/// Format error as JSON.
pub fn format_error(error: &str) -> String {
    serde_json::to_string(&json!({
        "error": error,
        "success": false
    })).unwrap_or_else(|_| format!(r#"{{"error":"{}"}}"#, error))
}

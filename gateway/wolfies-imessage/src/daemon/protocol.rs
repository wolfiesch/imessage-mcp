//! Daemon protocol types for NDJSON communication over UNIX socket.
//!
//! CHANGELOG:
//! - 01/10/2026 - Initial implementation (Phase 4C, Claude)

use anyhow::{Context, Result};
use serde::{Deserialize, Serialize};
use std::collections::HashMap;

/// NDJSON request from client to daemon.
#[derive(Debug, Serialize, Deserialize)]
pub struct Request {
    /// Unique request ID (UUID)
    pub id: String,
    /// Protocol version (currently 1)
    pub v: u8,
    /// Method name (e.g., "health", "analytics", "bundle")
    pub method: String,
    /// Method parameters (flexible key-value map)
    pub params: HashMap<String, serde_json::Value>,
}

/// NDJSON response from daemon to client.
#[derive(Debug, Serialize, Deserialize)]
pub struct Response {
    /// Request ID (matches request)
    pub id: String,
    /// Success flag
    pub ok: bool,
    /// Result data (if successful)
    pub result: Option<serde_json::Value>,
    /// Error information (if failed)
    pub error: Option<ErrorInfo>,
    /// Response metadata
    pub meta: ResponseMeta,
}

/// Error details in response.
#[derive(Debug, Serialize, Deserialize)]
pub struct ErrorInfo {
    /// Error code (e.g., "ERROR", "NOT_FOUND")
    pub code: String,
    /// Human-readable error message
    pub message: String,
    /// Additional error details (optional)
    pub details: Option<serde_json::Value>,
}

/// Response metadata.
#[derive(Debug, Serialize, Deserialize)]
pub struct ResponseMeta {
    /// Server execution time in milliseconds
    pub server_ms: f64,
    /// Protocol version
    pub protocol_v: u8,
}

impl Request {
    /// Parse request from NDJSON line.
    pub fn from_ndjson_line(line: &str) -> Result<Self> {
        serde_json::from_str(line).context("Failed to parse request JSON")
    }
}

impl Response {
    /// Create a success response.
    pub fn success(id: String, result: serde_json::Value, server_ms: f64) -> Self {
        Self {
            id,
            ok: true,
            result: Some(result),
            error: None,
            meta: ResponseMeta {
                server_ms,
                protocol_v: 1,
            },
        }
    }

    /// Create an error response.
    pub fn error(id: String, code: &str, message: String, server_ms: f64) -> Self {
        Self {
            id,
            ok: false,
            result: None,
            error: Some(ErrorInfo {
                code: code.to_string(),
                message,
                details: None,
            }),
            meta: ResponseMeta {
                server_ms,
                protocol_v: 1,
            },
        }
    }

    /// Serialize response to NDJSON line.
    pub fn to_ndjson_line(&self) -> Result<String> {
        let json = serde_json::to_string(self)?;
        Ok(format!("{}\n", json))
    }
}

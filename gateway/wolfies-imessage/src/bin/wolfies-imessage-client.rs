//! wolfies-imessage-client - Thin client for daemon mode.
//!
//! CHANGELOG:
//! - 01/10/2026 - Initial implementation (Phase 4C, Claude)

use anyhow::Result;
use clap::Parser;
use serde_json::json;
use std::collections::HashMap;
use std::io::{BufRead, BufReader, Write};
use std::os::unix::net::UnixStream;

#[derive(Parser)]
#[command(name = "wolfies-imessage-client")]
#[command(about = "Thin client for wolfies-imessage daemon")]
struct Cli {
    /// Method to call
    method: String,

    /// Socket path
    #[arg(long, default_value = "~/.wolfies-imessage/daemon.sock")]
    socket: String,

    /// JSON parameters (as string)
    #[arg(long)]
    params: Option<String>,

    /// Request timeout (seconds)
    #[arg(long, default_value = "5.0")]
    timeout: f64,
}

fn main() -> Result<()> {
    let cli = Cli::parse();

    // Parse params JSON
    let params: HashMap<String, serde_json::Value> = if let Some(p) = cli.params {
        serde_json::from_str(&p)?
    } else {
        HashMap::new()
    };

    // Build request
    let request = json!({
        "id": uuid::Uuid::new_v4().to_string(),
        "v": 1,
        "method": cli.method,
        "params": params,
    });

    // Connect to daemon
    let socket_path = shellexpand::tilde(&cli.socket).to_string();
    let stream = UnixStream::connect(&socket_path)?;

    // Set timeout
    stream.set_read_timeout(Some(std::time::Duration::from_secs_f64(cli.timeout)))?;
    stream.set_write_timeout(Some(std::time::Duration::from_secs_f64(cli.timeout)))?;

    // Send request (NDJSON)
    let request_line = format!("{}\n", serde_json::to_string(&request)?);
    (&stream).write_all(request_line.as_bytes())?;

    // Read response (NDJSON)
    let mut reader = BufReader::new(&stream);
    let mut response_line = String::new();
    reader.read_line(&mut response_line)?;

    // Parse and print response
    let response: serde_json::Value = serde_json::from_str(&response_line)?;

    if response["ok"].as_bool().unwrap_or(false) {
        // Success: print result only
        println!("{}", serde_json::to_string_pretty(&response["result"])?);
        Ok(())
    } else {
        // Error: print error and exit with code 1
        eprintln!(
            "Error: {}",
            response["error"]["message"]
                .as_str()
                .unwrap_or("unknown")
        );
        std::process::exit(1);
    }
}

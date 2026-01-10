//! UNIX socket server for daemon mode.
//!
//! Listens on a UNIX socket, accepts connections, and dispatches requests
//! to DaemonService.
//!
//! CHANGELOG:
//! - 01/10/2026 - Initial implementation (Phase 4C, Claude)

use anyhow::Result;
use std::io::{BufRead, BufReader, Write};
use std::os::unix::net::{UnixListener, UnixStream};
use std::path::Path;
use std::time::Instant;

use crate::daemon::{protocol, service::DaemonService};

/// Daemon server listening on UNIX socket.
pub struct DaemonServer {
    service: DaemonService,
    socket_path: String,
}

impl DaemonServer {
    /// Create new daemon server.
    pub fn new(socket_path: impl AsRef<Path>) -> Result<Self> {
        let socket_path = socket_path.as_ref().to_string_lossy().to_string();
        let service = DaemonService::new()?;

        Ok(Self {
            service,
            socket_path,
        })
    }

    /// Start serving requests (blocking).
    pub fn serve(&self) -> Result<()> {
        // Clean up stale socket
        let _ = std::fs::remove_file(&self.socket_path);

        let listener = UnixListener::bind(&self.socket_path)?;

        // Set permissions to owner-only (0600)
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            std::fs::set_permissions(
                &self.socket_path,
                std::fs::Permissions::from_mode(0o600),
            )?;
        }

        eprintln!("[daemon] listening on {}", self.socket_path);

        // Accept connections sequentially (single-threaded)
        for stream in listener.incoming() {
            match stream {
                Ok(stream) => {
                    if let Err(e) = self.handle_connection(stream) {
                        eprintln!("[daemon] connection error: {}", e);
                    }
                }
                Err(e) => {
                    eprintln!("[daemon] accept error: {}", e);
                }
            }
        }

        Ok(())
    }

    /// Handle a single client connection.
    fn handle_connection(&self, stream: UnixStream) -> Result<()> {
        // Clone stream for writer (UNIX sockets support try_clone)
        let writer_stream = stream.try_clone()?;
        let mut reader = BufReader::new(&stream);
        let mut writer = writer_stream;

        // Read NDJSON request (one line)
        let mut line = String::new();
        reader.read_line(&mut line)?;

        if line.trim().is_empty() {
            return Ok(()); // Client disconnected
        }

        let start = Instant::now();

        // Parse request
        let request = protocol::Request::from_ndjson_line(&line)?;

        // Dispatch to service
        let response = match self.service.dispatch(&request.method, request.params) {
            Ok(result) => protocol::Response::success(
                request.id,
                result,
                start.elapsed().as_secs_f64() * 1000.0,
            ),
            Err(e) => protocol::Response::error(
                request.id,
                "ERROR",
                e.to_string(),
                start.elapsed().as_secs_f64() * 1000.0,
            ),
        };

        // Send NDJSON response
        let response_line = response.to_ndjson_line()?;
        writer.write_all(response_line.as_bytes())?;
        writer.flush()?;

        Ok(())
    }
}

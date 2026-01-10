//! wolfies-imessage-daemon - Persistent daemon with hot resources.
//!
//! CHANGELOG:
//! - 01/10/2026 - Initial implementation (Phase 4C, Claude)

use anyhow::Result;
use clap::{Parser, Subcommand};
use std::path::Path;

#[derive(Parser)]
#[command(name = "wolfies-imessage-daemon")]
#[command(about = "Persistent daemon for wolfies-imessage CLI")]
struct Cli {
    #[command(subcommand)]
    command: Commands,
}

#[derive(Subcommand)]
enum Commands {
    /// Start the daemon
    Start {
        /// Socket path (default: ~/.wolfies-imessage/daemon.sock)
        #[arg(long, default_value = "~/.wolfies-imessage/daemon.sock")]
        socket: String,

        /// Run in foreground (don't daemonize)
        #[arg(long)]
        foreground: bool,
    },

    /// Stop the daemon
    Stop {
        /// Socket path
        #[arg(long, default_value = "~/.wolfies-imessage/daemon.sock")]
        socket: String,
    },

    /// Check daemon status
    Status {
        /// Socket path
        #[arg(long, default_value = "~/.wolfies-imessage/daemon.sock")]
        socket: String,
    },
}

fn main() -> Result<()> {
    let cli = Cli::parse();

    match cli.command {
        Commands::Start { socket, foreground } => cmd_start(socket, foreground),
        Commands::Stop { socket } => cmd_stop(socket),
        Commands::Status { socket } => cmd_status(socket),
    }
}

fn cmd_start(socket: String, foreground: bool) -> Result<()> {
    let socket_path = shellexpand::tilde(&socket).to_string();

    // Create parent directory if needed
    if let Some(parent) = Path::new(&socket_path).parent() {
        std::fs::create_dir_all(parent)?;
    }

    if foreground {
        // Foreground mode (for development/debugging)
        eprintln!("[daemon] starting in foreground");
        let server = wolfies_imessage::daemon::server::DaemonServer::new(&socket_path)?;
        server.serve()?;
    } else {
        // Background mode (fork into daemon process)
        use daemonize::Daemonize;

        let pid_file = format!("{}.pid", socket_path);

        let daemonize = Daemonize::new()
            .pid_file(&pid_file)
            .working_directory("/tmp");

        match daemonize.start() {
            Ok(_) => {
                // Child process: run server
                let server = wolfies_imessage::daemon::server::DaemonServer::new(&socket_path)?;
                server.serve()?;
            }
            Err(e) => {
                eprintln!("Failed to daemonize: {}", e);
                std::process::exit(1);
            }
        }
    }

    Ok(())
}

fn cmd_stop(socket: String) -> Result<()> {
    let socket_path = shellexpand::tilde(&socket).to_string();
    let pid_file = format!("{}.pid", socket_path);

    // Read PID file
    let pid_str = std::fs::read_to_string(&pid_file)?;
    let pid: i32 = pid_str.trim().parse()?;

    // Send SIGTERM
    unsafe {
        libc::kill(pid, libc::SIGTERM);
    }

    // Clean up files
    let _ = std::fs::remove_file(&pid_file);
    let _ = std::fs::remove_file(&socket_path);

    println!("Daemon stopped (pid {})", pid);

    Ok(())
}

fn cmd_status(socket: String) -> Result<()> {
    let socket_path = shellexpand::tilde(&socket).to_string();

    // Try to connect to socket
    match std::os::unix::net::UnixStream::connect(&socket_path) {
        Ok(_) => {
            println!("Daemon running at {}", socket_path);
            Ok(())
        }
        Err(_) => {
            println!("Daemon not running");
            std::process::exit(1);
        }
    }
}

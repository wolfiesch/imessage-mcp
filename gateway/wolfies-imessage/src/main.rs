//! wolfies-imessage - Fast Rust CLI for iMessage
//!
//! Direct SQLite queries for reading, AppleScript for sending.
//! RAG commands delegate to Python daemon via Unix socket.
//!
//! CHANGELOG:
//! - 01/10/2026 - Initial scaffold with CLI skeleton (Claude)

use clap::{Parser, Subcommand};
use std::process::ExitCode;
use std::sync::Arc;

mod applescript;
mod commands;
mod contacts;
mod db;
mod output;

/// Fast Rust CLI for iMessage - direct SQLite queries and AppleScript sending.
#[derive(Parser, Debug)]
#[command(name = "wolfies-imessage")]
#[command(version, about, long_about = None)]
struct Cli {
    /// Output as JSON (most commands support this)
    #[arg(long, global = true)]
    json: bool,

    /// Compact JSON output (reduced fields, no whitespace)
    #[arg(long, global = true)]
    compact: bool,

    /// Minimal JSON preset (compact + truncation)
    #[arg(long, global = true)]
    minimal: bool,

    /// Comma-separated field allowlist
    #[arg(long, global = true)]
    fields: Option<String>,

    /// Truncate text fields to this length
    #[arg(long, global = true)]
    max_text_chars: Option<u32>,

    #[command(subcommand)]
    command: Command,
}

#[derive(Subcommand, Debug)]
enum Command {
    // =========================================================================
    // CORE READING COMMANDS
    // =========================================================================
    /// Find messages with a contact (keyword search)
    Find {
        /// Contact name (fuzzy matched)
        contact: String,

        /// Text to search for in messages
        #[arg(short, long)]
        query: Option<String>,

        /// Max messages to return (1-500)
        #[arg(short, long, default_value_t = 30)]
        limit: u32,
    },

    /// Get messages with a specific contact
    Messages {
        /// Contact name
        contact: String,

        /// Max messages (1-500)
        #[arg(short, long, default_value_t = 20)]
        limit: u32,
    },

    /// Get recent conversations across all contacts
    Recent {
        /// Max conversations (1-500)
        #[arg(short, long, default_value_t = 10)]
        limit: u32,
    },

    /// Get unread messages
    Unread {
        /// Max messages (1-500)
        #[arg(short, long, default_value_t = 20)]
        limit: u32,
    },

    /// Fast text search across all messages (no embeddings)
    TextSearch {
        /// Search query (keyword or phrase)
        query: String,

        /// Optional contact name to filter results
        #[arg(long)]
        contact: Option<String>,

        /// Max results (1-500)
        #[arg(short, long, default_value_t = 50)]
        limit: u32,

        /// Only search messages from the last N days
        #[arg(long)]
        days: Option<u32>,

        /// Only search messages on/after YYYY-MM-DD
        #[arg(long)]
        since: Option<String>,
    },

    /// Run a canonical LLM workload bundle in one call
    Bundle {
        /// Optional contact name to include contact-specific data
        #[arg(long)]
        contact: Option<String>,

        /// Optional keyword search query
        #[arg(long)]
        query: Option<String>,

        /// Only search messages from the last N days
        #[arg(long)]
        days: Option<u32>,

        /// Only search messages on/after YYYY-MM-DD
        #[arg(long)]
        since: Option<String>,

        /// Unread messages limit
        #[arg(long, default_value_t = 20)]
        unread_limit: u32,

        /// Recent messages limit
        #[arg(long, default_value_t = 10)]
        recent_limit: u32,

        /// Search results limit
        #[arg(long, default_value_t = 20)]
        search_limit: u32,

        /// Messages limit for contact_messages
        #[arg(long, default_value_t = 20)]
        messages_limit: u32,

        /// Scope keyword search to specified contact
        #[arg(long)]
        search_scoped_to_contact: bool,

        /// Comma-separated bundle sections to include
        #[arg(long)]
        include: Option<String>,
    },

    // =========================================================================
    // MESSAGING COMMANDS
    // =========================================================================
    /// Send a message to a contact
    Send {
        /// Contact name
        contact: String,

        /// Message to send
        message: Vec<String>,
    },

    /// Send message directly to phone number
    SendByPhone {
        /// Phone number (e.g., +14155551234)
        phone: String,

        /// Message to send
        message: Vec<String>,
    },

    // =========================================================================
    // CONTACT COMMANDS
    // =========================================================================
    /// List all contacts
    Contacts,

    /// Add a new contact
    AddContact {
        /// Contact name
        name: String,

        /// Phone number (e.g., +14155551234)
        phone: String,

        /// Relationship type
        #[arg(short, long, default_value = "other")]
        relationship: String,

        /// Notes about the contact
        #[arg(short, long)]
        notes: Option<String>,
    },

    // =========================================================================
    // ANALYTICS COMMANDS
    // =========================================================================
    /// Get conversation analytics
    Analytics {
        /// Contact name (optional)
        contact: Option<String>,

        /// Days to analyze (1-365)
        #[arg(short, long, default_value_t = 30)]
        days: u32,
    },

    /// Detect messages needing follow-up
    Followup {
        /// Days to look back (1-365)
        #[arg(short, long, default_value_t = 7)]
        days: u32,

        /// Min stale days (1-365)
        #[arg(short, long, default_value_t = 2)]
        stale: u32,
    },

    // =========================================================================
    // GROUP COMMANDS
    // =========================================================================
    /// List all group chats
    Groups {
        /// Max groups (1-500)
        #[arg(short, long, default_value_t = 50)]
        limit: u32,
    },

    /// Get messages from a group chat
    GroupMessages {
        /// Group chat ID
        #[arg(short, long)]
        group_id: Option<String>,

        /// Filter by participant phone/email
        #[arg(short, long)]
        participant: Option<String>,

        /// Max messages (1-500)
        #[arg(short, long, default_value_t = 50)]
        limit: u32,
    },

    // =========================================================================
    // T1 COMMANDS - Advanced Features
    // =========================================================================
    /// Get attachments (photos, videos, files)
    Attachments {
        /// Contact name (optional)
        contact: Option<String>,

        /// MIME type filter (e.g., "image/", "video/")
        #[arg(short = 't', long = "type")]
        mime_type: Option<String>,

        /// Max attachments (1-500)
        #[arg(short, long, default_value_t = 50)]
        limit: u32,
    },

    /// Get reactions (tapbacks) from messages
    Reactions {
        /// Contact name (optional)
        contact: Option<String>,

        /// Max reactions (1-500)
        #[arg(short, long, default_value_t = 100)]
        limit: u32,
    },

    /// Extract URLs shared in conversations
    Links {
        /// Contact name (optional)
        contact: Option<String>,

        /// Days to look back (1-365)
        #[arg(short, long)]
        days: Option<u32>,

        /// Search without date cutoff
        #[arg(long)]
        all_time: bool,

        /// Max links (1-500)
        #[arg(short, long, default_value_t = 100)]
        limit: u32,
    },

    /// Get voice messages with file paths
    Voice {
        /// Contact name (optional)
        contact: Option<String>,

        /// Max voice messages (1-500)
        #[arg(short, long, default_value_t = 50)]
        limit: u32,
    },

    /// Get messages in a reply thread
    Thread {
        /// Message GUID to get thread for
        #[arg(short, long)]
        guid: String,

        /// Max messages (1-500)
        #[arg(short, long, default_value_t = 50)]
        limit: u32,
    },

    // =========================================================================
    // T2 COMMANDS - Discovery Features
    // =========================================================================
    /// List all phone/email handles from recent messages
    Handles {
        /// Days to look back (1-365)
        #[arg(short, long, default_value_t = 30)]
        days: u32,

        /// Max handles (1-500)
        #[arg(short, long, default_value_t = 100)]
        limit: u32,
    },

    /// Find messages from senders not in contacts
    Unknown {
        /// Days to look back (1-365)
        #[arg(short, long, default_value_t = 30)]
        days: u32,

        /// Max unknown senders (1-500)
        #[arg(short, long, default_value_t = 100)]
        limit: u32,
    },

    /// Discover frequent texters not in contacts
    Discover {
        /// Days to look back (1-365)
        #[arg(short, long, default_value_t = 90)]
        days: u32,

        /// Max contacts to discover (1-100)
        #[arg(short, long, default_value_t = 20)]
        limit: u32,

        /// Minimum message count to include
        #[arg(short, long, default_value_t = 5)]
        min_messages: u32,
    },

    /// Get scheduled messages (pending sends)
    Scheduled,

    /// Get conversation formatted for AI summarization
    Summary {
        /// Contact name
        contact: String,

        /// Days to include (1-365)
        #[arg(short, long)]
        days: Option<u32>,

        /// Start date (YYYY-MM-DD)
        #[arg(long)]
        start: Option<String>,

        /// End date (YYYY-MM-DD)
        #[arg(long)]
        end: Option<String>,

        /// Max messages (1-5000)
        #[arg(short, long, default_value_t = 200)]
        limit: u32,

        /// Skip this many messages (pagination)
        #[arg(long, default_value_t = 0)]
        offset: u32,

        /// Sort order by date
        #[arg(long, default_value = "asc")]
        order: String,
    },

    // =========================================================================
    // SETUP COMMAND
    // =========================================================================
    /// Configure Messages database access (one-time setup)
    Setup {
        /// Skip confirmation prompts
        #[arg(short, long)]
        yes: bool,

        /// Reconfigure even if already set up
        #[arg(short, long)]
        force: bool,
    },

    // =========================================================================
    // RAG COMMANDS - Delegate to Python daemon
    // =========================================================================
    /// Index content for semantic search (via daemon)
    Index {
        /// Source to index
        #[arg(short, long)]
        source: String,

        /// Days of history to index
        #[arg(short, long, default_value_t = 30)]
        days: u32,

        /// Maximum items to index
        #[arg(short, long)]
        limit: Option<u32>,

        /// For iMessage: index only this contact
        #[arg(short, long)]
        contact: Option<String>,

        /// Full reindex (ignore incremental state)
        #[arg(long)]
        full: bool,
    },

    /// Semantic search across indexed content (via daemon)
    Search {
        /// Search query
        query: String,

        /// Comma-separated sources to search
        #[arg(long)]
        sources: Option<String>,

        /// Only search content from last N days
        #[arg(short, long)]
        days: Option<u32>,

        /// Max results
        #[arg(short, long, default_value_t = 10)]
        limit: u32,
    },

    /// Get AI-formatted context from knowledge base (via daemon)
    Ask {
        /// Question to answer
        question: String,

        /// Comma-separated sources to search
        #[arg(long)]
        sources: Option<String>,

        /// Only search content from last N days
        #[arg(short, long)]
        days: Option<u32>,

        /// Max results to include
        #[arg(short, long, default_value_t = 5)]
        limit: u32,
    },

    /// Show knowledge base statistics (via daemon)
    Stats {
        /// Show stats for specific source
        #[arg(short, long)]
        source: Option<String>,
    },

    /// Clear indexed data (via daemon)
    Clear {
        /// Clear only this source
        #[arg(short, long)]
        source: Option<String>,

        /// Skip confirmation prompt
        #[arg(short, long)]
        force: bool,
    },

    /// List available and indexed sources (via daemon)
    Sources,
}

fn main() -> ExitCode {
    // Initialize tracing/logging
    tracing_subscriber::fmt()
        .with_env_filter(
            tracing_subscriber::EnvFilter::from_default_env()
                .add_directive(tracing::Level::WARN.into()),
        )
        .init();

    let cli = Cli::parse();

    // Build output controls from global flags
    let output_controls = output::OutputControls {
        json: cli.json,
        compact: cli.compact,
        minimal: cli.minimal,
        fields: cli.fields.clone(),
        max_text_chars: cli.max_text_chars,
    };

    // Load contacts once (shared across commands)
    let contacts = Arc::new(
        contacts::manager::ContactsManager::load_default()
            .unwrap_or_else(|_| contacts::manager::ContactsManager::empty())
    );

    let result = match cli.command {
        // Core reading commands
        Command::Find { contact, query, limit } => {
            commands::reading::find(&contact, query.as_deref(), limit, &output_controls)
        }
        Command::Messages { contact, limit } => {
            commands::reading::messages(&contact, limit, &output_controls)
        }
        Command::Recent { limit } => {
            commands::reading::recent(limit, &output_controls)
        }
        Command::Unread { limit } => {
            commands::reading::unread(limit, &output_controls)
        }
        Command::TextSearch { query, contact, limit, days, since } => {
            commands::reading::text_search(&query, contact.as_deref(), limit, days, since.as_deref(), &output_controls)
        }
        Command::Bundle { contact, query, days, since, unread_limit, recent_limit, search_limit, messages_limit, search_scoped_to_contact, include } => {
            commands::reading::bundle(
                contact.as_deref(), query.as_deref(), days, since.as_deref(),
                unread_limit, recent_limit, search_limit, messages_limit,
                search_scoped_to_contact, include.as_deref(), &output_controls
            )
        }

        // Messaging commands
        Command::Send { contact, message } => {
            commands::messaging::send(&contact, &message.join(" "), &output_controls)
        }
        Command::SendByPhone { phone, message } => {
            commands::messaging::send_by_phone(&phone, &message.join(" "), &output_controls)
        }

        // Contact commands
        Command::Contacts => {
            commands::contacts::list(&output_controls)
        }
        Command::AddContact { name, phone, relationship, notes } => {
            commands::contacts::add(&name, &phone, &relationship, notes.as_deref())
        }

        // Analytics commands
        Command::Analytics { contact, days } => {
            commands::analytics::analytics(contact.as_deref(), days, cli.json, &contacts)
        }
        Command::Followup { days, stale } => {
            commands::analytics::followup(days, stale, cli.json, &contacts)
        }

        // Group commands
        Command::Groups { limit } => {
            commands::groups::list(limit, cli.json)
        }
        Command::GroupMessages { group_id, participant, limit } => {
            commands::groups::messages(group_id.as_deref(), participant.as_deref(), limit, cli.json)
        }

        // T1 commands
        Command::Attachments { contact, mime_type, limit } => {
            commands::reading::attachments(contact.as_deref(), mime_type.as_deref(), limit, cli.json)
        }
        Command::Reactions { contact, limit } => {
            commands::reading::reactions(contact.as_deref(), limit, cli.json)
        }
        Command::Links { contact, days, all_time, limit } => {
            commands::reading::links(contact.as_deref(), days, all_time, limit, cli.json)
        }
        Command::Voice { contact, limit } => {
            commands::reading::voice(contact.as_deref(), limit, cli.json)
        }
        Command::Thread { guid, limit } => {
            commands::reading::thread(&guid, limit, cli.json)
        }

        // T2 commands
        Command::Handles { days, limit } => {
            commands::discovery::handles(days, limit, cli.json)
        }
        Command::Unknown { days, limit } => {
            commands::discovery::unknown(days, limit, cli.json, &contacts)
        }
        Command::Discover { days, limit, min_messages } => {
            commands::discovery::discover(days, limit, min_messages, cli.json, &contacts)
        }
        Command::Scheduled => {
            commands::discovery::scheduled(cli.json)
        }
        Command::Summary { contact, days, start, end, limit, offset, order } => {
            commands::reading::summary(&contact, days, start.as_deref(), end.as_deref(), limit, offset, &order, cli.json)
        }

        // Setup command
        Command::Setup { yes, force } => {
            commands::setup::run(yes, force, cli.json)
        }

        // RAG commands (delegate to daemon)
        Command::Index { source, days, limit, contact, full } => {
            commands::rag::index(&source, days, limit, contact.as_deref(), full, cli.json)
        }
        Command::Search { query, sources, days, limit } => {
            commands::rag::search(&query, sources.as_deref(), days, limit, cli.json)
        }
        Command::Ask { question, sources, days, limit } => {
            commands::rag::ask(&question, sources.as_deref(), days, limit, cli.json)
        }
        Command::Stats { source } => {
            commands::rag::stats(source.as_deref(), cli.json)
        }
        Command::Clear { source, force } => {
            commands::rag::clear(source.as_deref(), force, cli.json)
        }
        Command::Sources => {
            commands::rag::sources(cli.json)
        }
    };

    match result {
        Ok(()) => ExitCode::from(0),
        Err(e) => {
            eprintln!("Error: {}", e);
            ExitCode::from(1)
        }
    }
}

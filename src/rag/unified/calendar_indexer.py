"""
Calendar events indexer.

Indexes calendar events (Google Calendar, iCal, etc.) with event
titles, descriptions, attendees, and notes.

Note: This indexer is designed to work with calendar data fetched
via external APIs or MCP tools.
"""

import logging
from datetime import datetime
from typing import List, Dict, Any, Optional, Callable

from .base_indexer import BaseSourceIndexer
from .chunk import UnifiedChunk

logger = logging.getLogger(__name__)


class CalendarIndexer(BaseSourceIndexer):
    """
    Indexes calendar events.

    Each event becomes one chunk containing the title, description,
    notes, and meeting information.

    Args:
        calendar_fetcher: Function to fetch calendar events
        store: Optional UnifiedVectorStore to use
        use_local_embeddings: Use local embeddings instead of OpenAI

    Example:
        indexer = CalendarIndexer()
        events = [...]  # Fetched via Google Calendar API
        result = indexer.index_with_data(events)
    """

    source_name = "calendar"

    def __init__(
        self,
        calendar_fetcher: Optional[Callable] = None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.calendar_fetcher = calendar_fetcher

    def fetch_data(
        self,
        days: Optional[int] = None,
        limit: Optional[int] = None,
        **kwargs,
    ) -> List[Dict[str, Any]]:
        """
        Fetch events - requires calendar_fetcher to be set.

        For direct use, call index_with_data() with pre-fetched events.
        """
        logger.warning(
            "CalendarIndexer.fetch_data() is a stub. "
            "Use index_with_data() with pre-fetched events."
        )
        return []

    def index_with_data(
        self,
        events: List[Dict[str, Any]],
        batch_size: int = 100,
    ) -> Dict[str, Any]:
        """
        Index pre-fetched calendar events.

        Args:
            events: List of calendar event dicts
            batch_size: Batch size for embeddings

        Returns:
            Dict with indexing stats
        """
        start_time = datetime.now()

        if not events:
            return {
                "success": True,
                "source": self.source_name,
                "chunks_found": 0,
                "chunks_indexed": 0,
                "duration_seconds": 0,
            }

        # Convert to chunks
        chunks = self.chunk_data(events)

        if not chunks:
            return {
                "success": True,
                "source": self.source_name,
                "chunks_found": 0,
                "chunks_indexed": 0,
                "duration_seconds": 0,
            }

        # Index chunks
        result = self.store.add_chunks(chunks, batch_size=batch_size)
        indexed_count = result.get(self.source_name, 0)

        duration = (datetime.now() - start_time).total_seconds()

        return {
            "success": True,
            "source": self.source_name,
            "chunks_found": len(chunks),
            "chunks_indexed": indexed_count,
            "duration_seconds": duration,
        }

    def chunk_data(self, events: List[Dict[str, Any]]) -> List[UnifiedChunk]:
        """Convert calendar events to UnifiedChunks."""
        chunks = []

        for event in events:
            chunk = self._event_to_chunk(event)
            if chunk:
                chunks.append(chunk)

        logger.info(f"Created {len(chunks)} chunks from {len(events)} events")
        return chunks

    def _event_to_chunk(self, event: Dict[str, Any]) -> Optional[UnifiedChunk]:
        """Convert a single calendar event to a UnifiedChunk."""
        # Get title/summary
        title = (
            event.get("title") or
            event.get("summary") or
            event.get("subject", "")
        )

        if not title:
            return None

        # Get description and notes
        description = event.get("description", "") or ""
        notes = event.get("notes", "") or ""

        # Build full text
        text_parts = [title]
        if description:
            text_parts.append(description)
        if notes:
            text_parts.append(f"Notes: {notes}")

        full_text = "\n\n".join(text_parts)

        # Skip events with minimal content
        if len(full_text.split()) < 5:
            return None

        # Parse dates
        start_time = self._parse_event_date(
            event.get("start") or event.get("start_time") or event.get("startTime")
        )
        end_time = self._parse_event_date(
            event.get("end") or event.get("end_time") or event.get("endTime")
        )

        if not start_time:
            return None

        # Get attendees
        attendees = self._extract_attendees(event.get("attendees", []))

        # Get location
        location = (
            event.get("location") or
            event.get("hangoutLink") or
            event.get("conferenceData", {}).get("entryPoints", [{}])[0].get("uri", "")
        )

        # Get calendar name as tag
        calendar_name = (
            event.get("calendar") or
            event.get("calendarId") or
            event.get("organizer", {}).get("email", "primary")
        )

        # Get event ID
        event_id = (
            event.get("id") or
            event.get("iCalUID") or
            event.get("eventId", "")
        )

        return UnifiedChunk(
            source="calendar",
            text=full_text,
            title=title,
            context_id=str(event_id),
            context_type="event",
            timestamp=start_time,
            end_timestamp=end_time,
            participants=attendees,
            tags=[calendar_name] if calendar_name else [],
            metadata={
                "location": location[:200] if location else "",
                "is_recurring": bool(event.get("recurrence") or event.get("recurringEventId")),
                "is_all_day": self._is_all_day(event),
                "status": event.get("status", ""),
                "organizer": self._get_organizer(event),
                "has_meet_link": bool(event.get("hangoutLink") or event.get("conferenceData")),
            },
        )

    def _parse_event_date(self, date_value: Any) -> Optional[datetime]:
        """Parse various calendar date formats."""
        if not date_value:
            return None

        # Handle Google Calendar nested format
        if isinstance(date_value, dict):
            date_str = date_value.get("dateTime") or date_value.get("date")
        else:
            date_str = str(date_value)

        if not date_str:
            return None

        # Try ISO format
        try:
            return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        except ValueError:
            pass

        # Try date-only format (all-day events)
        try:
            return datetime.strptime(date_str[:10], "%Y-%m-%d")
        except ValueError:
            pass

        return None

    def _extract_attendees(self, attendees: Any) -> List[str]:
        """Extract attendee names/emails from various formats."""
        if not attendees:
            return []

        if isinstance(attendees, str):
            return [attendees]

        result = []
        for attendee in attendees:
            if isinstance(attendee, str):
                result.append(attendee)
            elif isinstance(attendee, dict):
                # Google Calendar format
                name = attendee.get("displayName") or attendee.get("email", "")
                if name:
                    result.append(name)

        return result

    def _is_all_day(self, event: Dict) -> bool:
        """Check if event is all-day."""
        start = event.get("start", {})
        if isinstance(start, dict):
            return "date" in start and "dateTime" not in start
        return False

    def _get_organizer(self, event: Dict) -> str:
        """Get event organizer."""
        organizer = event.get("organizer", {})
        if isinstance(organizer, dict):
            return organizer.get("displayName") or organizer.get("email", "")
        elif isinstance(organizer, str):
            return organizer
        return ""

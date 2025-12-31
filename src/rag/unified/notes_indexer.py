"""
Markdown notes/documents indexer.

Indexes markdown files from the data/notes/ directory structure:
- journals/
- meetings/
- notes/
- references/
- reflections/
- reviews/

Chunks documents by headers (H1/H2) or fixed-size windows.
"""

import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

from .base_indexer import BaseSourceIndexer
from .chunk import UnifiedChunk

logger = logging.getLogger(__name__)


class NotesIndexer(BaseSourceIndexer):
    """
    Indexes markdown documents from the notes directory.

    Documents are chunked by:
    1. H1/H2 headers (if document is well-structured)
    2. Fixed-size windows (if document lacks headers)

    The folder name is used as a tag (journals, meetings, etc.)

    Args:
        notes_path: Path to notes directory
        min_chunk_words: Minimum words for a valid chunk
        max_chunk_words: Maximum words before splitting
        store: Optional UnifiedVectorStore to use
        use_local_embeddings: Use local embeddings instead of OpenAI

    Example:
        indexer = NotesIndexer(notes_path=Path("data/notes"))
        result = indexer.index()
        print(f"Indexed {result['chunks_indexed']} note sections")
    """

    source_name = "notes"

    def __init__(
        self,
        notes_path: Optional[Path] = None,
        min_chunk_words: int = 20,
        max_chunk_words: int = 500,
        **kwargs,
    ):
        super().__init__(**kwargs)

        # Default notes path relative to project
        if notes_path is None:
            project_root = Path(__file__).parent.parent.parent.parent.parent
            notes_path = project_root / "data" / "notes"

        self.notes_path = notes_path
        self.min_chunk_words = min_chunk_words
        self.max_chunk_words = max_chunk_words

        if not self.notes_path.exists():
            logger.warning(f"Notes directory not found at {self.notes_path}")

    def fetch_data(
        self,
        days: Optional[int] = None,
        limit: Optional[int] = None,
        **kwargs,
    ) -> List[Dict[str, Any]]:
        """
        Load markdown files from the notes directory.

        Args:
            days: Only fetch files modified in last N days
            limit: Maximum number of files to fetch

        Returns:
            List of document dicts with path, content, and metadata
        """
        if not self.notes_path.exists():
            return []

        documents = []
        cutoff_date = None
        if days:
            cutoff_date = self.days_ago(days)

        # Find all markdown files
        md_files = list(self.notes_path.rglob("*.md"))

        # Sort by modification time (most recent first)
        md_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)

        for file_path in md_files:
            try:
                # Get file stats
                stat = file_path.stat()
                mtime = datetime.fromtimestamp(stat.st_mtime)

                # Apply date filter
                if cutoff_date and mtime < cutoff_date:
                    continue

                # Read content
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()

                # Skip empty files
                if len(content.strip()) < 20:
                    continue

                # Get folder name as category
                relative_path = file_path.relative_to(self.notes_path)
                folder = relative_path.parts[0] if len(relative_path.parts) > 1 else "notes"

                documents.append({
                    "path": str(file_path),
                    "relative_path": str(relative_path),
                    "filename": file_path.stem,
                    "folder": folder,
                    "content": content,
                    "mtime": mtime,
                    "size": stat.st_size,
                })

                if limit and len(documents) >= limit:
                    break

            except (IOError, OSError) as e:
                logger.warning(f"Failed to read {file_path}: {e}")
                continue

        logger.info(f"Found {len(documents)} markdown documents")
        return documents

    def chunk_data(self, documents: List[Dict[str, Any]]) -> List[UnifiedChunk]:
        """
        Convert documents to UnifiedChunks.

        Each document may produce multiple chunks if it has
        multiple sections or is very long.
        """
        chunks = []

        for doc in documents:
            doc_chunks = self._document_to_chunks(doc)
            chunks.extend(doc_chunks)

        logger.info(f"Created {len(chunks)} chunks from {len(documents)} documents")
        return chunks

    def _document_to_chunks(self, doc: Dict[str, Any]) -> List[UnifiedChunk]:
        """Split a document into chunks by headers or size."""
        content = doc["content"]
        sections = self._split_by_headers(content)

        chunks = []
        for i, (header, text) in enumerate(sections):
            # Skip sections that are too short
            word_count = len(text.split())
            if word_count < self.min_chunk_words:
                continue

            # Split large sections
            if word_count > self.max_chunk_words:
                sub_chunks = self._split_by_size(text, header)
                for j, (sub_header, sub_text) in enumerate(sub_chunks):
                    chunk = self._create_chunk(
                        doc, sub_text, sub_header, f"{i}_{j}"
                    )
                    if chunk:
                        chunks.append(chunk)
            else:
                chunk = self._create_chunk(doc, text, header, str(i))
                if chunk:
                    chunks.append(chunk)

        return chunks

    def _split_by_headers(self, content: str) -> List[Tuple[Optional[str], str]]:
        """
        Split markdown by H1/H2 headers.

        Returns list of (header, content) tuples.
        """
        # Pattern matches # or ## headers
        header_pattern = re.compile(r'^(#{1,2})\s+(.+)$', re.MULTILINE)

        sections = []
        last_pos = 0
        last_header = None

        for match in header_pattern.finditer(content):
            # Get content before this header
            if match.start() > last_pos:
                text = content[last_pos:match.start()].strip()
                if text:
                    sections.append((last_header, text))

            last_header = match.group(2).strip()
            last_pos = match.end()

        # Get remaining content after last header
        if last_pos < len(content):
            text = content[last_pos:].strip()
            if text:
                sections.append((last_header, text))

        # If no headers found, return entire content
        if not sections:
            sections = [(None, content.strip())]

        return sections

    def _split_by_size(
        self,
        text: str,
        header: Optional[str],
    ) -> List[Tuple[Optional[str], str]]:
        """
        Split text by word count, preserving paragraph boundaries.
        """
        paragraphs = text.split("\n\n")
        chunks = []
        current_text = ""
        current_words = 0

        for para in paragraphs:
            para_words = len(para.split())

            if current_words + para_words > self.max_chunk_words and current_text:
                # Save current chunk
                chunk_header = f"{header} (part {len(chunks) + 1})" if header else None
                chunks.append((chunk_header, current_text.strip()))
                current_text = para
                current_words = para_words
            else:
                if current_text:
                    current_text += "\n\n" + para
                else:
                    current_text = para
                current_words += para_words

        # Add remaining text
        if current_text.strip():
            chunk_header = header
            if len(chunks) > 0:
                chunk_header = f"{header} (part {len(chunks) + 1})" if header else None
            chunks.append((chunk_header, current_text.strip()))

        return chunks

    def _create_chunk(
        self,
        doc: Dict[str, Any],
        text: str,
        header: Optional[str],
        section_id: str,
    ) -> Optional[UnifiedChunk]:
        """Create a UnifiedChunk from document section."""
        if not text or len(text.strip()) < 20:
            return None

        # Use header or filename as title
        title = header or doc["filename"]

        # Extract date from filename if present (e.g., 2024-12-30_meeting_notes.md)
        doc_date = self._extract_date_from_filename(doc["filename"])
        if not doc_date:
            doc_date = doc["mtime"]

        return UnifiedChunk(
            source="notes",
            text=text,
            title=title,
            context_id=doc["relative_path"],
            context_type="document",
            timestamp=doc_date,
            participants=[],
            tags=[doc["folder"]],
            metadata={
                "filename": doc["filename"],
                "folder": doc["folder"],
                "section_id": section_id,
                "full_path": doc["path"],
            },
        )

    def _extract_date_from_filename(self, filename: str) -> Optional[datetime]:
        """
        Try to extract date from filename.

        Supports formats:
        - 2024-12-30_notes.md
        - 2024_12_30_meeting.md
        - 20241230_notes.md
        """
        patterns = [
            (r'(\d{4})-(\d{2})-(\d{2})', '%Y-%m-%d'),
            (r'(\d{4})_(\d{2})_(\d{2})', '%Y_%m_%d'),
            (r'(\d{8})', '%Y%m%d'),
        ]

        for pattern, date_format in patterns:
            match = re.search(pattern, filename)
            if match:
                try:
                    date_str = match.group(0)
                    return datetime.strptime(date_str, date_format)
                except ValueError:
                    continue

        return None

"""
Directory Traversal Module.

Recursively scans extracted archive directories for parseable files,
filtering out OS junk and hidden files.
"""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Generator


@dataclass
class FileInfo:
    """Metadata about a discovered file."""
    path: Path
    extension: str       # lowercase, without dot (e.g., "md", "yaml")
    size_bytes: int
    relative_path: str   # relative to archive root, for metadata


# System and IDE junk to ignore
JUNK_FILES = {".DS_Store", "Thumbs.db", "desktop.ini", ".gitkeep"}
JUNK_DIRS = {"__MACOSX", ".git", "__pycache__", "node_modules", ".svn"}


def walk_files(root: Path) -> Generator[FileInfo, None, None]:
    """
    Recursively walk a directory, yielding FileInfo for each valid file.

    Prunes junk directories in-place for efficiency and skips hidden/junk files.

    Args:
        root: Root directory to scan.

    Yields:
        FileInfo objects for each valid file found.
    """
    for dirpath, dirnames, filenames in os.walk(root):
        # Prune junk directories in-place to prevent descending into them
        dirnames[:] = [d for d in dirnames if d not in JUNK_DIRS]

        for filename in filenames:
            # Skip junk and hidden files
            if filename in JUNK_FILES or filename.startswith("."):
                continue

            filepath = Path(dirpath) / filename
            ext = filepath.suffix.lstrip(".").lower()

            # Skip files with no extension
            if not ext:
                continue

            yield FileInfo(
                path=filepath,
                extension=ext,
                size_bytes=filepath.stat().st_size,
                relative_path=str(filepath.relative_to(root)),
            )

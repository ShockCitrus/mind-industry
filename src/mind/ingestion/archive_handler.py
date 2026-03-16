"""
Archive Extraction Module.

Securely decompresses uploaded archives (.zip, .tar, .7z) to a temporary
directory with protections against zip bombs, path traversal, and excessive
file counts.
"""

import os
import logging
import tarfile
import tempfile
import zipfile
from pathlib import Path

logger = logging.getLogger(__name__)

# Safety limits
MAX_EXTRACTED_SIZE = 100 * 1024 * 1024   # 100 MB
MAX_EXTRACTED_FILES = 5000

# Supported archive extensions (without leading dot)
ARCHIVE_EXTENSIONS = {"zip", "tar", "gz", "bz2", "xz", "7z"}


def is_archive(extension: str) -> bool:
    """Check if a file extension corresponds to a supported archive format."""
    return extension.lower() in ARCHIVE_EXTENSIONS


def extract_archive(file_path: Path) -> Path:
    """
    Extract an archive to a secure temporary directory.

    The caller is responsible for cleaning up the returned directory
    (use shutil.rmtree in a finally block).

    Args:
        file_path: Path to the archive file.

    Returns:
        Path to the temporary directory containing extracted contents.

    Raises:
        ValueError: If the archive format is unsupported, exceeds size/file
                     limits, or contains path traversal attempts.
    """
    temp_dir = Path(tempfile.mkdtemp(prefix="mind_ingest_"))
    ext = file_path.suffix.lstrip(".").lower()

    # Handle compound extensions like .tar.gz, .tar.bz2, .tar.xz
    name_lower = file_path.name.lower()
    if name_lower.endswith((".tar.gz", ".tar.bz2", ".tar.xz")):
        _extract_tar(file_path, temp_dir)
    elif ext == "tar":
        _extract_tar(file_path, temp_dir)
    elif ext == "zip":
        _extract_zip(file_path, temp_dir)
    elif ext == "7z":
        _extract_7z(file_path, temp_dir)
    else:
        raise ValueError(
            f"Unsupported archive format: '.{ext}'. "
            f"Supported formats: .zip, .tar, .tar.gz, .tar.bz2, .tar.xz, .7z"
        )

    logger.info(f"Extracted archive '{file_path.name}' to {temp_dir}")
    return temp_dir


def _extract_zip(file_path: Path, dest_dir: Path) -> None:
    """Extract a .zip archive with zip bomb and path traversal protection."""
    with zipfile.ZipFile(file_path, "r") as zf:
        # Zip bomb check: sum uncompressed sizes
        total_size = sum(info.file_size for info in zf.infolist())
        if total_size > MAX_EXTRACTED_SIZE:
            raise ValueError(
                f"Archive uncompressed size ({total_size / 1024 / 1024:.1f} MB) "
                f"exceeds the {MAX_EXTRACTED_SIZE / 1024 / 1024:.0f} MB limit. "
                f"This may be a zip bomb."
            )

        # File count check
        file_count = len(zf.infolist())
        if file_count > MAX_EXTRACTED_FILES:
            raise ValueError(
                f"Archive contains {file_count} files, exceeding the "
                f"{MAX_EXTRACTED_FILES} file limit."
            )

        # Path traversal check
        for info in zf.infolist():
            target = (dest_dir / info.filename).resolve()
            if not str(target).startswith(str(dest_dir.resolve())):
                raise ValueError(
                    f"Path traversal detected in archive: '{info.filename}'"
                )

        zf.extractall(dest_dir)


def _extract_tar(file_path: Path, dest_dir: Path) -> None:
    """Extract a .tar/.tar.gz/.tar.bz2/.tar.xz archive with safety checks."""
    with tarfile.open(file_path, "r:*") as tf:
        members = tf.getmembers()

        # File count check
        if len(members) > MAX_EXTRACTED_FILES:
            raise ValueError(
                f"Archive contains {len(members)} files, exceeding the "
                f"{MAX_EXTRACTED_FILES} file limit."
            )

        # Size and path traversal checks
        total_size = 0
        for member in members:
            total_size += member.size
            if total_size > MAX_EXTRACTED_SIZE:
                raise ValueError(
                    f"Archive uncompressed size exceeds the "
                    f"{MAX_EXTRACTED_SIZE / 1024 / 1024:.0f} MB limit."
                )

            # Path traversal: reject absolute paths or '..' components
            if member.name.startswith("/") or ".." in member.name.split("/"):
                raise ValueError(
                    f"Path traversal detected in archive: '{member.name}'"
                )

            # Verify resolved path stays within dest_dir
            target = (dest_dir / member.name).resolve()
            if not str(target).startswith(str(dest_dir.resolve())):
                raise ValueError(
                    f"Path traversal detected in archive: '{member.name}'"
                )

        tf.extractall(dest_dir, filter="data")


def _extract_7z(file_path: Path, dest_dir: Path) -> None:
    """Extract a .7z archive with safety checks."""
    try:
        import py7zr
    except ImportError:
        raise ImportError(
            "py7zr package is required for .7z support. "
            "Install with: pip install py7zr"
        )

    with py7zr.SevenZipFile(file_path, mode="r") as szf:
        # File count check
        file_count = len(szf.getnames())
        if file_count > MAX_EXTRACTED_FILES:
            raise ValueError(
                f"Archive contains {file_count} files, exceeding the "
                f"{MAX_EXTRACTED_FILES} file limit."
            )

        # Path traversal check on names
        for name in szf.getnames():
            if name.startswith("/") or ".." in name.split("/"):
                raise ValueError(
                    f"Path traversal detected in archive: '{name}'"
                )
            target = (dest_dir / name).resolve()
            if not str(target).startswith(str(dest_dir.resolve())):
                raise ValueError(
                    f"Path traversal detected in archive: '{name}'"
                )

        szf.extractall(path=dest_dir)

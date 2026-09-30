"""
TelecomAI Security Utilities
Provides file validation, magic-byte inspection, path traversal protection,
and secret masking.
"""

import os
import re
from typing import Tuple, Optional

# File Upload Constraints
MAX_IMAGE_SIZE_BYTES = 15 * 1024 * 1024  # 15 MB
MAX_AUDIO_SIZE_BYTES = 25 * 1024 * 1024  # 25 MB

ALLOWED_IMAGE_MIMES = {
    "image/jpeg": [b"\xff\xd8\xff"],
    "image/jpg": [b"\xff\xd8\xff"],
    "image/png": [b"\x89PNG\r\n\x1a\n"],
    "image/webp": [b"RIFF"],
}

ALLOWED_AUDIO_PREFIXES = [
    b"RIFF",     # WAV
    b"ID3",      # MP3 with ID3
    b"\xff\xfb", # MP3 frame
    b"\xff\xf3", # MP3 frame
    b"\xff\xf2", # MP3 frame
    b"OggS",     # Ogg Vorbis
    b"\x1a\x45\xdf\xa3", # WebM / Matroska
]


def validate_image_file(
    image_bytes: bytes,
    mime_type: Optional[str] = None,
) -> Tuple[bool, str]:
    """
    Validate uploaded image bytes against size limits, MIME type,
    and binary magic header bytes.
    """
    if not image_bytes or len(image_bytes) == 0:
        return False, "Empty image file provided"

    if len(image_bytes) > MAX_IMAGE_SIZE_BYTES:
        return False, f"Image exceeds maximum allowable size of {MAX_IMAGE_SIZE_BYTES // (1024 * 1024)} MB"

    # Normalize mime type
    mime = (mime_type or "image/jpeg").lower().strip()
    if mime not in ALLOWED_IMAGE_MIMES:
        return False, f"Unsupported image MIME type '{mime}'. Allowed: {list(ALLOWED_IMAGE_MIMES.keys())}"

    # Verify binary magic bytes
    expected_signatures = ALLOWED_IMAGE_MIMES[mime]
    matches_magic = any(image_bytes.startswith(sig) for sig in expected_signatures)

    # For webp, also check for WEBP chunk header at offset 8
    if mime == "image/webp" and matches_magic:
        if len(image_bytes) < 12 or image_bytes[8:12] != b"WEBP":
            return False, "Invalid WebP image file signature"

    if not matches_magic:
        return False, f"File content does not match declared MIME type '{mime}'"

    return True, "Valid image"


def validate_audio_file(
    audio_bytes: bytes,
    max_size_bytes: int = MAX_AUDIO_SIZE_BYTES,
) -> Tuple[bool, str]:
    """
    Validate uploaded audio bytes for voice processing.
    """
    if not audio_bytes or len(audio_bytes) == 0:
        return False, "Empty audio stream"

    if len(audio_bytes) > max_size_bytes:
        return False, f"Audio file exceeds maximum size of {max_size_bytes // (1024 * 1024)} MB"

    # Check magic bytes
    matches_audio = any(audio_bytes.startswith(sig) for sig in ALLOWED_AUDIO_PREFIXES)
    if not matches_audio:
        # Permissive for raw PCM chunks in certain browser environments, but verify minimum structure
        if len(audio_bytes) < 16:
            return False, "Audio chunk too short or unrecognized format"

    return True, "Valid audio"


def sanitize_filename(filename: str) -> str:
    """
    Sanitize filename to prevent directory traversal and special character exploits.
    """
    if not filename:
        return "unnamed_file"

    # Remove path separators
    clean_name = os.path.basename(filename)
    # Strip dangerous characters
    clean_name = re.sub(r"[^\w\.\-_]", "_", clean_name)
    # Prevent leading dots (hidden files or traversal)
    clean_name = clean_name.lstrip(".")
    return clean_name or "safe_file"


def mask_sensitive_token(token: Optional[str]) -> str:
    """
    Mask API keys and JWT tokens for safe logging and status reporting.
    """
    if not token or len(token) < 8:
        return "***"
    return f"{token[:4]}...{token[-4:]}"

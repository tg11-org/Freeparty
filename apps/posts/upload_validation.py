from __future__ import annotations

from pathlib import Path

from apps.posts.models import Attachment

MAX_ATTACHMENT_BYTES = 25 * 1024 * 1024

_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
_VIDEO_EXTENSIONS = {".mp4", ".webm", ".mov"}

_CANONICAL_MIME_BY_EXTENSION = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".mp4": "video/mp4",
    ".webm": "video/webm",
    ".mov": "video/quicktime",
}


def _looks_like_image(ext: str, header: bytes) -> bool:
    if ext in {".jpg", ".jpeg"}:
        return header.startswith(b"\xff\xd8\xff")
    if ext == ".png":
        return header.startswith(b"\x89PNG\r\n\x1a\n")
    if ext == ".gif":
        return header.startswith((b"GIF87a", b"GIF89a"))
    if ext == ".webp":
        return len(header) >= 12 and header.startswith(b"RIFF") and header[8:12] == b"WEBP"
    return False


def _looks_like_video(ext: str, header: bytes) -> bool:
    if ext in {".mp4", ".mov"}:
        return len(header) >= 12 and header[4:8] == b"ftyp"
    if ext == ".webm":
        return header.startswith(b"\x1a\x45\xdf\xa3")
    return False


def validate_post_media_upload(upload) -> tuple[str, str]:
    if not upload:
        raise ValueError("No file was uploaded.")

    size = int(getattr(upload, "size", 0) or 0)
    if size > MAX_ATTACHMENT_BYTES:
        raise ValueError("Attachment is too large (max 25 MB).")

    ext = Path((getattr(upload, "name", "") or "").lower()).suffix
    if ext not in _IMAGE_EXTENSIONS | _VIDEO_EXTENSIONS:
        raise ValueError("Unsupported file type. Allowed: jpg/jpeg/png/gif/webp/mp4/webm/mov.")

    content_type = (getattr(upload, "content_type", "") or "").lower().strip()
    if content_type and not (content_type.startswith("image/") or content_type.startswith("video/")):
        raise ValueError("Only image and video uploads are supported.")

    header = upload.read(512)
    upload.seek(0)

    if ext in _IMAGE_EXTENSIONS:
        if not _looks_like_image(ext, header):
            raise ValueError("Uploaded image does not match its file type.")
        return Attachment.AttachmentType.IMAGE, _CANONICAL_MIME_BY_EXTENSION[ext]

    if not _looks_like_video(ext, header):
        raise ValueError("Uploaded video does not match its file type.")
    return Attachment.AttachmentType.VIDEO, _CANONICAL_MIME_BY_EXTENSION[ext]

import mimetypes
import struct


BINARY_CONTENT_TYPE = 'application/octet-stream'
INLINE_CONTENT_TYPES = {
    'image/png',
    'image/jpeg',
    'image/gif',
    'image/webp',
    'application/pdf',
}


def stored_content_type(filename: str, uploaded_content_type: str | None) -> str:
    candidate = (uploaded_content_type or '').split(';', 1)[0].strip().lower()
    if candidate in ('', BINARY_CONTENT_TYPE):
        candidate = (mimetypes.guess_type(filename)[0] or BINARY_CONTENT_TYPE).lower()
    if len(candidate) > 255 or '/' not in candidate or any(ord(char) < 32 for char in candidate):
        return BINARY_CONTENT_TYPE
    return candidate


def verified_inline_content_type(content: bytes) -> str | None:
    size = len(content)
    head = content[:16]
    tail = content[max(0, size - 1024):]

    if head.startswith(b'\x89PNG\r\n\x1a\n') and tail.endswith(b'IEND\xaeB`\x82'):
        return 'image/png'
    if head.startswith(b'\xff\xd8\xff') and tail.endswith(b'\xff\xd9'):
        return 'image/jpeg'
    if head[:6] in (b'GIF87a', b'GIF89a') and tail.endswith(b';'):
        return 'image/gif'
    if (
        len(head) >= 12
        and head.startswith(b'RIFF')
        and head[8:12] == b'WEBP'
        and struct.unpack('<I', head[4:8])[0] == size - 8
    ):
        return 'image/webp'
    if head.startswith(b'%PDF-') and tail.rstrip().endswith(b'%%EOF'):
        return 'application/pdf'
    return None

from pathlib import PurePosixPath


MAX_IMAGE_SIZE_BYTES = 5 * 1024 * 1024
ALLOWED_IMAGE_TYPES = {
    "image/jpeg": (".jpg", lambda data: data.startswith(b"\xff\xd8\xff")),
    "image/png": (".png", lambda data: data.startswith(b"\x89PNG\r\n\x1a\n")),
    "image/webp": (
        ".webp",
        lambda data: len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP",
    ),
}


def validate_catalog_image(data: bytes, content_type: str) -> str:
    image_format = ALLOWED_IMAGE_TYPES.get(content_type)
    if image_format is None:
        raise ValueError("Only JPEG, PNG, and WebP images are allowed.")
    if not data or len(data) > MAX_IMAGE_SIZE_BYTES:
        raise ValueError("Image must be between 1 byte and 5 MB.")
    extension, signature_check = image_format
    if not signature_check(data):
        raise ValueError("Uploaded file content does not match its image type.")
    return extension


def safe_original_filename(filename: str | None) -> str:
    if not filename:
        return "image"
    clean_name = PurePosixPath(filename.replace("\\", "/")).name
    clean_name = "".join(
        character for character in clean_name if character.isalnum() or character in "._- "
    ).strip()
    return clean_name[:180] or "image"

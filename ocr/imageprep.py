import io
from PIL import Image, ImageOps


def prepare_image(raw: bytes, max_edge: int = 1400) -> bytes:
    """Apply EXIF orientation, downscale so the long edge <= max_edge (never upscale),
    re-encode as JPEG (drops EXIF/GPS metadata)."""
    try:
        img = Image.open(io.BytesIO(raw))
        img = ImageOps.exif_transpose(img)
        img = img.convert("RGB")
    except Exception as e:  # noqa: BLE001
        raise ValueError("Unreadable image file") from e
    w, h = img.size
    long_edge = max(w, h)
    if long_edge > max_edge:
        scale = max_edge / long_edge
        img = img.resize((round(w * scale), round(h * scale)), Image.LANCZOS)
    out = io.BytesIO()
    img.save(out, "JPEG", quality=92)
    return out.getvalue()

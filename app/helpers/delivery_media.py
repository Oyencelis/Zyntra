"""Compress and persist delivery proof images."""
import os
from datetime import datetime

# pyrefly: ignore [missing-import]
try:
    # pyrefly: ignore [missing-import]
    from PIL import Image
except ImportError:
    Image = None

# pyrefly: ignore [missing-import]
from werkzeug.utils import secure_filename
from helpers.HelperFunction import allowed_image_file

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def save_compressed_proof(file_storage, *, max_side: int = 1600, quality: int = 82, subdir: str = "delivery_proofs") -> str | None:
    """
    Saves under static/uploads/{subdir}. Returns web-relative path
    (uploads/{subdir}/...) or None on failure.
    """
    if not file_storage or not getattr(file_storage, "filename", None):
        return None
    if not allowed_image_file(file_storage.filename):
        return None

    upload_dir = os.path.join(BASE_DIR, "static", "uploads", subdir)
    os.makedirs(upload_dir, exist_ok=True)
    ext = (os.path.splitext(file_storage.filename)[1] or ".jpg").lower()
    if ext not in {".jpg", ".jpeg", ".png", ".webp"}:
        ext = ".jpg"

    stamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    out_name = f"pod_{stamp}_{os.urandom(4).hex()}.jpg"
    out_path = os.path.join(upload_dir, secure_filename(out_name))

    if Image is None:
        file_storage.save(out_path)
        return f"uploads/{subdir}/{out_name}"

    try:
        img = Image.open(file_storage.stream)
        img = img.convert("RGB")
        img.thumbnail((max_side, max_side))
        img.save(out_path, format="JPEG", quality=quality, optimize=True)
    except Exception:
        try:
            file_storage.stream.seek(0)
        except Exception:
            pass
        file_storage.save(out_path)
    return f"uploads/{subdir}/{out_name}"

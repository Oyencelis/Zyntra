import os
import uuid
from typing import Optional, Tuple
from urllib.parse import unquote, urlparse

# pyrefly: ignore [missing-import]
from supabase import Client, create_client
# pyrefly: ignore [missing-import]
from werkzeug.utils import secure_filename


_supabase_client: Optional[Client] = None


def _normalize_public_url(public_url) -> Optional[str]:
    if isinstance(public_url, str):
        return public_url

    if isinstance(public_url, dict):
        for key in ("publicURL", "publicUrl"):
            value = public_url.get(key)
            if isinstance(value, str) and value:
                return value

        data = public_url.get("data")
        if isinstance(data, dict):
            for key in ("publicURL", "publicUrl"):
                value = data.get(key)
                if isinstance(value, str) and value:
                    return value

    return None


def _normalize_signed_url(signed_url) -> Optional[str]:
    if isinstance(signed_url, str):
        return signed_url

    if isinstance(signed_url, dict):
        for key in ("signedURL", "signedUrl"):
            value = signed_url.get(key)
            if isinstance(value, str) and value:
                return value

        data = signed_url.get("data")
        if isinstance(data, dict):
            for key in ("signedURL", "signedUrl"):
                value = data.get(key)
                if isinstance(value, str) and value:
                    return value

    return None


def _extract_bucket_and_object_path(value: str) -> Tuple[Optional[str], Optional[str]]:
    if not value:
        return None, None

    raw_value = value.strip()
    if not raw_value:
        return None, None

    if raw_value.startswith(("http://", "https://")):
        parsed = urlparse(raw_value)
        path = parsed.path or ""
        markers = ["/storage/v1/object/public/", "/storage/v1/object/sign/"]
        for marker in markers:
            if marker in path:
                tail = path.split(marker, 1)[1].strip("/")
                if not tail:
                    return None, None
                parts = tail.split('/', 1)
                bucket = parts[0] if parts else None
                object_path = parts[1] if len(parts) > 1 else None
                return bucket, unquote(object_path) if object_path else None
        return None, None

    clean_value = raw_value.strip('/').replace('\\', '/')
    if '/' not in clean_value:
        return None, clean_value

    bucket, object_path = clean_value.split('/', 1)
    return bucket or None, object_path or None


def resolve_storage_url(value: Optional[str], bucket_name: Optional[str] = None, expires_in: int = 3600) -> Optional[str]:
    if not value:
        return value

    if isinstance(value, str) and value.startswith(("http://", "https://")):
        bucket, object_path = _extract_bucket_and_object_path(value)
        if not bucket or not object_path:
            return value
    else:
        bucket, object_path = _extract_bucket_and_object_path(value)
        if not object_path:
            return value
        bucket = bucket or bucket_name or os.environ.get("SUPABASE_STORAGE_BUCKET", "zyntra-uploads")

    try:
        client = _get_supabase_client()
        signed_url = client.storage.from_(bucket).create_signed_url(object_path, expires_in)
        normalized_signed_url = _normalize_signed_url(signed_url)
        return normalized_signed_url or value
    except Exception:
        if isinstance(value, str) and value.startswith(("http://", "https://")):
            return value

        try:
            client = _get_supabase_client()
            public_url = client.storage.from_(bucket).get_public_url(object_path)
            normalized_public_url = _normalize_public_url(public_url)
            return normalized_public_url or value
        except Exception:
            return value


def _get_supabase_client() -> Client:
    global _supabase_client
    if _supabase_client is not None:
        return _supabase_client

    project_url = os.environ.get("SUPABASE_PROJECT_URL")
    service_role_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")

    if not project_url or not service_role_key:
        raise ValueError("SUPABASE_PROJECT_URL and SUPABASE_SERVICE_ROLE_KEY are required for Storage uploads.")

    _supabase_client = create_client(project_url, service_role_key)
    return _supabase_client


def upload_file_to_supabase(file_storage, folder: str, bucket_name: Optional[str] = None) -> Tuple[Optional[str], Optional[str]]:
    if file_storage is None or not getattr(file_storage, "filename", None):
        return None, "No file provided"

    target_bucket = bucket_name or os.environ.get("SUPABASE_STORAGE_BUCKET", "zyntra-uploads")

    _, ext = os.path.splitext(secure_filename(file_storage.filename))
    ext = ext.lower()
    object_name = f"{uuid.uuid4().hex}{ext}"
    object_path = f"{folder.strip('/')}/{object_name}"

    try:
        client = _get_supabase_client()
        file_storage.stream.seek(0)
        payload = file_storage.read()
        file_storage.stream.seek(0)

        client.storage.from_(target_bucket).upload(
            object_path,
            payload,
            {
                "content-type": file_storage.mimetype or "application/octet-stream",
                "upsert": "false",
            },
        )

        public_url = client.storage.from_(target_bucket).get_public_url(object_path)
        normalized_public_url = _normalize_public_url(public_url)
        if not normalized_public_url:
            return None, f"Unable to determine public URL for uploaded file: {public_url}"

        return normalized_public_url, None
    except Exception as e:
        return None, str(e)

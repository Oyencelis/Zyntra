import os
import uuid
from typing import Optional, Tuple

from supabase import Client, create_client
from werkzeug.utils import secure_filename


_supabase_client: Optional[Client] = None


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
        return public_url, None
    except Exception as e:
        return None, str(e)

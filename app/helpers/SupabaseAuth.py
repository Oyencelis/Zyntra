import os
from typing import Any, Dict, Optional, Tuple

from supabase import Client, create_client


_auth_client: Optional[Client] = None


def _as_dict(value: Any) -> Dict[str, Any]:
    if value is None:
        return {}

    if isinstance(value, dict):
        return value

    if hasattr(value, 'model_dump'):
        try:
            dumped = value.model_dump()
            if isinstance(dumped, dict):
                return dumped
        except Exception:
            pass

    if hasattr(value, 'dict'):
        try:
            dumped = value.dict()
            if isinstance(dumped, dict):
                return dumped
        except Exception:
            pass

    data = getattr(value, '__dict__', None)
    if isinstance(data, dict):
        return data

    return {}


def _pick_first_string(*values: Any) -> Optional[str]:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _get_auth_key() -> Optional[str]:
    return _pick_first_string(
        os.environ.get('SUPABASE_ANON_KEY'),
        os.environ.get('SUPABASE_PUBLISHABLE_KEY'),
        os.environ.get('SUPABASE_SERVICE_ROLE_KEY'),
    )


def get_supabase_auth_client() -> Client:
    global _auth_client
    if _auth_client is not None:
        return _auth_client

    project_url = _pick_first_string(os.environ.get('SUPABASE_PROJECT_URL'))
    auth_key = _get_auth_key()

    if not project_url or not auth_key:
        raise ValueError('SUPABASE_PROJECT_URL and SUPABASE_ANON_KEY (or SUPABASE_PUBLISHABLE_KEY) are required for Supabase Auth.')

    _auth_client = create_client(project_url, auth_key)
    return _auth_client


def _extract_user_data(auth_response: Any) -> Dict[str, Any]:
    if auth_response is None:
        return {}

    user = getattr(auth_response, 'user', None)
    if user is not None:
        user_data = _as_dict(user)
        if user_data:
            return user_data

    response_data = _as_dict(auth_response)
    if isinstance(response_data.get('user'), dict):
        return response_data['user']

    session = getattr(auth_response, 'session', None)
    if session is not None:
        session_data = _as_dict(session)
        if isinstance(session_data.get('user'), dict):
            return session_data['user']

    if isinstance(response_data.get('session'), dict) and isinstance(response_data['session'].get('user'), dict):
        return response_data['session']['user']

    return {}


def _normalize_auth_error(error: Exception) -> str:
    message = str(error).strip() or 'Supabase authentication request failed.'
    lowered = message.lower()

    if 'email not confirmed' in lowered or 'email_not_confirmed' in lowered:
        return 'Please check your email and confirm your Supabase account before logging in.'
    if 'invalid login credentials' in lowered:
        return 'Invalid email or password.'
    if 'user already registered' in lowered:
        return 'Email already exists.'
    if 'email rate limit exceeded' in lowered or 'over_email_send_rate_limit' in lowered:
        return 'Too many confirmation emails were requested from Supabase. Please wait a few minutes before trying again, or use a different email while testing.'
    if 'signup is disabled' in lowered:
        return 'Supabase signup is currently disabled.'

    return message


def sign_up_with_supabase(
    email: str,
    password: str,
    metadata: Optional[Dict[str, Any]] = None,
    redirect_url: Optional[str] = None,
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    try:
        payload: Dict[str, Any] = {
            'email': email,
            'password': password,
        }

        options: Dict[str, Any] = {}
        if metadata:
            options['data'] = metadata
        if redirect_url:
            options['email_redirect_to'] = redirect_url
        if options:
            payload['options'] = options

        response = get_supabase_auth_client().auth.sign_up(payload)
        user_data = _extract_user_data(response)
        if not user_data:
            return None, 'Supabase did not return a user record for signup.'
        return user_data, None
    except Exception as error:
        return None, _normalize_auth_error(error)


def sign_in_with_supabase(email: str, password: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    try:
        response = get_supabase_auth_client().auth.sign_in_with_password({
            'email': email,
            'password': password,
        })
        user_data = _extract_user_data(response)
        if not user_data:
            return None, 'Unable to resolve the authenticated Supabase user.'
        return user_data, None
    except Exception as error:
        return None, _normalize_auth_error(error)

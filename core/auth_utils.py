import functools
import hashlib
import hmac
import json
import os
import secrets

from django.http import JsonResponse


# ---------------------------------------------------------------------------
# Password hashing (PBKDF2-SHA256, stdlib only - no extra dependency needed)
# ---------------------------------------------------------------------------
_ITERATIONS = 260_000


def hash_password(raw_password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", raw_password.encode("utf-8"), salt.encode("utf-8"), _ITERATIONS
    ).hex()
    return f"pbkdf2_sha256${_ITERATIONS}${salt}${digest}"


def verify_password(raw_password: str, encoded: str) -> bool:
    try:
        algo, iterations, salt, digest = encoded.split("$")
        iterations = int(iterations)
    except (ValueError, AttributeError):
        return False
    check = hashlib.pbkdf2_hmac(
        "sha256", raw_password.encode("utf-8"), salt.encode("utf-8"), iterations
    ).hex()
    return hmac.compare_digest(check, digest)


def new_token() -> str:
    return secrets.token_urlsafe(32)


# ---------------------------------------------------------------------------
# Request helpers
# ---------------------------------------------------------------------------
def json_body(request) -> dict:
    if not request.body:
        return {}
    try:
        return json.loads(request.body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {}


def get_bearer_token(request):
    header = request.headers.get("Authorization", "")
    if header.startswith("Bearer "):
        return header[len("Bearer "):].strip()
    return None


def login_required(view_func):
    """Attaches request.user (a User mongoengine document) if the bearer
    token is valid, otherwise returns 401."""

    @functools.wraps(view_func)
    def wrapper(request, *args, **kwargs):
        from accounts.models import AuthToken

        token_value = get_bearer_token(request)
        if not token_value:
            return JsonResponse({"detail": "Authentication required."}, status=401)
        token = AuthToken.objects(token=token_value).first()
        if not token:
            return JsonResponse({"detail": "Invalid or expired token."}, status=401)
        request.user = token.user
        return view_func(request, *args, **kwargs)

    return wrapper


def role_required(*allowed_roles):
    def decorator(view_func):
        @functools.wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if request.user.role not in allowed_roles:
                return JsonResponse(
                    {"detail": "You do not have permission to perform this action."},
                    status=403,
                )
            return view_func(request, *args, **kwargs)

        return wrapper

    return decorator

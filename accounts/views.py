import re

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from core.auth_utils import (
    get_bearer_token,
    hash_password,
    json_body,
    login_required,
    new_token,
    verify_password,
)
from .models import ROLE_CHOICES, ROLE_STANDARD, AuthToken, User

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@csrf_exempt
@require_http_methods(["POST"])
def register(request):
    data = json_body(request)
    username = (data.get("username") or "").strip()
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    role = data.get("role") or ROLE_STANDARD

    if not username or len(username) < 3:
        return JsonResponse({"detail": "Username must be at least 3 characters."}, status=400)
    if not EMAIL_RE.match(email):
        return JsonResponse({"detail": "Enter a valid email address."}, status=400)
    if len(password) < 8:
        return JsonResponse({"detail": "Password must be at least 8 characters."}, status=400)
    if role not in ROLE_CHOICES:
        role = ROLE_STANDARD

    if User.objects(username=username).first():
        return JsonResponse({"detail": "That username is taken."}, status=409)
    if User.objects(email=email).first():
        return JsonResponse({"detail": "An account with that email already exists."}, status=409)

    user = User(
        username=username,
        email=email,
        password_hash=hash_password(password),
        role=role,
    ).save()

    token = AuthToken(token=new_token(), user=user).save()
    return JsonResponse(
        {"token": token.token, "user": user.to_public_dict()}, status=201
    )


@csrf_exempt
@require_http_methods(["POST"])
def login(request):
    data = json_body(request)
    identifier = (data.get("username") or data.get("email") or "").strip()
    password = data.get("password") or ""

    user = User.objects(username=identifier).first() or User.objects(
        email=identifier.lower()
    ).first()
    if not user or not verify_password(password, user.password_hash):
        return JsonResponse({"detail": "Invalid credentials."}, status=401)

    token = AuthToken(token=new_token(), user=user).save()
    return JsonResponse({"token": token.token, "user": user.to_public_dict()})


@csrf_exempt
@require_http_methods(["POST"])
@login_required
def logout(request):
    token_value = get_bearer_token(request)
    AuthToken.objects(token=token_value).delete()
    return JsonResponse({"detail": "Logged out."})


@require_http_methods(["GET"])
@login_required
def me(request):
    return JsonResponse({"user": request.user.to_public_dict()})

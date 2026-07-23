from django.conf import settings
from django.http import HttpResponse


class CorsMiddleware:
    """Small CORS helper. The bundled frontend is served by Django itself
    (same-origin), so this mainly matters if you point a separately-hosted
    frontend at this API during development."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.method == "OPTIONS":
            response = HttpResponse()
        else:
            response = self.get_response(request)
        response["Access-Control-Allow-Origin"] = settings.CORS_ALLOWED_ORIGIN
        response["Access-Control-Allow-Methods"] = "GET, POST, PATCH, DELETE, OPTIONS"
        response["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
        return response

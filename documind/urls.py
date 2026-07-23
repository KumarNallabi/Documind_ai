from django.urls import include, path
from django.views.generic import TemplateView

urlpatterns = [
    path("api/auth/", include("accounts.urls")),
    path("api/documents/", include("documents.urls")),
    path("api/chat/", include("chat.urls")),
    path("", TemplateView.as_view(template_name="index.html"), name="index"),
]

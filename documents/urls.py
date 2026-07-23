from django.urls import path

from . import views

urlpatterns = [
    path("", views.list_documents, name="document-list"),
    path("upload/", views.upload, name="document-upload"),
    path("<str:document_id>/", views.rename_document, name="document-rename"),
    path("<str:document_id>/delete/", views.delete_document, name="document-delete"),
    path("<str:document_id>/retry/", views.retry_document, name="document-retry"),
    path("<str:document_id>/share/", views.share_document, name="document-share"),
    path("<str:document_id>/preview/", views.preview_document, name="document-preview"),
]

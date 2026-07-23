from django.urls import path

from . import views

urlpatterns = [
    #path("conversations/", views.list_conversations, name="conversation-list"),
    path("conversations/", views.create_conversation, name="conversation-list"),
    path("conversations/new/", views.create_conversation, name="conversation-create"),
    path(
        "conversations/<str:conversation_id>/messages/",
        views.conversation_messages,
        name="conversation-messages",
    ),
    path("ask/", views.ask, name="ask"),
]

import datetime

import mongoengine as me

ROLE_USER = "user"
ROLE_ASSISTANT = "assistant"


class Conversation(me.Document):
    owner_id = me.StringField(required=True)
    title = me.StringField(default="New conversation")
    document_scope = me.ListField(me.StringField(), default=list)  # [] == "all"
    created_at = me.DateTimeField(default=datetime.datetime.utcnow)
    updated_at = me.DateTimeField(default=datetime.datetime.utcnow)

    meta = {"collection": "conversations", "indexes": ["owner_id"], "ordering": ["-updated_at"]}

    def to_public_dict(self):
        return {
            "id": str(self.id),
            "title": self.title,
            "document_scope": self.document_scope,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


class Message(me.Document):
    conversation_id = me.StringField(required=True)
    owner_id = me.StringField(required=True)
    role = me.StringField(choices=(ROLE_USER, ROLE_ASSISTANT), required=True)
    content = me.StringField(required=True)
    citations = me.ListField(me.DictField(), default=list)
    grounded = me.BooleanField(default=True)
    created_at = me.DateTimeField(default=datetime.datetime.utcnow)

    meta = {"collection": "messages", "indexes": ["conversation_id"], "ordering": ["created_at"]}

    def to_public_dict(self):
        return {
            "id": str(self.id),
            "role": self.role,
            "content": self.content,
            "citations": self.citations,
            "grounded": self.grounded,
            "created_at": self.created_at.isoformat(),
        }

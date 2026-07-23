import datetime

import mongoengine as me

ROLE_ADMIN = "admin"
ROLE_STANDARD = "standard"
ROLE_VIEWER = "viewer"
ROLE_CHOICES = (ROLE_ADMIN, ROLE_STANDARD, ROLE_VIEWER)


class User(me.Document):
    username = me.StringField(required=True, unique=True, max_length=150)
    email = me.EmailField(required=True, unique=True)
    password_hash = me.StringField(required=True)
    role = me.StringField(choices=ROLE_CHOICES, default=ROLE_STANDARD)
    created_at = me.DateTimeField(default=datetime.datetime.utcnow)

    meta = {"collection": "users", "indexes": ["username", "email"]}

    def to_public_dict(self):
        return {
            "id": str(self.id),
            "username": self.username,
            "email": self.email,
            "role": self.role,
            "created_at": self.created_at.isoformat(),
        }


class AuthToken(me.Document):
    token = me.StringField(required=True, unique=True)
    user = me.ReferenceField(User, required=True, reverse_delete_rule=me.CASCADE)
    created_at = me.DateTimeField(default=datetime.datetime.utcnow)

    meta = {"collection": "auth_tokens", "indexes": ["token"]}


class SharedDocumentAccess(me.Document):
    """Grants a Viewer/Standard user read-only access to a document they
    do not own."""

    document_id = me.StringField(required=True)
    shared_with = me.ReferenceField(User, required=True, reverse_delete_rule=me.CASCADE)
    shared_by = me.ReferenceField(User, required=True, reverse_delete_rule=me.CASCADE)
    created_at = me.DateTimeField(default=datetime.datetime.utcnow)

    meta = {
        "collection": "shared_document_access",
        "indexes": ["document_id", "shared_with"],
    }

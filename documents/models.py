import datetime

import mongoengine as me

STATUS_UPLOADING = "uploading"
STATUS_PARSING = "parsing"
STATUS_CHUNKING = "chunking"
STATUS_EMBEDDING = "embedding"
STATUS_READY = "ready"
STATUS_FAILED = "failed"

STATUS_CHOICES = (
    STATUS_UPLOADING,
    STATUS_PARSING,
    STATUS_CHUNKING,
    STATUS_EMBEDDING,
    STATUS_READY,
    STATUS_FAILED,
)

FILE_TYPE_PDF = "pdf"
FILE_TYPE_MD = "md"


class Document(me.Document):
    owner_id = me.StringField(required=True)
    filename = me.StringField(required=True)
    file_type = me.StringField(choices=(FILE_TYPE_PDF, FILE_TYPE_MD), required=True)
    file_path = me.StringField(required=True)  # path on disk under MEDIA_ROOT
    size_bytes = me.IntField(default=0)
    page_count = me.IntField(default=0)
    status = me.StringField(choices=STATUS_CHOICES, default=STATUS_UPLOADING)
    error_message = me.StringField(default="")
    chunk_count = me.IntField(default=0)
    uploaded_at = me.DateTimeField(default=datetime.datetime.utcnow)
    ready_at = me.DateTimeField(null=True)

    meta = {
        "collection": "documents",
        "indexes": ["owner_id", "status", "filename"],
        "ordering": ["-uploaded_at"],
    }

    def to_public_dict(self):
        return {
            "id": str(self.id),
            "filename": self.filename,
            "file_type": self.file_type,
            "size_bytes": self.size_bytes,
            "page_count": self.page_count,
            "status": self.status,
            "error_message": self.error_message,
            "chunk_count": self.chunk_count,
            "uploaded_at": self.uploaded_at.isoformat(),
            "ready_at": self.ready_at.isoformat() if self.ready_at else None,
        }


class Chunk(me.Document):
    document_id = me.StringField(required=True)
    owner_id = me.StringField(required=True)
    filename = me.StringField(required=True)
    page_number = me.IntField(default=1)
    chunk_index = me.IntField(required=True)
    heading = me.StringField(default="")
    text = me.StringField(required=True)
    embedding = me.ListField(me.FloatField(), default=list)
    created_at = me.DateTimeField(default=datetime.datetime.utcnow)

    meta = {
        "collection": "chunks",
        "indexes": ["document_id", "owner_id"],
    }

    def to_citation_dict(self):
        return {
            "document_id": self.document_id,
            "filename": self.filename,
            "page_number": self.page_number,
            "chunk_index": self.chunk_index,
        }

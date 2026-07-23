import os
import uuid

from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from accounts.models import ROLE_ADMIN, SharedDocumentAccess, User
from core.auth_utils import json_body, login_required, role_required

from .models import STATUS_FAILED, STATUS_UPLOADING, Chunk, Document
from .parsing import extract_blocks
from .processing import process_document_async

ALLOWED_EXTENSIONS = {".pdf": "pdf", ".md": "md"}


def _visible_document_ids_for(user):
    """Admins see everything. Everyone else sees their own docs plus
    anything explicitly shared with them."""
    if user.role == ROLE_ADMIN:
        return None  # sentinel meaning "no owner filter"
    shared_ids = [
        s.document_id for s in SharedDocumentAccess.objects(shared_with=user)
    ]
    return shared_ids


@csrf_exempt
@require_http_methods(["POST"])
@login_required
def upload(request):
    upload_file = request.FILES.get("file")
    if not upload_file:
        return JsonResponse({"detail": "No file was provided."}, status=400)

    _, ext = os.path.splitext(upload_file.name.lower())
    if ext not in ALLOWED_EXTENSIONS:
        return JsonResponse(
            {"detail": "Only .pdf and .md files are supported."}, status=400
        )

    max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    if upload_file.size > max_bytes:
        return JsonResponse(
            {"detail": f"File exceeds the {settings.MAX_UPLOAD_SIZE_MB}MB limit."},
            status=400,
        )

    owner_dir = os.path.join(str(settings.MEDIA_ROOT), str(request.user.id))
    os.makedirs(owner_dir, exist_ok=True)
    stored_name = f"{uuid.uuid4().hex}{ext}"
    stored_path = os.path.join(owner_dir, stored_name)

    with open(stored_path, "wb") as dest:
        for chunk in upload_file.chunks():
            dest.write(chunk)

    document = Document(
        owner_id=str(request.user.id),
        filename=upload_file.name,
        file_type=ALLOWED_EXTENSIONS[ext],
        file_path=stored_path,
        size_bytes=upload_file.size,
        status=STATUS_UPLOADING,
    ).save()

    process_document_async(str(document.id))

    return JsonResponse(document.to_public_dict(), status=201)


@require_http_methods(["GET"])
@login_required
def list_documents(request):
    from mongoengine import Q

    visible_ids = _visible_document_ids_for(request.user)
    if visible_ids is None:
        qs = Document.objects.all()
    elif visible_ids:
        qs = Document.objects(Q(owner_id=str(request.user.id)) | Q(id__in=visible_ids))
    else:
        qs = Document.objects(owner_id=str(request.user.id))
    docs = [d.to_public_dict() for d in qs.order_by("-uploaded_at")]
    return JsonResponse({"documents": docs})


def _get_owned_document_or_none(request, document_id):
    doc = Document.objects(id=document_id).first()
    if not doc:
        return None
    if doc.owner_id != str(request.user.id) and request.user.role != ROLE_ADMIN:
        return None
    return doc


@csrf_exempt
@require_http_methods(["PATCH"])
@login_required
def rename_document(request, document_id):
    doc = _get_owned_document_or_none(request, document_id)
    if not doc:
        return JsonResponse({"detail": "Document not found."}, status=404)
    data = json_body(request)
    new_name = (data.get("filename") or "").strip()
    if not new_name:
        return JsonResponse({"detail": "filename is required."}, status=400)
    doc.filename = new_name
    doc.save()
    Chunk.objects(document_id=str(doc.id)).update(set__filename=new_name)
    return JsonResponse(doc.to_public_dict())


@csrf_exempt
@require_http_methods(["DELETE"])
@login_required
def delete_document(request, document_id):
    doc = _get_owned_document_or_none(request, document_id)
    if not doc:
        return JsonResponse({"detail": "Document not found."}, status=404)
    Chunk.objects(document_id=str(doc.id)).delete()
    SharedDocumentAccess.objects(document_id=str(doc.id)).delete()
    try:
        if os.path.exists(doc.file_path):
            os.remove(doc.file_path)
    except OSError:
        pass
    doc.delete()
    return JsonResponse({"detail": "Document deleted."})


@csrf_exempt
@require_http_methods(["POST"])
@login_required
def retry_document(request, document_id):
    doc = _get_owned_document_or_none(request, document_id)
    if not doc:
        return JsonResponse({"detail": "Document not found."}, status=404)
    if doc.status != STATUS_FAILED:
        return JsonResponse({"detail": "Only failed documents can be retried."}, status=400)
    Chunk.objects(document_id=str(doc.id)).delete()
    doc.status = STATUS_UPLOADING
    doc.error_message = ""
    doc.save()
    process_document_async(str(doc.id))
    return JsonResponse(doc.to_public_dict())


@csrf_exempt
@require_http_methods(["POST"])
@login_required
def share_document(request, document_id):
    doc = _get_owned_document_or_none(request, document_id)
    if not doc:
        return JsonResponse({"detail": "Document not found."}, status=404)
    data = json_body(request)
    username = (data.get("username") or "").strip()
    target = User.objects(username=username).first()
    if not target:
        return JsonResponse({"detail": "No user with that username."}, status=404)
    if not SharedDocumentAccess.objects(
        document_id=str(doc.id), shared_with=target
    ).first():
        SharedDocumentAccess(
            document_id=str(doc.id), shared_with=target, shared_by=request.user
        ).save()
    return JsonResponse({"detail": f"Shared with {target.username} (read-only)."})


@require_http_methods(["GET"])
@login_required
def preview_document(request, document_id):
    """Returns the extracted text for one page/section, with the cited
    excerpt's chunk_index so the frontend can highlight it."""
    doc = Document.objects(id=document_id).first()
    if not doc:
        return JsonResponse({"detail": "Document not found."}, status=404)
    is_owner = doc.owner_id == str(request.user.id)
    is_admin = request.user.role == ROLE_ADMIN
    is_shared = SharedDocumentAccess.objects(
        document_id=str(doc.id), shared_with=request.user
    ).first()
    if not (is_owner or is_admin or is_shared):
        return JsonResponse({"detail": "You do not have access to this document."}, status=403)

    page_number = int(request.GET.get("page", 1))
    chunk_index = request.GET.get("chunk_index")

    blocks, _ = extract_blocks(doc.file_path, doc.file_type)
    matching = [b for b in blocks if b["page_number"] == page_number]
    page_text = matching[0]["text"] if matching else ""

    excerpt = None
    if chunk_index is not None:
        c = Chunk.objects(document_id=str(doc.id), chunk_index=int(chunk_index)).first()
        if c:
            excerpt = c.text

    return JsonResponse(
        {
            "document_id": str(doc.id),
            "filename": doc.filename,
            "page_number": page_number,
            "page_count": doc.page_count,
            "page_text": page_text,
            "excerpt": excerpt,
        }
    )

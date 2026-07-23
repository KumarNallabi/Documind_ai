import json

from django.http import JsonResponse, StreamingHttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from core.auth_utils import json_body, login_required

from .llm import get_llm_provider
from .models import Conversation, Message
from .retrieval import retrieve

REFUSAL_MESSAGE = "I cannot find this in the documents."


@csrf_exempt
@require_http_methods(["GET", "POST"])
@login_required
def create_conversation(request):
    """
    GET  -> List conversations
    POST -> Create conversation
    """

    if request.method == "GET":
        conversations = (
            Conversation.objects(owner_id=str(request.user.id))
            .order_by("-updated_at")
        )

        return JsonResponse(
            {
                "conversations": [
                    c.to_public_dict()
                    for c in conversations
                ]
            }
        )

    # POST
    data = json_body(request)

    convo = Conversation(
        owner_id=str(request.user.id),
        title=data.get("title") or "New conversation",
        document_scope=data.get("document_scope") or [],
    ).save()

    return JsonResponse(
        convo.to_public_dict(),
        status=201,
    )


@require_http_methods(["GET"])
@login_required
def conversation_messages(request, conversation_id):

    convo = Conversation.objects(
        id=conversation_id,
        owner_id=str(request.user.id)
    ).first()

    if not convo:
        return JsonResponse(
            {"detail": "Conversation not found."},
            status=404,
        )

    messages = (
        Message.objects(
            conversation_id=str(convo.id)
        ).order_by("created_at")
    )

    return JsonResponse(
        {
            "conversation": convo.to_public_dict(),
            "messages": [
                m.to_public_dict()
                for m in messages
            ],
        }
    )


def _sse(event_type, payload):
    return f"event: {event_type}\ndata: {json.dumps(payload)}\n\n"

@csrf_exempt
@require_http_methods(["POST"])
@login_required
def ask(request):
    data = json_body(request)
    question = (data.get("question") or "").strip()
    conversation_id = data.get("conversation_id")
    document_scope = data.get("document_scope") or []  # [] == all documents

    if not question:
        return JsonResponse({"detail": "question is required."}, status=400)

    if conversation_id:
        convo = Conversation.objects(id=conversation_id, owner_id=str(request.user.id)).first()
        if not convo:
            return JsonResponse({"detail": "Conversation not found."}, status=404)
    else:
        convo = Conversation(
            owner_id=str(request.user.id),
            title=question[:60],
            document_scope=document_scope,
        ).save()

    Message(
        conversation_id=str(convo.id),
        owner_id=str(request.user.id),
        role="user",
        content=question,
    ).save()

    user = request.user

    def event_stream():
        chunks, best_similarity = retrieve(
            owner_id=str(user.id),
            query_text=question,
            document_ids=document_scope or None,
        )

        yield _sse("conversation", {"conversation_id": str(convo.id)})

        if not chunks:
            Message(
                conversation_id=str(convo.id),
                owner_id=str(user.id),
                role="assistant",
                content=REFUSAL_MESSAGE,
                citations=[],
                grounded=False,
            ).save()
            yield _sse("token", {"delta": REFUSAL_MESSAGE})
            yield _sse(
                "done",
                {"grounded": False, "citations": [], "best_similarity": best_similarity},
            )
            return

        try:
            provider = get_llm_provider()
            full_answer = []
            for delta in provider.stream_answer(question, chunks):
                full_answer.append(delta)
                yield _sse("token", {"delta": delta})
        except Exception as exc:  # noqa: BLE001
            yield _sse("error", {"detail": str(exc)})
            return

        answer_text = "".join(full_answer).strip()
        if not answer_text or answer_text == REFUSAL_MESSAGE:
            citations = []
            grounded = False
        else:
            # De-duplicate citations by (filename, page) while preserving order.
            seen = set()
            citations = []
            for c in chunks:
                key = (c.filename, c.page_number)
                if key not in seen:
                    seen.add(key)
                    citations.append(c.to_citation_dict())
            grounded = True

        Message(
            conversation_id=str(convo.id),
            owner_id=str(user.id),
            role="assistant",
            content=answer_text or REFUSAL_MESSAGE,
            citations=citations,
            grounded=grounded,
        ).save()

        convo.update(set__updated_at=__import__("datetime").datetime.utcnow())

        yield _sse(
            "done",
            {"grounded": grounded, "citations": citations, "best_similarity": best_similarity},
        )

    response = StreamingHttpResponse(event_stream(), content_type="text/event-stream")
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    return response

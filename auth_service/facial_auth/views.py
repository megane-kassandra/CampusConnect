from botocore.exceptions import BotoCoreError, ClientError
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_POST

from .rekognition import MAX_IMAGE_BYTES
from .strategy import FaceAuthentication


@ensure_csrf_cookie
def camera_page(request):
    return render(request, "facial_auth/camera.html")


@require_POST
def recognize(request):
    frame = request.FILES.get("frame")
    if frame is None:
        return JsonResponse({"error": "Image caméra absente."}, status=400)
    if frame.size > MAX_IMAGE_BYTES:
        return JsonResponse({"error": "Image trop volumineuse (maximum 5 Mo)."}, status=413)
    if frame.content_type not in ("image/jpeg", "image/png", "image/webp"):
        return JsonResponse({"error": "Format accepté : JPEG, PNG ou WebP."}, status=415)

    try:
        return JsonResponse(FaceAuthentication().authenticate(frame.read()))
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    except (BotoCoreError, ClientError):
        return JsonResponse(
            {"error": "AWS Rekognition indisponible ou mal configuré."},
            status=502,
        )

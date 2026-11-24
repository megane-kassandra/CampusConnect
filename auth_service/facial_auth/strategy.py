"""Stratégie faciale : enrôlement et identification via le fournisseur facial."""

from django.core.files.base import ContentFile

from authentication.models import FaceCredential
from .rekognition import (
    MAX_IMAGE_BYTES,
    detect_face_count,
    enroll_face,
    normalize_image,
    recognize_face,
)
from authentication.strategies.base import AuthMethod, Authentication, Enrollable


class FaceAuthentication(Authentication, Enrollable):
    """Adapter appelé par le container/factory du service Auth.

    Cette stratégie identifie un compte, mais ne crée pas de session ni de JWT.
    L'AuthenticationService reste responsable de la décision finale et des tokens.
    """

    method = AuthMethod.FACE

    def enroll(self, user, reference_image_bytes):
        user_id = getattr(user, "pk", user)
        if not reference_image_bytes or len(reference_image_bytes) > MAX_IMAGE_BYTES:
            raise ValueError("La photo de référence doit peser au maximum 5 Mo.")
        if detect_face_count(reference_image_bytes) != 1:
            raise ValueError("La photo de référence doit contenir exactement un visage.")
        reference_jpeg = normalize_image(reference_image_bytes)

        credential, created = FaceCredential.objects.get_or_create(user_id=user_id)
        if not created and credential.rekognition_face_id:
            raise ValueError("Un visage est déjà enrôlé pour ce compte.")

        credential.reference_photo.save(
            f"{user_id}.jpg",
            ContentFile(reference_jpeg),
            save=True,
        )
        try:
            indexed = enroll_face(user_id, reference_image_bytes)
        except Exception:
            credential.reference_photo.delete(save=False)
            if created:
                credential.delete()
            raise

        credential.rekognition_face_id = indexed["face_id"]
        credential.save(update_fields=["rekognition_face_id"])
        return credential

    def authenticate(self, live_image_bytes):
        result = recognize_face(live_image_bytes)
        if result.get("status") != "recognized":
            return result

        credential = FaceCredential.objects.filter(
            user_id=result["user_id"],
            rekognition_face_id=result["face_id"],
            is_active=True,
        ).first()
        if credential is None:
            return {"status": "unknown", "face_count": 1}

        return {
            "status": "recognized",
            "face_count": 1,
            "user_id": str(credential.user_id),
            "similarity": result["similarity"],
        }

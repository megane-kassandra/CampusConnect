from django.conf import settings
from django.db import models


class FaceCredential(models.Model):
    """Référence faciale rattachée au compte central du service Auth."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="face_credential",
    )
    reference_photo = models.ImageField(upload_to="auth/face_references/")
    rekognition_face_id = models.CharField(max_length=128, blank=True, db_index=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Face credential for user {self.user_id}"

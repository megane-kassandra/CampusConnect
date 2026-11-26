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


# WebAuthn : aucune empreinte ou cle privee n'est stockee.
import uuid


class FingerprintConsent(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                related_name="fingerprint_consent")
    handle = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    policy_version = models.CharField(max_length=32)
    accepted_at = models.DateTimeField(auto_now=True)


class FingerprintCredential(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                             related_name="fingerprint_credentials")
    credential_id = models.CharField(max_length=1400, unique=True)
    public_key = models.BinaryField()
    sign_count = models.PositiveBigIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"Passkey {self.pk}"


class FingerprintChallenge(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    purpose = models.CharField(max_length=12)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                             on_delete=models.CASCADE)
    binding = models.CharField(max_length=64)
    user_handle = models.UUIDField(null=True, blank=True)
    challenge = models.BinaryField(max_length=32)
    expires_at = models.DateTimeField(db_index=True)
    consumed_at = models.DateTimeField(null=True, blank=True)

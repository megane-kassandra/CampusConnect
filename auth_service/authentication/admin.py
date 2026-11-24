from django.contrib import admin

from .models import FaceCredential


@admin.register(FaceCredential)
class FaceCredentialAdmin(admin.ModelAdmin):
    list_display = ("user", "rekognition_face_id", "is_active", "created_at")
    readonly_fields = ("rekognition_face_id", "created_at")

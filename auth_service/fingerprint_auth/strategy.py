from authentication.strategies.base import AuthMethod, Authentication, Enrollable
from .webauthn_service import WebAuthnService


class FingerprintAuthentication(Authentication, Enrollable):
    """Comme FaceAuthentication : identifie un compte, sans emettre de JWT."""
    method = AuthMethod.FINGERPRINT

    def __init__(self, service=None):
        self.service = service if service is not None else WebAuthnService()

    def enroll(self, user, payload):
        return self.service.enroll(user, payload)

    def authenticate(self, payload):
        return self.service.authenticate(payload)

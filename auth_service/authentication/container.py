from authentication.factories.authentication_factory import AuthenticationFactory
from authentication.strategies.base import AuthMethod


def build_authentication_factory():
    """Racine de composition des strategies d'authentification."""
    from facial_auth.strategy import FaceAuthentication
    from fingerprint_auth.strategy import FingerprintAuthentication
    from fingerprint_auth.webauthn_service import WebAuthnService

    return AuthenticationFactory({
        AuthMethod.FACE: FaceAuthentication(),
        AuthMethod.FINGERPRINT: FingerprintAuthentication(WebAuthnService()),
    })

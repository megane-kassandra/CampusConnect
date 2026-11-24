from authentication.factories.authentication_factory import AuthenticationFactory
from authentication.strategies.base import AuthMethod


def build_authentication_factory():
    """Seule racine de composition : branche la stratégie faciale au cœur Auth."""
    from facial_auth.strategy import FaceAuthentication

    return AuthenticationFactory({
        AuthMethod.FACE: FaceAuthentication(),
    })

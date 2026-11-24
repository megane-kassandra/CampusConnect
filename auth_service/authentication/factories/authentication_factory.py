from authentication.strategies.base import AuthMethod


class AuthenticationFactory:
    """Résout une méthode d'authentification déjà construite par le container."""

    def __init__(self, strategies):
        self._strategies = dict(strategies)

    def create(self, method):
        try:
            auth_method = method if isinstance(method, AuthMethod) else AuthMethod(method)
            return self._strategies[auth_method]
        except (ValueError, KeyError) as exc:
            raise ValueError(f"Méthode d'authentification non configurée : {method}") from exc

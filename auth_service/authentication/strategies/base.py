from abc import ABC, abstractmethod
from enum import Enum


class AuthMethod(str, Enum):
    PASSWORD = "password"
    FACE = "face"
    FINGERPRINT = "fingerprint"
    QR = "qr"


class Authentication(ABC):
    @abstractmethod
    def authenticate(self, payload):
        """Retourne le résultat de l'authentification de la stratégie."""
        raise NotImplementedError


class Enrollable(ABC):
    @abstractmethod
    def enroll(self, user, payload):
        """Enrôle une méthode biométrique pour un compte existant."""
        raise NotImplementedError

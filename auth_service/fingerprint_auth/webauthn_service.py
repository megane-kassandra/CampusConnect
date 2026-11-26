import hashlib
import json
import logging
import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.utils import timezone
from webauthn import (
    generate_registration_options, verify_registration_response,
    generate_authentication_options, verify_authentication_response,
    options_to_json, base64url_to_bytes,
)
from webauthn.helpers import bytes_to_base64url, parse_authentication_credential_json
from webauthn.helpers.exceptions import WebAuthnException
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria, PublicKeyCredentialDescriptor,
    ResidentKeyRequirement, UserVerificationRequirement,
    AttestationConveyancePreference,
)

from authentication.models import (
    FingerprintChallenge, FingerprintConsent, FingerprintCredential,
)

logger = logging.getLogger(__name__)
PROOF_ERRORS = (WebAuthnException, ValueError, TypeError, KeyError, IndexError, OverflowError)


class FingerprintError(Exception):
    def __init__(self, code, status=400):
        self.code = code
        self.status = status
        super().__init__(code)


class WebAuthnService:
    """Moteur independant de HTTP, des sessions Django et des JWT."""

    @staticmethod
    def _binding(value):
        if not isinstance(value, str) or not value:
            raise FingerprintError('INVALID_CHALLENGE')
        return hashlib.sha256(value.encode()).hexdigest()

    def _new_challenge(self, purpose, binding, user=None, user_handle=None):
        # Purge opportuniste : en production, prevoir aussi une tache periodique.
        FingerprintChallenge.objects.filter(expires_at__lt=timezone.now()).delete()
        return FingerprintChallenge.objects.create(
            purpose=purpose, user=user, binding=self._binding(binding), user_handle=user_handle,
            challenge=secrets.token_bytes(32),
            expires_at=timezone.now() + timedelta(minutes=5),
        )

    def _consume(self, challenge_id, purpose, binding, user_id=None):
        # UPDATE atomique en autocommit : une seule requete peut gagner.
        # Ne pas englober cet appel dans une transaction rollbackable par le verify.
        now = timezone.now()
        query = FingerprintChallenge.objects.filter(
            pk=challenge_id, purpose=purpose, binding=self._binding(binding),
            user_id=user_id, consumed_at__isnull=True, expires_at__gt=now,
        )
        if query.update(consumed_at=now) != 1:
            raise FingerprintError('CHALLENGE_EXPIRED', 410)
        try:
            return FingerprintChallenge.objects.get(pk=challenge_id)
        except FingerprintChallenge.DoesNotExist as exc:
            raise FingerprintError('CHALLENGE_EXPIRED', 410) from exc

    @staticmethod
    def _active(user):
        if not user.is_active:
            raise FingerprintError('ACCOUNT_NOT_ACTIVE', 403)

    def consent(self, user):
        with transaction.atomic():
            user = get_user_model().objects.select_for_update().get(pk=user.pk)
            self._active(user)
            FingerprintConsent.objects.update_or_create(
                user=user, defaults={'policy_version': settings.WEBAUTHN_POLICY_VERSION},
            )

    def registration_options(self, user, binding):
        self._active(user)
        consent = FingerprintConsent.objects.filter(
            user=user, policy_version=settings.WEBAUTHN_POLICY_VERSION,
        ).first()
        if not consent:
            raise FingerprintError('CONSENT_REQUIRED', 403)
        existing = list(FingerprintCredential.objects.filter(user=user))
        if len(existing) >= settings.WEBAUTHN_MAX_CREDENTIALS:
            raise FingerprintError('MAX_CREDENTIALS_REACHED', 409)
        challenge = self._new_challenge('register', binding, user, consent.handle)
        opts = generate_registration_options(
            rp_id=settings.WEBAUTHN_RP_ID, rp_name=settings.WEBAUTHN_RP_NAME,
            user_id=consent.handle.bytes, user_name=user.get_username(),
            user_display_name=user.get_full_name() or user.get_username(),
            challenge=bytes(challenge.challenge), timeout=300000,
            attestation=AttestationConveyancePreference.NONE,
            authenticator_selection=AuthenticatorSelectionCriteria(
                resident_key=ResidentKeyRequirement.REQUIRED,
                user_verification=UserVerificationRequirement.REQUIRED,
            ),
            exclude_credentials=[PublicKeyCredentialDescriptor(id=base64url_to_bytes(c.credential_id)) for c in existing],
        )
        return {'challengeId': str(challenge.pk), 'publicKey': json.loads(options_to_json(opts))}

    def enroll(self, user, payload):
        challenge = self._consume(payload['challengeId'], 'register', payload['binding'], user.pk)
        self._active(user)
        # Consentement peut etre retire entre options et verify.
        try:
            proof = verify_registration_response(
                credential=payload['response'], expected_challenge=bytes(challenge.challenge),
                expected_rp_id=settings.WEBAUTHN_RP_ID,
                expected_origin=settings.WEBAUTHN_ORIGIN,
                require_user_verification=True,
            )
        except PROOF_ERRORS as exc:
            logger.info('PASSKEY_ENROLL_FAILED')
            raise FingerprintError('WEBAUTHN_VERIFICATION_FAILED', 401) from exc
        try:
            with transaction.atomic():
                user = get_user_model().objects.select_for_update().get(pk=user.pk)
                self._active(user)
                if not FingerprintConsent.objects.filter(
                    user=user, policy_version=settings.WEBAUTHN_POLICY_VERSION, handle=challenge.user_handle,
                ).exists():
                    raise FingerprintError('CONSENT_REQUIRED', 403)
                if FingerprintCredential.objects.filter(user=user).count() >= settings.WEBAUTHN_MAX_CREDENTIALS:
                    raise FingerprintError('MAX_CREDENTIALS_REACHED', 409)
                credential = FingerprintCredential.objects.create(
                    user=user, credential_id=bytes_to_base64url(proof.credential_id),
                    public_key=proof.credential_public_key, sign_count=proof.sign_count,
                )
        except IntegrityError as exc:
            raise FingerprintError('CREDENTIAL_ALREADY_EXISTS', 409) from exc
        logger.info('PASSKEY_ENROLLED')
        return credential

    def login_options(self, binding):
        # Credentials decouvrables : aucune enumeration par email/username.
        challenge = self._new_challenge('login', binding)
        opts = generate_authentication_options(
            rp_id=settings.WEBAUTHN_RP_ID, challenge=bytes(challenge.challenge),
            timeout=300000, user_verification=UserVerificationRequirement.REQUIRED,
        )
        return {'challengeId': str(challenge.pk), 'publicKey': json.loads(options_to_json(opts))}

    def authenticate(self, payload):
        challenge = self._consume(payload['challengeId'], 'login', payload['binding'])
        try:
            response = parse_authentication_credential_json(payload['response'])
            credential_id = bytes_to_base64url(response.raw_id)
            with transaction.atomic():
                # Meme ordre de verrouillage que le retrait de consentement : user puis credential.
                owner = FingerprintCredential.objects.filter(credential_id=credential_id).values_list('user_id', flat=True).first()
                if owner is None:
                    raise FingerprintError('INVALID_CREDENTIALS', 401)
                user = get_user_model().objects.select_for_update().get(pk=owner)
                credential = FingerprintCredential.objects.select_for_update().get(credential_id=credential_id, user=user)
                consent = FingerprintConsent.objects.filter(user=user, policy_version=settings.WEBAUTHN_POLICY_VERSION).first()
                if not user.is_active or not consent or response.response.user_handle != consent.handle.bytes:
                    raise FingerprintError('INVALID_CREDENTIALS', 401)
                proof = verify_authentication_response(
                    credential=response, expected_challenge=bytes(challenge.challenge),
                    expected_rp_id=settings.WEBAUTHN_RP_ID,
                    expected_origin=settings.WEBAUTHN_ORIGIN,
                    credential_public_key=bytes(credential.public_key),
                    credential_current_sign_count=credential.sign_count,
                    require_user_verification=True,
                )
                credential.sign_count = proof.new_sign_count
                credential.last_used_at = timezone.now()
                credential.save(update_fields=['sign_count', 'last_used_at'])
        except (FingerprintCredential.DoesNotExist, get_user_model().DoesNotExist) + PROOF_ERRORS as exc:
            logger.info('PASSKEY_LOGIN_FAILED')
            raise FingerprintError('INVALID_CREDENTIALS', 401) from exc
        except FingerprintError:
            logger.info('PASSKEY_LOGIN_FAILED')
            raise
        logger.info('PASSKEY_VERIFIED')
        return {'status': 'recognized', 'user_id': str(user.pk), 'amr': 'webauthn'}

    def revoke(self, user, credential_pk):
        with transaction.atomic():
            get_user_model().objects.select_for_update().get(pk=user.pk)
            deleted, _ = FingerprintCredential.objects.filter(pk=credential_pk, user=user).delete()
        if not deleted:
            raise FingerprintError('CREDENTIAL_NOT_FOUND', 404)
        logger.info('PASSKEY_REVOKED')

    def withdraw_consent(self, user):
        with transaction.atomic():
            get_user_model().objects.select_for_update().get(pk=user.pk)
            FingerprintCredential.objects.filter(user=user).delete()
            FingerprintChallenge.objects.filter(user=user).delete()
            FingerprintConsent.objects.filter(user=user).delete()
        logger.info('PASSKEY_CONSENT_WITHDRAWN')

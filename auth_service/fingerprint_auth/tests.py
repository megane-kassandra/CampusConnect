from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, Client, override_settings
from django.urls import reverse
from django.utils import timezone
from webauthn.helpers import bytes_to_base64url

from authentication.models import FingerprintChallenge, FingerprintConsent, FingerprintCredential
from .webauthn_service import WebAuthnService, FingerprintError


@override_settings(WEBAUTHN_DEMO_ENABLED=True, WEBAUTHN_RP_ID='localhost',
                   WEBAUTHN_ORIGIN='http://localhost:8081')
class FingerprintTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = get_user_model().objects.create_user(username='alice', password='Test12345!')
        self.other = get_user_model().objects.create_user(username='bob', password='Test12345!')
        self.service = WebAuthnService()
        self.binding = 'test-session'

    def register(self):
        self.service.consent(self.user)
        opts = self.service.registration_options(self.user, self.binding)
        with patch('fingerprint_auth.webauthn_service.verify_registration_response', return_value=SimpleNamespace(
            credential_id=b'credential-a', credential_public_key=b'test-public-key', sign_count=0,
        )) as verify:
            credential = self.service.enroll(self.user, {'challengeId': opts['challengeId'], 'binding': self.binding, 'response': {}})
            self.assertTrue(verify.call_args.kwargs['require_user_verification'])
        return credential, opts

    def test_consent_required(self):
        with self.assertRaises(FingerprintError) as exc:
            self.service.registration_options(self.user, self.binding)
        self.assertEqual(exc.exception.code, 'CONSENT_REQUIRED')

    def test_enroll_and_replay(self):
        credential, opts = self.register()
        self.assertEqual(credential.user, self.user)
        self.assertEqual(len(FingerprintChallenge.objects.get(pk=opts['challengeId']).challenge), 32)
        with self.assertRaises(FingerprintError) as exc:
            self.service.enroll(self.user, {'challengeId': opts['challengeId'], 'binding': self.binding, 'response': {}})
        self.assertEqual(exc.exception.code, 'CHALLENGE_EXPIRED')

    def test_expired_challenge(self):
        opts = self.service.login_options(self.binding)
        FingerprintChallenge.objects.filter(pk=opts['challengeId']).update(expires_at=timezone.now()-timedelta(seconds=1))
        with self.assertRaises(FingerprintError) as exc:
            self.service.authenticate({'challengeId':opts['challengeId'], 'binding':self.binding,'response':{}})
        self.assertEqual(exc.exception.status, 410)

    def test_challenge_bound_to_session(self):
        opts = self.service.login_options(self.binding)
        with self.assertRaises(FingerprintError):
            self.service.authenticate({'challengeId':opts['challengeId'], 'binding':'other-session','response':{}})
        self.assertIsNone(FingerprintChallenge.objects.get(pk=opts['challengeId']).consumed_at)

    def test_login_updates_counter(self):
        credential, _ = self.register()
        opts = self.service.login_options(self.binding)
        handle = FingerprintConsent.objects.get(user=self.user).handle.bytes
        response = SimpleNamespace(raw_id=b'credential-a', response=SimpleNamespace(user_handle=handle))
        with patch('fingerprint_auth.webauthn_service.parse_authentication_credential_json', return_value=response), \
             patch('fingerprint_auth.webauthn_service.verify_authentication_response', return_value=SimpleNamespace(new_sign_count=1)) as verify:
            result = self.service.authenticate({'challengeId':opts['challengeId'], 'binding':self.binding,'response':{}})
            self.assertEqual(result['user_id'], str(self.user.pk))
            self.assertTrue(verify.call_args.kwargs['require_user_verification'])
        credential.refresh_from_db()
        self.assertEqual(credential.sign_count, 1)

    def test_wrong_user_handle(self):
        self.register()
        opts = self.service.login_options(self.binding)
        response = SimpleNamespace(raw_id=b'credential-a', response=SimpleNamespace(user_handle=b'wrong'))
        with patch('fingerprint_auth.webauthn_service.parse_authentication_credential_json', return_value=response):
            with self.assertRaises(FingerprintError) as exc:
                self.service.authenticate({'challengeId':opts['challengeId'], 'binding':self.binding,'response':{}})
        self.assertEqual(exc.exception.status, 401)

    def test_withdraw_and_ownership(self):
        credential, _ = self.register()
        with self.assertRaises(FingerprintError):
            self.service.revoke(self.other, credential.pk)
        self.service.withdraw_consent(self.user)
        self.assertFalse(FingerprintCredential.objects.filter(user=self.user).exists())
        self.assertFalse(FingerprintConsent.objects.filter(user=self.user).exists())

    def test_anonymous_cannot_enroll(self):
        response = self.client.post(reverse('fingerprint_auth:registration_options'))
        self.assertEqual(response.status_code, 401)

    def test_csrf_required(self):
        client = Client(enforce_csrf_checks=True)
        self.assertEqual(client.post(reverse('fingerprint_auth:login_options')).status_code, 403)

    def test_maximum_credentials(self):
        self.service.consent(self.user)
        for i in range(5):
            FingerprintCredential.objects.create(user=self.user, credential_id=bytes_to_base64url(bytes([i])),public_key=b'key')
        with self.assertRaises(FingerprintError) as exc:
            self.service.registration_options(self.user, self.binding)
        self.assertEqual(exc.exception.code, 'MAX_CREDENTIALS_REACHED')

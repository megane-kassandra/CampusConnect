import json
import hashlib
import logging
from functools import wraps

from django.conf import settings
from django.contrib.auth.views import LoginView, LogoutView
from django.core.cache import cache
from django.http import Http404, JsonResponse, HttpResponse
from django.shortcuts import render
from django.urls import reverse_lazy
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST, require_http_methods

from authentication.models import FingerprintCredential
from .serializers import ConsentSerializer, VerificationSerializer
from .strategy import FingerprintAuthentication
from .webauthn_service import FingerprintError

logger = logging.getLogger(__name__)


def demo_only(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not settings.WEBAUTHN_DEMO_ENABLED:
            raise Http404
        return view(request, *args, **kwargs)
    return wrapped


def api(view):
    @demo_only
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        # Limitation simple par IP pour la demo. Cache partage requis en multi-workers.
        ip = request.META.get('REMOTE_ADDR', 'unknown')
        key = 'fingerprint:rate:' + hashlib.sha256(ip.encode()).hexdigest()
        if not cache.add(key, 1, timeout=60):
            try:
                count = cache.incr(key)
            except ValueError:  # expiration entre add et incr
                cache.add(key, 1, timeout=60)
                count = 1
            if count > 20:
                return JsonResponse({'error': 'TOO_MANY_REQUESTS'}, status=429)
        try:
            return view(request, *args, **kwargs)
        except FingerprintError as exc:
            logger.info('PASSKEY_REQUEST_REJECTED code=%s', exc.code)
            return JsonResponse({'error': exc.code}, status=exc.status)
    return wrapped


def signed_in(request):
    if not request.user.is_authenticated or not request.user.is_active:
        raise FingerprintError('AUTHENTICATION_REQUIRED', 401)
    return request.user


def binding(request):
    # Le challenge est lie a la session navigateur, jamais a un ID fourni par le client.
    if not request.session.session_key:
        request.session.create()
    return request.session.session_key


def validated(request, serializer_class):
    if request.content_type != 'application/json':
        raise FingerprintError('JSON_REQUIRED', 415)
    if len(request.body) > 65536:
        raise FingerprintError('PAYLOAD_TOO_LARGE', 413)
    try:
        data = json.loads(request.body)
    except (ValueError, UnicodeError) as exc:
        raise FingerprintError('VALIDATION_ERROR') from exc
    serializer = serializer_class(data=data)
    if not serializer.is_valid():
        raise FingerprintError('VALIDATION_ERROR')
    return dict(serializer.validated_data)


@demo_only
@ensure_csrf_cookie
@require_GET
def demo_page(request):
    return render(request, 'fingerprint_auth/demo.html')


# Connexion classique de DEMO pour permettre l'enrolement sur son propre compte.
demo_signin = demo_only(LoginView.as_view(
    template_name='fingerprint_auth/signin.html',
    next_page=reverse_lazy('fingerprint_auth:demo'),
    redirect_authenticated_user=True,
))
demo_signout = demo_only(LogoutView.as_view(next_page=reverse_lazy('fingerprint_auth:demo')))


@api
@require_http_methods(['POST', 'DELETE'])
def consent(request):
    user = signed_in(request)
    service = FingerprintAuthentication().service
    if request.method == 'DELETE':
        service.withdraw_consent(user)
        return HttpResponse(status=204)
    validated(request, ConsentSerializer)
    service.consent(user)
    return JsonResponse({'status': 'accepted', 'policyVersion': settings.WEBAUTHN_POLICY_VERSION})


@api
@require_POST
def registration_options(request):
    user = signed_in(request)
    return JsonResponse(FingerprintAuthentication().service.registration_options(user, binding(request)))


@api
@require_POST
def registration_verify(request):
    user = signed_in(request)
    payload = validated(request, VerificationSerializer)
    payload['binding'] = binding(request)
    credential = FingerprintAuthentication().enroll(user, payload)
    return JsonResponse({'status': 'enrolled', 'id': credential.pk, 'completedSteps': ['FINGERPRINT']})


@api
@require_POST
def login_options(request):
    return JsonResponse(FingerprintAuthentication().service.login_options(binding(request)))


@api
@require_POST
def login_verify(request):
    payload = validated(request, VerificationSerializer)
    payload['binding'] = binding(request)
    return JsonResponse(FingerprintAuthentication().authenticate(payload))


@api
@require_GET
def credentials(request):
    user = signed_in(request)
    items = FingerprintCredential.objects.filter(user=user).order_by('created_at').values('id', 'created_at', 'last_used_at')
    return JsonResponse({'credentials': list(items)})


@api
@require_http_methods(['DELETE'])
def revoke(request, pk):
    FingerprintAuthentication().service.revoke(signed_in(request), pk)
    return HttpResponse(status=204)

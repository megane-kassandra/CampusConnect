from django.urls import path
from . import views

app_name = 'fingerprint_auth'
urlpatterns = [
    path('fingerprint/demo/', views.demo_page, name='demo'),
    path('fingerprint/demo/signin/', views.demo_signin, name='signin'),
    path('fingerprint/demo/signout/', views.demo_signout, name='signout'),
    path('register/consent/', views.consent, name='consent'),
    path('biometrics/consent/', views.consent, name='biometrics_consent'),
    path('register/fingerprint/options/', views.registration_options, name='registration_options'),
    path('register/fingerprint/verify/', views.registration_verify, name='registration_verify'),
    path('webauthn/login/options/', views.login_options, name='login_options'),
    path('webauthn/login/verify/', views.login_verify, name='login_verify'),
    path('webauthn/credentials/', views.credentials, name='credentials'),
    path('webauthn/credentials/<int:pk>/', views.revoke, name='revoke'),
]

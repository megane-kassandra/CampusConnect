from django.urls import path

from . import views


app_name = "facial_auth"

urlpatterns = [
    path("camera/", views.camera_page, name="camera"),
    path("recognize/", views.recognize, name="recognize"),
]

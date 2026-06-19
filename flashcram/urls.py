from django.contrib import admin
from django.contrib.auth.views import LogoutView
from django.http import HttpResponse
from django.urls import include, path

from .views import FlashCramLoginView


def healthz(_request):
    return HttpResponse("ok\n", content_type="text/plain")


urlpatterns = [
    path("healthz/", healthz, name="healthz"),
    path("login/", FlashCramLoginView.as_view(), name="login"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("oidc/", include("mozilla_django_oidc.urls")),
    path("admin/", admin.site.urls),
    path("", include("cards.urls")),
]

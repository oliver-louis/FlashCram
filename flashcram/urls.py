from django.contrib import admin
from django.http import HttpResponse
from django.urls import include, path


def healthz(_request):
    return HttpResponse("ok\n", content_type="text/plain")


urlpatterns = [
    path("healthz/", healthz, name="healthz"),
    path("oidc/", include("mozilla_django_oidc.urls")),
    path("admin/", admin.site.urls),
    path("", include("cards.urls")),
]

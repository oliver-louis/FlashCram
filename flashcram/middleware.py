from __future__ import annotations

from django.conf import settings
from django.shortcuts import redirect
from django.urls import reverse


class LoginRequiredMiddleware:
    """Redirect anonymous app traffic to OIDC while leaving health/static/auth open."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if self._requires_login(request) and not request.user.is_authenticated:
            return redirect(f"{reverse('oidc_authentication_init')}?next={request.get_full_path()}")
        return self.get_response(request)

    def _requires_login(self, request) -> bool:
        path = request.path_info
        static_url = settings.STATIC_URL
        if not static_url.startswith("/"):
            static_url = f"/{static_url}"
        exempt_prefixes = (
            static_url,
            "/healthz/",
            "/oidc/",
        )
        return not any(path.startswith(prefix) for prefix in exempt_prefixes)

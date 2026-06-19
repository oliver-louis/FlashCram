from urllib.parse import urlencode

from django.contrib.auth.views import LoginView
from django.urls import reverse


class FlashCramLoginView(LoginView):
    template_name = "registration/login.html"
    redirect_authenticated_user = True

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        redirect_to = self.get_redirect_url() or self.get_success_url()
        oidc_url = reverse("oidc_authentication_init")
        if redirect_to:
            oidc_url = f"{oidc_url}?{urlencode({self.redirect_field_name: redirect_to})}"
        context["oidc_login_url"] = oidc_url
        return context

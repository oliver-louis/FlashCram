from __future__ import annotations

from django.contrib.auth import get_user_model
from mozilla_django_oidc.auth import OIDCAuthenticationBackend


class FlashCramOIDCAuthenticationBackend(OIDCAuthenticationBackend):
    """Map Authentik/OIDC claims onto Django's standard User model."""

    def filter_users_by_claims(self, claims):
        User = get_user_model()
        username = self._username_from_claims(claims)
        email = (claims.get("email") or "").strip()
        if username:
            users = User.objects.filter(username=username)
            if users.exists():
                return users
        if email:
            return User.objects.filter(email__iexact=email)
        return User.objects.none()

    def create_user(self, claims):
        User = get_user_model()
        username = self._unique_username(self._username_from_claims(claims) or "flashcram")
        email = (claims.get("email") or "").strip()
        user = User.objects.create_user(
            username=username,
            email=email,
            first_name=(claims.get("given_name") or "")[:150],
            last_name=(claims.get("family_name") or "")[:150],
        )
        return user

    def update_user(self, user, claims):
        email = (claims.get("email") or "").strip()
        changed_fields = []
        if email and user.email != email:
            user.email = email
            changed_fields.append("email")
        first_name = (claims.get("given_name") or "")[:150]
        last_name = (claims.get("family_name") or "")[:150]
        if first_name != user.first_name:
            user.first_name = first_name
            changed_fields.append("first_name")
        if last_name != user.last_name:
            user.last_name = last_name
            changed_fields.append("last_name")
        if changed_fields:
            user.save(update_fields=changed_fields)
        return user

    def _username_from_claims(self, claims):
        preferred = (claims.get("preferred_username") or "").strip()
        if preferred:
            return preferred[:150]
        email = (claims.get("email") or "").strip()
        if email and "@" in email:
            return email.split("@", 1)[0][:150]
        subject = (claims.get("sub") or "").strip()
        return subject[:150]

    def _unique_username(self, username):
        User = get_user_model()
        base = username[:140] or "flashcram"
        candidate = base
        suffix = 2
        while User.objects.filter(username=candidate).exists():
            candidate = f"{base}-{suffix}"[:150]
            suffix += 1
        return candidate

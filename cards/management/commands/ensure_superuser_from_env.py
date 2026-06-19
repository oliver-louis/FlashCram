import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Create an initial superuser from DJANGO_SUPERUSER_* env vars when provided."

    def handle(self, *args, **options):
        username = (os.environ.get("DJANGO_SUPERUSER_USERNAME") or "").strip()
        email = (os.environ.get("DJANGO_SUPERUSER_EMAIL") or "").strip()
        password = os.environ.get("DJANGO_SUPERUSER_PASSWORD") or ""
        if not username or not password:
            self.stdout.write("No DJANGO_SUPERUSER_USERNAME/PASSWORD provided; skipping superuser creation.")
            return

        User = get_user_model()
        user, created = User.objects.get_or_create(
            username=username,
            defaults={"email": email, "is_staff": True, "is_superuser": True},
        )
        changed = False
        if not user.is_staff:
            user.is_staff = True
            changed = True
        if not user.is_superuser:
            user.is_superuser = True
            changed = True
        if email and user.email != email:
            user.email = email
            changed = True
        if created or not user.has_usable_password():
            user.set_password(password)
            changed = True
        if changed:
            user.save()
        self.stdout.write(self.style.SUCCESS(f"Superuser {username!r} is ready."))

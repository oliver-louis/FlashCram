import time

from django.core.management.base import BaseCommand
from django.db import OperationalError, connections


class Command(BaseCommand):
    help = "Wait until the configured database accepts connections."

    def add_arguments(self, parser):
        parser.add_argument("--timeout", type=int, default=60)
        parser.add_argument("--interval", type=float, default=2.0)

    def handle(self, *args, **options):
        deadline = time.monotonic() + options["timeout"]
        last_error = None
        while time.monotonic() < deadline:
            try:
                connections["default"].ensure_connection()
                self.stdout.write(self.style.SUCCESS("Database is available."))
                return
            except OperationalError as exc:
                last_error = exc
                time.sleep(options["interval"])
        raise OperationalError(f"Database did not become available: {last_error}")

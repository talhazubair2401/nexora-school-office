from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Online demo only (SCHOOL_DEMO=1): rebuild the fictional demo school now."

    def handle(self, *args, **opts):
        if not settings.DEMO_MODE:
            raise CommandError("Refusing to run: this only works when SCHOOL_DEMO=1. It never touches a school's real records.")
        from office.demo import build_demo, next_reset
        build_demo()
        self.stdout.write(self.style.SUCCESS(f"Demo school rebuilt. Next automatic reset: {next_reset():%d %b %Y %H:%M}."))

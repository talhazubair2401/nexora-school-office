from django.db.utils import DatabaseError
from django.templatetags.static import static

from .models import School


from django.conf import settings as _settings

# Who made the software (shown on the login screen, at the bottom of the menu and in Settings).
_maker_logo = _settings.BASE_DIR / "static" / "img" / "nexora_logo.png"
MAKER = {
    "name": "NEXORA SOFTWARE & WEB SOLUTIONS",
    "short": "NEXORA",
    "logo": static("img/nexora_logo.png") if _maker_logo.exists() else "",
    "email": "nexoraservices90@gmail.com",   # shown under "Need help?"
    "version": "2.1 (October 2026)",
}


def school(request):
    try:
        s = School.get()
        logo = s.logo.url if s.logo else static("img/school_logo.png")
    except DatabaseError:
        s, logo = None, static("img/school_logo.png")
    from .access import Access
    ctx = {"school": s, "logo_url": logo, "maker": MAKER, "access": Access(getattr(request, "user", None)),
           "DEMO_MODE": _settings.DEMO_MODE}
    if _settings.DEMO_MODE:
        from .demo import next_reset
        ctx["demo_reset"] = next_reset()
    return ctx

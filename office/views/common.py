from datetime import date

from django.core.paginator import Paginator
from django.utils import timezone


def paginate(request, qs, per_page=50):
    page = Paginator(qs, per_page).get_page(request.GET.get("page"))
    params = request.GET.copy()
    params.pop("page", None)
    page.querystring = params.urlencode()
    return page


def parse_month(value, default=None):
    """'2026-10' -> date(2026, 10, 1)."""
    try:
        y, m = map(int, str(value).split("-")[:2])
        return date(y, m, 1)
    except (TypeError, ValueError):
        return default or timezone.localdate().replace(day=1)


def safe_next(request, fallback):
    from django.utils.http import url_has_allowed_host_and_scheme

    nxt = request.POST.get("next") or request.GET.get("next")
    if nxt and url_has_allowed_host_and_scheme(nxt, allowed_hosts={request.get_host()}):
        return nxt
    return fallback

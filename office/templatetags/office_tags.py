from decimal import Decimal

from django import template
from django.contrib.humanize.templatetags.humanize import intcomma

from ..results import ordinal as _ordinal

register = template.Library()


@register.filter
def rs(value):
    """2500 -> 'Rs. 2,500'"""
    try:
        n = int(round(float(value or 0)))
    except (TypeError, ValueError):
        return value
    sign = "−" if n < 0 else ""
    return f"{sign}Rs. {intcomma(abs(n))}"


@register.filter
def num(value):
    """45.0 -> 45, 45.5 -> 45.5"""
    if value is None or value == "":
        return ""
    try:
        return f"{float(value):g}"
    except (TypeError, ValueError):
        return value


@register.filter
def pct(value):
    return "–" if value is None else f"{value:g}%"


@register.filter
def ordinal(n):
    return _ordinal(n)


@register.filter
def in_csv(name, csv_names):
    """True if name is one of the comma-separated names (exact match)."""
    return name in [n.strip() for n in str(csv_names).split(",")]


@register.filter
def get_item(mapping, key):
    return None if mapping is None else mapping.get(key)


@register.filter
def text_on(hex_colour):
    """Black or white text, whichever reads better on the class colour."""
    try:
        h = hex_colour.lstrip("#")
        r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    except (ValueError, AttributeError):
        return "#fff"
    return "#1b1b1b" if (0.299 * r + 0.587 * g + 0.114 * b) > 160 else "#ffffff"


@register.simple_tag(takes_context=True)
def active(context, *prefixes):
    path = context["request"].path
    for p in prefixes:
        if (p == "/" and path == "/") or (p != "/" and path.startswith(p)):
            return "active"
    return ""


@register.simple_tag
def money_words(value):
    """Amount in words for receipts, e.g. 'One thousand five hundred rupees only'."""
    try:
        n = int(Decimal(value or 0))
    except Exception:
        return ""
    if n == 0:
        return "Zero rupees"
    ones = ["", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven",
            "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen"]
    tens = ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"]

    def below_1000(x):
        words = []
        if x >= 100:
            words += [ones[x // 100], "hundred"]
            x %= 100
        if x >= 20:
            words.append(tens[x // 10] + ("-" + ones[x % 10] if x % 10 else ""))
        elif x:
            words.append(ones[x])
        return " ".join(words)

    parts = []
    for size, label in ((10_000_000, "crore"), (100_000, "lakh"), (1000, "thousand")):
        if n >= size:
            parts.append(f"{below_1000(n // size)} {label}")
            n %= size
    if n:
        parts.append(below_1000(n))
    text = " ".join(parts)
    return text[0].upper() + text[1:] + " rupees only"


@register.filter
def fill(value, width="40mm"):
    """The value, or a dotted line to write on by hand when it's empty (certificates)."""
    from django.utils.html import conditional_escape, format_html

    if value in (None, ""):
        return format_html('<span class="blank" style="min-width:{}"></span>', width)
    return format_html('<b class="val">{}</b>', conditional_escape(value))


@register.filter
def fill_date(value, width="32mm"):
    if not value:
        return fill("", width)
    try:
        return fill(value.strftime("%d-%m-%Y"))
    except AttributeError:
        return fill(value, width)


@register.simple_tag
def vstatic(path):
    """Static file address with its change time added, so the browser always loads the newest version
    after an update instead of an old copy it kept."""
    import os

    from django.conf import settings
    from django.templatetags.static import static

    try:
        v = int(os.path.getmtime(settings.BASE_DIR / "static" / path))
    except OSError:
        v = 0
    return f"{static(path)}?v={v}"

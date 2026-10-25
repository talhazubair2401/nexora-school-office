from django.conf import settings
from django.urls import include, re_path, path
from django.views.static import serve

from office.demo import demo_login

urlpatterns = [
    path("demo-login/", demo_login, name="demo_login"),
    path("", include("office.urls")),
    # Serve the app's own CSS/JS/images and uploaded photos (local computer only).
    re_path(r"^static/(?P<path>.*)$", serve, {"document_root": settings.BASE_DIR / "static"}),
    re_path(r"^media/(?P<path>.*)$", serve, {"document_root": settings.MEDIA_ROOT}),
]

handler404 = "office.views.errors.not_found"
handler500 = "office.views.errors.server_error"

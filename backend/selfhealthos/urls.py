from django.conf import settings
from django.contrib import admin
from django.urls import path, re_path
from django.views.static import serve as serve_static

from apps.api.api import api

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/", api.urls),
    # Uploaded media (avatars, diet/doc photos). There is no bundled reverse
    # proxy in this project (see CLAUDE.md) to hand this off to, and
    # WhiteNoise only covers STATIC_URL, not user-uploaded files - so Django
    # serves it directly, unconditionally rather than DEBUG-gated. Django's
    # own docs call this unfit for a high-traffic production site; at the
    # scale a self-hosted instance actually runs at, it's the same tradeoff
    # WhiteNoise already makes for static files, and it means this keeps
    # working with or without an operator's own reverse proxy in front.
    re_path(r"^media/(?P<path>.*)$", serve_static, {"document_root": settings.MEDIA_ROOT}),
]

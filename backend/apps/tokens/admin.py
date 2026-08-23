from django.contrib import admin

from .models import AccessToken


@admin.register(AccessToken)
class AccessTokenAdmin(admin.ModelAdmin):
    list_display = ("name", "user", "kind", "masked", "is_live", "last_used_at", "expires_at")
    list_filter = ("kind", "revoked_at")
    search_fields = ("name",)
    # The hash is not a secret worth showing, and it is not editable either -
    # a token whose hash can be typed in is a token anyone can mint.
    readonly_fields = ("lookup", "token_hash", "last_used_at", "last_used_ip")

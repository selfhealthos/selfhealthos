from django.contrib import admin

from .models import FriendPref, Friendship


@admin.register(Friendship)
class FriendshipAdmin(admin.ModelAdmin):
    list_display = ["user_low", "user_high", "status", "requested_by", "responded_at"]
    list_filter = ["status"]
    search_fields = ["user_low__username", "user_high__username"]
    raw_id_fields = ["user_low", "user_high", "requested_by", "blocked_by"]


@admin.register(FriendPref)
class FriendPrefAdmin(admin.ModelAdmin):
    list_display = ["owner", "friend", "workout_partner"]
    list_filter = ["workout_partner"]
    search_fields = ["owner__username", "friend__username"]
    raw_id_fields = ["owner", "friend"]

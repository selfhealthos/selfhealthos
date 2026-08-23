from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import User


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    list_display = ["username", "first_name", "last_name", "is_staff", "is_active"]
    list_filter = ["is_staff", "is_superuser", "is_active"]
    search_fields = ["username", "first_name", "last_name"]

    fieldsets = (
        *DjangoUserAdmin.fieldsets,
        ("Health profile", {"fields": ("birth_date", "sex", "avatar", "timezone", "locale")}),
    )

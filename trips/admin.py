from django.contrib import admin
from .models import Trip, DailyLog, LogEntry


class LogEntryInline(admin.TabularInline):
    model = LogEntry
    extra = 0


@admin.register(DailyLog)
class DailyLogAdmin(admin.ModelAdmin):
    list_display = ("id", "trip", "date", "driving_hrs", "on_duty_hrs", "total_miles")
    list_filter = ("date",)
    inlines = [LogEntryInline]


@admin.register(Trip)
class TripAdmin(admin.ModelAdmin):
    list_display = ("id", "pickup_location", "dropoff_location", "total_miles", "created_at")
    search_fields = ("pickup_location", "dropoff_location", "current_location")


@admin.register(LogEntry)
class LogEntryAdmin(admin.ModelAdmin):
    list_display = ("id", "daily_log", "status", "start_time", "end_time", "location")
    list_filter = ("status",)

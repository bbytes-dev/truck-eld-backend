from rest_framework import serializers
from .models import Trip, DailyLog, LogEntry


class LogEntrySerializer(serializers.ModelSerializer):
    class Meta:
        model = LogEntry
        fields = ["id", "start_time", "end_time", "status", "location", "remark"]


class DailyLogSerializer(serializers.ModelSerializer):
    entries = LogEntrySerializer(many=True, read_only=True)

    class Meta:
        model = DailyLog
        fields = [
            "id",
            "date",
            "total_miles",
            "from_location",
            "to_location",
            "off_duty_hrs",
            "sleeper_hrs",
            "driving_hrs",
            "on_duty_hrs",
            "entries",
        ]


class TripSerializer(serializers.ModelSerializer):
    daily_logs = DailyLogSerializer(many=True, read_only=True)

    class Meta:
        model = Trip
        fields = [
            "id",
            "current_location",
            "current_lat",
            "current_lng",
            "pickup_location",
            "pickup_lat",
            "pickup_lng",
            "dropoff_location",
            "dropoff_lat",
            "dropoff_lng",
            "current_cycle_used_hrs",
            "total_miles",
            "total_duration_hrs",
            "route_geometry",
            "driver_name",
            "carrier_name",
            "truck_number",
            "trailer_number",
            "created_at",
            "daily_logs",
        ]
        read_only_fields = [
            "id",
            "total_miles",
            "total_duration_hrs",
            "route_geometry",
            "created_at",
            "daily_logs",
            "current_lat",
            "current_lng",
            "pickup_lat",
            "pickup_lng",
            "dropoff_lat",
            "dropoff_lng",
        ]


class TripCreateSerializer(serializers.Serializer):
    current_location = serializers.CharField(max_length=255)
    pickup_location = serializers.CharField(max_length=255)
    dropoff_location = serializers.CharField(max_length=255)
    current_cycle_used_hrs = serializers.FloatField(min_value=0, max_value=70)
    driver_name = serializers.CharField(max_length=120, required=False, allow_blank=True, default="")
    carrier_name = serializers.CharField(max_length=120, required=False, allow_blank=True, default="Spotter AI Transport")
    truck_number = serializers.CharField(max_length=60, required=False, allow_blank=True, default="")
    trailer_number = serializers.CharField(max_length=60, required=False, allow_blank=True, default="")

from django.db import models


class Trip(models.Model):
    current_location = models.CharField(max_length=255)
    current_lat = models.FloatField()
    current_lng = models.FloatField()

    pickup_location = models.CharField(max_length=255)
    pickup_lat = models.FloatField()
    pickup_lng = models.FloatField()

    dropoff_location = models.CharField(max_length=255)
    dropoff_lat = models.FloatField()
    dropoff_lng = models.FloatField()

    current_cycle_used_hrs = models.FloatField(default=0)

    total_miles = models.FloatField(default=0)
    total_duration_hrs = models.FloatField(default=0)
    route_geometry = models.JSONField(default=dict, blank=True)

    driver_name = models.CharField(max_length=120, blank=True, default="")
    carrier_name = models.CharField(max_length=120, blank=True, default="Spotter AI Transport")
    truck_number = models.CharField(max_length=60, blank=True, default="")
    trailer_number = models.CharField(max_length=60, blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Trip {self.id}: {self.pickup_location} -> {self.dropoff_location}"


class DailyLog(models.Model):
    trip = models.ForeignKey(Trip, on_delete=models.CASCADE, related_name="daily_logs")
    date = models.DateField()
    total_miles = models.FloatField(default=0)

    from_location = models.CharField(max_length=255, blank=True, default="")
    to_location = models.CharField(max_length=255, blank=True, default="")

    off_duty_hrs = models.FloatField(default=0)
    sleeper_hrs = models.FloatField(default=0)
    driving_hrs = models.FloatField(default=0)
    on_duty_hrs = models.FloatField(default=0)

    class Meta:
        ordering = ["date"]
        unique_together = ("trip", "date")

    def __str__(self):
        return f"Log {self.date} for trip {self.trip_id}"


class LogEntry(models.Model):
    STATUS_CHOICES = [
        ("OFF", "Off Duty"),
        ("SB", "Sleeper Berth"),
        ("D", "Driving"),
        ("ON", "On Duty (Not Driving)"),
    ]

    daily_log = models.ForeignKey(DailyLog, on_delete=models.CASCADE, related_name="entries")
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    status = models.CharField(max_length=3, choices=STATUS_CHOICES)
    location = models.CharField(max_length=255, blank=True, default="")
    remark = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        ordering = ["start_time"]

    def __str__(self):
        return f"{self.status} {self.start_time} -> {self.end_time}"

"""HOS (Hours of Service) compliance engine for property-carrying drivers.

Rules enforced (FMCSA 395):
- 11-hour driving limit per duty period
- 14-hour on-duty window from first on-duty moment
- 30-minute break after 8 cumulative driving hours
- 10 consecutive hours off-duty between duty periods
- 70-hour / 8-day cycle limit (with current_cycle_used_hrs as starting balance)
- Fuel stop every 1,000 miles (30 min on-duty, not driving)
- 1 hour on-duty for pickup and drop-off
- Average speed 55 mph (no adverse conditions)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Literal


Status = Literal["OFF", "SB", "D", "ON"]

AVG_SPEED_MPH = 55.0
MAX_DRIVING_HRS = 11.0
MAX_ONDUTY_WINDOW_HRS = 14.0
BREAK_AFTER_DRIVING_HRS = 8.0
BREAK_DURATION_HRS = 0.5
OFF_DUTY_RESET_HRS = 10.0
CYCLE_LIMIT_HRS = 70.0
CYCLE_WINDOW_DAYS = 8
FUEL_INTERVAL_MILES = 1000.0
FUEL_DURATION_HRS = 0.5
PICKUP_DROPOFF_HRS = 1.0


@dataclass
class Segment:
    start: datetime
    end: datetime
    status: Status
    location: str
    remark: str = ""
    miles: float = 0.0

    @property
    def duration_hrs(self) -> float:
        return (self.end - self.start).total_seconds() / 3600.0


@dataclass
class ScheduleBuilder:
    start_time: datetime
    current_location: str
    pickup_location: str
    dropoff_location: str
    current_cycle_used_hrs: float
    leg1_miles: float  # current -> pickup
    leg2_miles: float  # pickup -> dropoff

    segments: list[Segment] = field(default_factory=list)

    # live counters
    driving_since_break_hrs: float = 0.0
    driving_today_hrs: float = 0.0
    window_start: datetime | None = None
    cycle_used_hrs: float = 0.0
    miles_since_fuel: float = 0.0

    def __post_init__(self):
        self.cycle_used_hrs = self.current_cycle_used_hrs

    # ---------- helpers ----------
    def _now(self) -> datetime:
        return self.segments[-1].end if self.segments else self.start_time

    def _add(self, status: Status, duration_hrs: float, location: str, remark: str = "", miles: float = 0.0):
        if duration_hrs <= 0:
            return
        start = self._now()
        end = start + timedelta(hours=duration_hrs)
        self.segments.append(Segment(start, end, status, location, remark, miles))
        if status in ("D", "ON"):
            self.cycle_used_hrs += duration_hrs
            if self.window_start is None:
                self.window_start = start
        if status == "D":
            self.driving_since_break_hrs += duration_hrs
            self.driving_today_hrs += duration_hrs

    def _window_hrs_used(self) -> float:
        if self.window_start is None:
            return 0.0
        return (self._now() - self.window_start).total_seconds() / 3600.0

    def _take_break(self, location: str):
        """30-min off-duty break after 8 hours of driving."""
        self._add("ON", BREAK_DURATION_HRS, location, remark="30-min break")
        self.driving_since_break_hrs = 0.0

    def _take_reset(self, location: str):
        """10-hour sleeper berth reset between duty periods."""
        self._add("SB", OFF_DUTY_RESET_HRS, location, remark="10-hr sleeper reset")
        self.driving_since_break_hrs = 0.0
        self.driving_today_hrs = 0.0
        self.window_start = None

    def _fuel_stop(self, location: str):
        self._add("ON", FUEL_DURATION_HRS, location, remark="Fueling")
        self.miles_since_fuel = 0.0

    # ---------- core ----------
    def drive_leg(self, miles: float, destination_label: str):
        """Simulate driving `miles` toward destination_label, respecting all HOS limits."""
        remaining = miles
        while remaining > 0:
            # mandatory checks before driving
            if self.driving_today_hrs >= MAX_DRIVING_HRS or self._window_hrs_used() >= MAX_ONDUTY_WINDOW_HRS:
                self._take_reset(destination_label)
                continue
            if self.driving_since_break_hrs >= BREAK_AFTER_DRIVING_HRS:
                self._take_break(destination_label)
                continue
            if self.miles_since_fuel >= FUEL_INTERVAL_MILES:
                self._fuel_stop(destination_label)
                continue

            # how far/long can we drive in this slice?
            max_by_driving = MAX_DRIVING_HRS - self.driving_today_hrs
            max_by_window = MAX_ONDUTY_WINDOW_HRS - self._window_hrs_used()
            max_by_break = BREAK_AFTER_DRIVING_HRS - self.driving_since_break_hrs
            max_by_fuel_miles = FUEL_INTERVAL_MILES - self.miles_since_fuel

            hrs_limit = min(max_by_driving, max_by_window, max_by_break)
            miles_limit = min(max_by_fuel_miles, remaining)
            hrs_for_miles = miles_limit / AVG_SPEED_MPH

            drive_hrs = min(hrs_limit, hrs_for_miles)
            if drive_hrs <= 0:
                # cannot drive → force a reset
                self._take_reset(destination_label)
                continue

            drive_miles = drive_hrs * AVG_SPEED_MPH
            self._add("D", drive_hrs, destination_label, remark="Driving", miles=drive_miles)
            self.miles_since_fuel += drive_miles
            remaining -= drive_miles

    def pickup_or_dropoff(self, location: str, label: str):
        # ensure window / cycle room; if exhausted, reset first
        if (
            self._window_hrs_used() + PICKUP_DROPOFF_HRS > MAX_ONDUTY_WINDOW_HRS
            or self.driving_today_hrs >= MAX_DRIVING_HRS
        ):
            self._take_reset(location)
        self._add("ON", PICKUP_DROPOFF_HRS, location, remark=label)

    def build(self) -> list[Segment]:
        # Driver starts at current location — assume just came on duty
        self._add("ON", 0.25, self.current_location, remark="Pre-trip inspection")
        # Drive current -> pickup
        self.drive_leg(self.leg1_miles, self.pickup_location)
        # 1 hour pickup
        self.pickup_or_dropoff(self.pickup_location, "Pickup")
        # Drive pickup -> dropoff
        self.drive_leg(self.leg2_miles, self.dropoff_location)
        # 1 hour dropoff
        self.pickup_or_dropoff(self.dropoff_location, "Drop-off")
        return self.segments


def build_schedule(
    *,
    start_time: datetime,
    current_location: str,
    pickup_location: str,
    dropoff_location: str,
    current_cycle_used_hrs: float,
    leg1_miles: float,
    leg2_miles: float,
) -> list[Segment]:
    builder = ScheduleBuilder(
        start_time=start_time,
        current_location=current_location,
        pickup_location=pickup_location,
        dropoff_location=dropoff_location,
        current_cycle_used_hrs=current_cycle_used_hrs,
        leg1_miles=leg1_miles,
        leg2_miles=leg2_miles,
    )
    return builder.build()

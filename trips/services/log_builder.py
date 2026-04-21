"""Turn a flat list of Segments into persisted DailyLog + LogEntry rows."""
from __future__ import annotations

from datetime import datetime, timedelta, date as date_type, time

from ..models import Trip, DailyLog, LogEntry
from .hos_calculator import Segment


def _split_at_midnight(seg: Segment) -> list[Segment]:
    """Split a segment if it crosses midnight so each piece lives on one day."""
    out: list[Segment] = []
    start = seg.start
    end = seg.end
    while start.date() != end.date():
        boundary = datetime.combine(
            start.date() + timedelta(days=1),
            time.min,
            tzinfo=start.tzinfo,
        )
        out.append(Segment(start, boundary, seg.status, seg.location, seg.remark, 0.0))
        start = boundary
    out.append(Segment(start, end, seg.status, seg.location, seg.remark, seg.miles))
    return out


def _fill_day(day: date_type, segs: list[Segment]) -> list[Segment]:
    """Cover the full [00:00, 24:00) of `day`, filling any gap with OFF."""
    if not segs:
        return segs
    tz = segs[0].start.tzinfo
    day_start = datetime.combine(day, time.min, tzinfo=tz)
    day_end = day_start + timedelta(days=1)

    segs.sort(key=lambda s: s.start)

    # clamp each segment to the day window
    clamped: list[Segment] = []
    for s in segs:
        start = max(s.start, day_start)
        end = min(s.end, day_end)
        if end > start:
            clamped.append(Segment(start, end, s.status, s.location, s.remark, s.miles))

    # fill any gap (including before-first and after-last) with OFF
    out: list[Segment] = []
    cursor = day_start
    last_loc = clamped[0].location if clamped else ""
    for s in clamped:
        if s.start > cursor:
            out.append(Segment(cursor, s.start, "OFF", last_loc, "Off duty", 0.0))
        out.append(s)
        cursor = s.end
        last_loc = s.location
    if cursor < day_end:
        out.append(Segment(cursor, day_end, "OFF", last_loc, "Off duty", 0.0))
    return out


def persist_schedule(trip: Trip, segments: list[Segment]) -> list[DailyLog]:
    """Create DailyLog + LogEntry rows for the given trip."""
    trip.daily_logs.all().delete()

    # split midnight-crossing segments
    daily_segments: dict[date_type, list[Segment]] = {}
    for seg in segments:
        for piece in _split_at_midnight(seg):
            daily_segments.setdefault(piece.start.date(), []).append(piece)

    logs: list[DailyLog] = []
    for day in sorted(daily_segments.keys()):
        segs = _fill_day(day, daily_segments[day])
        if not segs:
            continue

        off = sum(s.duration_hrs for s in segs if s.status == "OFF")
        sb = sum(s.duration_hrs for s in segs if s.status == "SB")
        dr = sum(s.duration_hrs for s in segs if s.status == "D")
        on = sum(s.duration_hrs for s in segs if s.status == "ON")

        miles_today = sum(s.miles for s in segs)

        log = DailyLog.objects.create(
            trip=trip,
            date=day,
            total_miles=round(miles_today, 1),
            from_location=segs[0].location,
            to_location=segs[-1].location,
            off_duty_hrs=round(off, 2),
            sleeper_hrs=round(sb, 2),
            driving_hrs=round(dr, 2),
            on_duty_hrs=round(on, 2),
        )
        for s in segs:
            LogEntry.objects.create(
                daily_log=log,
                start_time=s.start,
                end_time=s.end,
                status=s.status,
                location=s.location,
                remark=s.remark,
            )
        logs.append(log)

    return logs

"""Turn a flat list of Segments into persisted DailyLog + LogEntry rows."""
from __future__ import annotations

from datetime import datetime, timedelta, date as date_type

from django.utils import timezone

from ..models import Trip, DailyLog, LogEntry
from .hos_calculator import Segment


def _split_at_midnight(seg: Segment) -> list[Segment]:
    """Split a segment if it crosses midnight (so each piece lives on one DailyLog)."""
    out: list[Segment] = []
    start = seg.start
    end = seg.end
    while start.date() != end.date():
        boundary = datetime.combine(start.date() + timedelta(days=1), datetime.min.time(), tzinfo=start.tzinfo)
        out.append(Segment(start, boundary, seg.status, seg.location, seg.remark, 0.0))
        start = boundary
    out.append(Segment(start, end, seg.status, seg.location, seg.remark, seg.miles))
    return out


def persist_schedule(trip: Trip, segments: list[Segment]) -> list[DailyLog]:
    """Create DailyLog + LogEntry rows for the given trip."""
    # wipe any previous logs for this trip (idempotent re-runs)
    trip.daily_logs.all().delete()

    # split midnight-crossing segments
    daily_segments: dict[date_type, list[Segment]] = {}
    for seg in segments:
        for piece in _split_at_midnight(seg):
            daily_segments.setdefault(piece.start.date(), []).append(piece)

    logs: list[DailyLog] = []
    for day, segs in sorted(daily_segments.items()):
        off = sum(s.duration_hrs for s in segs if s.status == "OFF")
        sb = sum(s.duration_hrs for s in segs if s.status == "SB")
        dr = sum(s.duration_hrs for s in segs if s.status == "D")
        on = sum(s.duration_hrs for s in segs if s.status == "ON")

        # fill remaining hours of the day as OFF to reach 24h (for the final day)
        total = off + sb + dr + on
        filler = max(0.0, 24.0 - total)
        if filler > 0:
            last_end = segs[-1].end
            fill_end = last_end + timedelta(hours=filler)
            segs.append(Segment(last_end, fill_end, "OFF", segs[-1].location, "Off duty", 0.0))
            off += filler

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

"""Generate a landscape PDF of daily log sheets using reportlab."""
from __future__ import annotations

from datetime import datetime, time, timezone as dt_tz
from io import BytesIO

from reportlab.lib.colors import Color, HexColor
from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas

from ..models import Trip


STATUS_ROW = {"OFF": 0, "SB": 1, "D": 2, "ON": 3}
STATUS_LABEL_FIELD = {
    "OFF": "off_duty_hrs",
    "SB": "sleeper_hrs",
    "D": "driving_hrs",
    "ON": "on_duty_hrs",
}
STATUS_SHADE = {
    "OFF": Color(0.58, 0.64, 0.72, alpha=0.12),
    "SB":  Color(0.39, 0.40, 0.95, alpha=0.18),
    "D":   Color(0.06, 0.72, 0.51, alpha=0.18),
    "ON":  Color(0.96, 0.62, 0.04, alpha=0.22),
}


def _draw_log_sheet(c: canvas.Canvas, trip: Trip, daily_log):
    page_w, page_h = landscape(letter)

    # --- Header ---
    c.setFillColor(HexColor("#0f172a"))
    c.setFont("Helvetica-Bold", 16)
    c.drawString(0.5 * inch, page_h - 0.5 * inch, "Driver's Daily Log (24 hours)")
    c.setFont("Helvetica", 10)
    c.drawString(0.5 * inch, page_h - 0.75 * inch, f"Date: {daily_log.date.strftime('%m/%d/%Y')}")
    c.drawString(3.0 * inch, page_h - 0.75 * inch, f"From: {(daily_log.from_location or '')[:40]}")
    c.drawString(6.0 * inch, page_h - 0.75 * inch, f"To: {(daily_log.to_location or '')[:40]}")

    c.drawString(0.5 * inch, page_h - 1.0 * inch, f"Total Miles: {daily_log.total_miles}")
    c.drawString(3.0 * inch, page_h - 1.0 * inch, f"Carrier: {trip.carrier_name}")
    c.drawString(6.0 * inch, page_h - 1.0 * inch, f"Truck/Trailer: {trip.truck_number} / {trip.trailer_number}")

    # --- Grid geometry ---
    grid_x = 1.4 * inch
    grid_y = page_h - 3.8 * inch
    grid_w = 8.6 * inch
    grid_h = 2.1 * inch
    row_h = grid_h / 4

    labels = ["1. Off Duty", "2. Sleeper Berth", "3. Driving", "4. On Duty"]

    # day-start anchored to the DailyLog's date, in UTC (matches DB tz)
    day_start = datetime.combine(daily_log.date, time.min, tzinfo=dt_tz.utc)

    entries = list(daily_log.entries.all())

    # --- status shading (colored blocks under the duty line) ---
    for e in entries:
        start_hr = max(0.0, min(24.0, (e.start_time - day_start).total_seconds() / 3600.0))
        end_hr = max(0.0, min(24.0, (e.end_time - day_start).total_seconds() / 3600.0))
        if end_hr <= start_hr:
            continue
        row = STATUS_ROW.get(e.status, 0)
        x1 = grid_x + (grid_w / 24.0) * start_hr
        x2 = grid_x + (grid_w / 24.0) * end_hr
        y_row = grid_y + grid_h - (row + 1) * row_h
        c.setFillColor(STATUS_SHADE.get(e.status, Color(0, 0, 0, 0)))
        c.rect(x1, y_row, x2 - x1, row_h, stroke=0, fill=1)

    # --- row frames + labels ---
    c.setFillColor(HexColor("#0f172a"))
    c.setStrokeColor(HexColor("#cbd5e1"))
    c.setLineWidth(0.7)
    for i, label in enumerate(labels):
        y = grid_y + grid_h - (i + 1) * row_h
        c.setFont("Helvetica", 8)
        c.drawRightString(grid_x - 0.08 * inch, y + row_h / 2 - 3, label)
        c.rect(grid_x, y, grid_w, row_h, stroke=1, fill=0)

    # --- 15-min minor ticks + hour ticks ---
    c.setStrokeColor(HexColor("#e2e8f0"))
    c.setLineWidth(0.4)
    for q in range(24 * 4 + 1):
        x = grid_x + (grid_w / (24 * 4)) * q
        c.line(x, grid_y, x, grid_y + grid_h)
    c.setStrokeColor(HexColor("#94a3b8"))
    c.setLineWidth(0.5)
    for h in range(25):
        x = grid_x + (grid_w / 24) * h
        c.line(x, grid_y, x, grid_y + grid_h)

    # --- hour numbers above grid ---
    c.setFont("Helvetica-Bold", 7.5)
    c.setFillColor(HexColor("#334155"))
    for h in range(25):
        x = grid_x + (grid_w / 24) * h
        label = "Mid" if h in (0, 24) else ("Noon" if h == 12 else str(h % 12 or 12))
        c.drawCentredString(x, grid_y + grid_h + 4, label)

    # --- duty step line ---
    c.setStrokeColor(HexColor("#4f46e5"))
    c.setLineWidth(1.6)
    c.setLineJoin(1)  # round
    c.setLineCap(1)   # round

    path = c.beginPath()
    started = False
    prev_x = prev_y = None
    for e in entries:
        start_hr = max(0.0, min(24.0, (e.start_time - day_start).total_seconds() / 3600.0))
        end_hr = max(0.0, min(24.0, (e.end_time - day_start).total_seconds() / 3600.0))
        if end_hr <= start_hr:
            continue
        row = STATUS_ROW.get(e.status, 0)
        y = grid_y + grid_h - (row + 0.5) * row_h
        x1 = grid_x + (grid_w / 24.0) * start_hr
        x2 = grid_x + (grid_w / 24.0) * end_hr

        if not started:
            path.moveTo(x1, y)
            started = True
        else:
            # connect previous endpoint (x1 == prev_x) via vertical line
            path.lineTo(x1, y)
        path.lineTo(x2, y)
        prev_x, prev_y = x2, y
    if started:
        c.drawPath(path, stroke=1, fill=0)

    # --- totals column ---
    c.setFillColor(HexColor("#0f172a"))
    c.setFont("Helvetica-Bold", 9)
    totals_x = grid_x + grid_w + 0.12 * inch
    for i, key in enumerate(["OFF", "SB", "D", "ON"]):
        y = grid_y + grid_h - (i + 1) * row_h + row_h / 2 - 3
        hrs = getattr(daily_log, STATUS_LABEL_FIELD[key])
        c.drawString(totals_x, y, f"{hrs:.2f}h")

    # --- Remarks ---
    c.setFont("Helvetica-Bold", 10)
    c.drawString(0.5 * inch, grid_y - 0.4 * inch, "Remarks:")
    c.setFont("Helvetica", 8)
    c.setFillColor(HexColor("#334155"))
    y = grid_y - 0.6 * inch
    skip_remarks = {"off duty", "driving"}
    for e in entries:
        if not e.remark or e.remark.strip().lower() in skip_remarks:
            continue
        c.drawString(
            0.6 * inch,
            y,
            f"{e.start_time.strftime('%H:%M')} — {e.remark} @ {(e.location or '')[:60]}",
        )
        y -= 0.18 * inch
        if y < 0.6 * inch:
            break

    # --- Summary strip ---
    c.setFont("Helvetica-Bold", 11)
    c.setFillColor(HexColor("#0f172a"))
    total_driving = daily_log.driving_hrs
    total_onduty = daily_log.driving_hrs + daily_log.on_duty_hrs
    c.drawString(
        0.5 * inch,
        0.4 * inch,
        f"Total Driving: {total_driving:.2f}h   |   Total On-Duty (D+ON): {total_onduty:.2f}h",
    )


def generate_trip_pdf(trip: Trip) -> bytes:
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=landscape(letter))
    logs = list(trip.daily_logs.all())
    for log in logs:
        _draw_log_sheet(c, trip, log)
        c.showPage()
    c.save()
    return buf.getvalue()

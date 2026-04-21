"""Generate a simple PDF of daily log sheets using reportlab."""
from __future__ import annotations

from io import BytesIO
from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas

from ..models import Trip


STATUS_ROW = {"OFF": 0, "SB": 1, "D": 2, "ON": 3}
STATUS_LABEL = {
    "OFF": "Off Duty",
    "SB": "Sleeper Berth",
    "D": "Driving",
    "ON": "On Duty (not driving)",
}


def _draw_log_sheet(c: canvas.Canvas, trip: Trip, daily_log):
    width, height = landscape(letter)

    # Header
    c.setFont("Helvetica-Bold", 16)
    c.drawString(0.5 * inch, height - 0.5 * inch, "Driver's Daily Log (24 hours)")
    c.setFont("Helvetica", 10)
    c.drawString(0.5 * inch, height - 0.75 * inch, f"Date: {daily_log.date.strftime('%m/%d/%Y')}")
    c.drawString(3.0 * inch, height - 0.75 * inch, f"From: {daily_log.from_location[:40]}")
    c.drawString(6.0 * inch, height - 0.75 * inch, f"To: {daily_log.to_location[:40]}")

    c.drawString(0.5 * inch, height - 1.0 * inch, f"Total Miles: {daily_log.total_miles}")
    c.drawString(3.0 * inch, height - 1.0 * inch, f"Carrier: {trip.carrier_name}")
    c.drawString(6.0 * inch, height - 1.0 * inch, f"Truck/Trailer: {trip.truck_number} / {trip.trailer_number}")

    # Grid
    grid_x = 1.0 * inch
    grid_y = height - 3.5 * inch
    grid_w = 9.0 * inch
    grid_h = 2.0 * inch
    row_h = grid_h / 4

    labels = ["1. Off Duty", "2. Sleeper Berth", "3. Driving", "4. On Duty"]
    for i, label in enumerate(labels):
        y = grid_y + grid_h - (i + 1) * row_h
        c.setFont("Helvetica", 8)
        c.drawRightString(grid_x - 0.05 * inch, y + row_h / 2 - 3, label)
        c.setStrokeColorRGB(0.7, 0.7, 0.7)
        c.rect(grid_x, y, grid_w, row_h, stroke=1, fill=0)

    # Hour columns
    c.setFont("Helvetica", 7)
    for h in range(25):
        x = grid_x + (grid_w / 24) * h
        c.setStrokeColorRGB(0.85, 0.85, 0.85)
        c.line(x, grid_y, x, grid_y + grid_h)
        if h < 24:
            label = "Mid" if h == 0 else ("Noon" if h == 12 else str(h % 12 or 12))
            c.drawString(x + 2, grid_y + grid_h + 2, label)

    # Draw status line
    entries = list(daily_log.entries.all())
    c.setStrokeColorRGB(0.1, 0.4, 0.9)
    c.setLineWidth(1.8)

    day_start = entries[0].start_time.replace(hour=0, minute=0, second=0, microsecond=0) if entries else None

    for i, e in enumerate(entries):
        if day_start is None:
            continue
        start_hr = (e.start_time - day_start).total_seconds() / 3600.0
        end_hr = (e.end_time - day_start).total_seconds() / 3600.0
        row = STATUS_ROW.get(e.status, 0)
        y = grid_y + grid_h - (row + 0.5) * row_h
        x1 = grid_x + (grid_w / 24) * start_hr
        x2 = grid_x + (grid_w / 24) * end_hr
        c.line(x1, y, x2, y)

        # vertical connector to next entry
        if i + 1 < len(entries):
            nxt = entries[i + 1]
            next_row = STATUS_ROW.get(nxt.status, 0)
            if next_row != row:
                y2 = grid_y + grid_h - (next_row + 0.5) * row_h
                c.line(x2, y, x2, y2)

    # Totals column
    c.setFont("Helvetica-Bold", 9)
    totals_x = grid_x + grid_w + 0.1 * inch
    for i, label in enumerate(["OFF", "SB", "D", "ON"]):
        y = grid_y + grid_h - (i + 1) * row_h + row_h / 2 - 3
        hrs = getattr(daily_log, {"OFF": "off_duty_hrs", "SB": "sleeper_hrs", "D": "driving_hrs", "ON": "on_duty_hrs"}[label])
        c.drawString(totals_x, y, f"{hrs:.2f}h")

    # Remarks
    c.setFont("Helvetica-Bold", 10)
    c.drawString(0.5 * inch, grid_y - 0.4 * inch, "Remarks:")
    c.setFont("Helvetica", 8)
    y = grid_y - 0.6 * inch
    for e in entries:
        if e.remark and e.remark.lower() != "off duty":
            c.drawString(
                0.6 * inch,
                y,
                f"{e.start_time.strftime('%H:%M')} — {e.remark} @ {e.location[:60]}",
            )
            y -= 0.18 * inch
            if y < 0.5 * inch:
                break

    # Summary
    c.setFont("Helvetica-Bold", 11)
    total_driving = daily_log.driving_hrs
    total_onduty = daily_log.driving_hrs + daily_log.on_duty_hrs
    c.drawString(
        0.5 * inch,
        0.4 * inch,
        f"Total Driving: {total_driving:.2f}h   |   Total On-Duty: {total_onduty:.2f}h",
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

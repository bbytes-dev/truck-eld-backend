from datetime import datetime, timezone as dt_timezone

from django.http import HttpResponse
from rest_framework import status, viewsets
from rest_framework.decorators import action, api_view
from rest_framework.response import Response

from .models import Trip
from .serializers import TripSerializer, TripCreateSerializer
from .services import geocoding, routing
from .services.hos_calculator import build_schedule
from .services.log_builder import persist_schedule
from .services.pdf_generator import generate_trip_pdf


class TripViewSet(viewsets.ModelViewSet):
    queryset = Trip.objects.all()
    serializer_class = TripSerializer
    http_method_names = ["get", "post", "delete"]

    def create(self, request, *args, **kwargs):
        payload = TripCreateSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        data = payload.validated_data

        try:
            cur = geocoding.geocode(data["current_location"])
            pick = geocoding.geocode(data["pickup_location"])
            drop = geocoding.geocode(data["dropoff_location"])
        except geocoding.GeocodingError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        try:
            route_info = routing.route(
                [
                    (cur["lng"], cur["lat"]),
                    (pick["lng"], pick["lat"]),
                    (drop["lng"], drop["lat"]),
                ]
            )
        except routing.RoutingError as exc:
            msg = str(exc)
            is_user_error = "drivable road route" in msg.lower() or "wrong country" in msg.lower()
            code = status.HTTP_400_BAD_REQUEST if is_user_error else status.HTTP_502_BAD_GATEWAY
            return Response({"detail": msg}, status=code)

        leg1_miles = route_info["leg_miles"][0] if len(route_info["leg_miles"]) >= 1 else 0.0
        leg2_miles = route_info["leg_miles"][1] if len(route_info["leg_miles"]) >= 2 else 0.0

        trip = Trip.objects.create(
            current_location=cur["display_name"],
            current_lat=cur["lat"],
            current_lng=cur["lng"],
            pickup_location=pick["display_name"],
            pickup_lat=pick["lat"],
            pickup_lng=pick["lng"],
            dropoff_location=drop["display_name"],
            dropoff_lat=drop["lat"],
            dropoff_lng=drop["lng"],
            current_cycle_used_hrs=data["current_cycle_used_hrs"],
            total_miles=round(route_info["miles"], 1),
            total_duration_hrs=round(route_info["duration_hrs"], 2),
            route_geometry=route_info["geometry"],
            driver_name=data.get("driver_name", ""),
            carrier_name=data.get("carrier_name") or "Spotter AI Transport",
            truck_number=data.get("truck_number", ""),
            trailer_number=data.get("trailer_number", ""),
        )

        segments = build_schedule(
            start_time=datetime.now(tz=dt_timezone.utc).replace(minute=0, second=0, microsecond=0),
            current_location=cur["display_name"],
            pickup_location=pick["display_name"],
            dropoff_location=drop["display_name"],
            current_cycle_used_hrs=data["current_cycle_used_hrs"],
            leg1_miles=leg1_miles,
            leg2_miles=leg2_miles,
        )
        persist_schedule(trip, segments)

        return Response(TripSerializer(trip).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["get"], url_path="logs")
    def logs(self, request, pk=None):
        trip = self.get_object()
        from .serializers import DailyLogSerializer
        return Response(DailyLogSerializer(trip.daily_logs.all(), many=True).data)

    @action(detail=True, methods=["get"], url_path="logs/pdf")
    def logs_pdf(self, request, pk=None):
        trip = self.get_object()
        pdf_bytes = generate_trip_pdf(trip)
        resp = HttpResponse(pdf_bytes, content_type="application/pdf")
        resp["Content-Disposition"] = f'attachment; filename="trip-{trip.id}-logs.pdf"'
        return resp


@api_view(["GET"])
def geocode_view(request):
    query = request.query_params.get("q", "").strip()
    if not query:
        return Response([])
    results = geocoding.autocomplete(query, limit=6)
    return Response(results)

"""Generate interactive trail map HTML from GPS data using Leaflet.js."""

import logging
from pathlib import Path

from .detector import Event
from .telemetry import Telemetry

logger = logging.getLogger(__name__)

_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html>
<head>
    <title>ShredFinder Trail Map</title>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <style>
        body {{ margin: 0; padding: 0; font-family: sans-serif; }}
        #map {{ width: 100%; height: 100vh; }}
        .legend {{ background: white; padding: 10px; border-radius: 5px;
                   box-shadow: 0 2px 6px rgba(0,0,0,0.3); line-height: 1.6; }}
        .legend i {{ width: 12px; height: 12px; display: inline-block;
                     margin-right: 5px; border-radius: 50%; }}
    </style>
</head>
<body>
    <div id="map"></div>
    <script>
        var tracks = {tracks_json};
        var events = {events_json};

        var map = L.map('map');
        L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
            attribution: '&copy; OpenStreetMap contributors | ShredFinder',
            maxZoom: 19
        }}).addTo(map);

        var bounds = L.latLngBounds();
        var colors = ['#e74c3c', '#3498db', '#2ecc71', '#f39c12', '#9b59b6',
                       '#1abc9c', '#e67e22', '#34495e'];

        tracks.forEach(function(track, idx) {{
            var color = colors[idx % colors.length];
            var latlngs = track.points.map(function(p) {{
                bounds.extend([p[0], p[1]]);
                return [p[0], p[1]];
            }});
            L.polyline(latlngs, {{color: color, weight: 3, opacity: 0.8}}).addTo(map)
                .bindPopup('<b>' + track.name + '</b>');
        }});

        var eventIcons = {{
            'jump': '\\u23eb',
            'spin': '\\ud83c\\udf00',
            'crash': '\\ud83d\\udca5',
            'speed': '\\u26a1'
        }};

        events.forEach(function(evt) {{
            var icon = eventIcons[evt.type] || '\\u2b50';
            var marker = L.marker([evt.lat, evt.lon], {{
                icon: L.divIcon({{
                    html: '<div style="font-size:20px;text-align:center">' + icon + '</div>',
                    iconSize: [25, 25],
                    className: ''
                }})
            }}).addTo(map);
            marker.bindPopup('<b>' + evt.type.toUpperCase() + '</b><br>' + evt.detail);
            bounds.extend([evt.lat, evt.lon]);
        }});

        if (bounds.isValid()) {{
            map.fitBounds(bounds, {{padding: [30, 30]}});
        }}

        var legend = L.control({{position: 'bottomright'}});
        legend.onAdd = function() {{
            var div = L.DomUtil.create('div', 'legend');
            div.innerHTML = '<b>ShredFinder</b><br>'
                + '\\u23eb Jump &nbsp; \\ud83c\\udf00 Spin<br>'
                + '\\ud83d\\udca5 Crash &nbsp; \\u26a1 Speed';
            return div;
        }};
        legend.addTo(map);
    </script>
</body>
</html>
"""


def write_trail_map(
    telemetry_by_file: dict[Path, Telemetry],
    events_by_file: dict[Path, list[Event]],
    output_path: Path,
) -> Path | None:
    """Generate an interactive HTML trail map with GPS tracks and event markers.

    Args:
        telemetry_by_file: Map of source file -> telemetry data.
        events_by_file: Map of source file -> detected events.
        output_path: Path to write the HTML file.

    Returns:
        Path to the written HTML file, or None if no GPS data.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    tracks = []
    event_markers = []

    for source_file, telemetry in telemetry_by_file.items():
        if not telemetry.has_gps or telemetry.gps_df.empty:
            continue

        gps = telemetry.gps_df
        # Filter out invalid GPS points
        valid = (gps["lat"].abs() > 0.001) & (gps["lon"].abs() > 0.001)
        valid_gps = gps[valid]

        if valid_gps.empty:
            continue

        # Downsample to every 5th point for performance
        sampled = valid_gps.iloc[::5]
        points = list(zip(
            sampled["lat"].round(6).tolist(),
            sampled["lon"].round(6).tolist(),
        ))

        tracks.append({
            "name": source_file.stem,
            "points": points,
        })

        # Add event markers with GPS coordinates
        if source_file in events_by_file:
            for event in events_by_file[source_file]:
                # Find closest GPS point to the event timestamp
                ts_diff = (valid_gps["ts_sec"] - event.peak_ts).abs()
                closest_idx = ts_diff.idxmin()
                lat = float(valid_gps.loc[closest_idx, "lat"])
                lon = float(valid_gps.loc[closest_idx, "lon"])

                primary_type = event.event_type.split("+")[0]
                detail = _format_event_detail(event)

                event_markers.append({
                    "type": primary_type,
                    "lat": round(lat, 6),
                    "lon": round(lon, 6),
                    "detail": detail,
                })

    if not tracks:
        logger.warning("No GPS data available for trail map")
        return None

    import json
    html = _HTML_TEMPLATE.format(
        tracks_json=json.dumps(tracks),
        events_json=json.dumps(event_markers),
    )

    output_path.write_text(html, encoding="utf-8")
    logger.info("Trail map written: %s (%d tracks, %d events)",
                output_path, len(tracks), len(event_markers))
    return output_path


def _format_event_detail(event: Event) -> str:
    """Format event detail for map popup."""
    parts = [f"at {event.peak_ts}s"]
    if event.airtime_sec > 0:
        parts.append(f"airtime: {event.airtime_sec}s")
    if event.spin_degrees > 0:
        parts.append(f"{event.spin_degrees:.0f}°")
    if event.peak_speed_mph > 0:
        parts.append(f"{event.peak_speed_mph} mph")
    if event.landing_quality:
        parts.append(event.landing_quality)
    if event.crash_severity > 0:
        parts.append(f"severity: {event.crash_severity}")
    return ", ".join(parts)

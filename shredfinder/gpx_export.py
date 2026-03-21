"""Export GPS tracks and event waypoints as GPX 1.1 XML."""

import logging
import xml.etree.ElementTree as ET
from pathlib import Path

from .detector import Event
from .telemetry import Telemetry

logger = logging.getLogger(__name__)


def write_gpx(telemetry_list: list[Telemetry], events: list[Event], output_path: Path) -> Path:
    """Generate a GPX 1.1 file from telemetry GPS data and detected events.

    Args:
        telemetry_list: List of Telemetry objects (each becomes a track).
        events: List of Event objects (each becomes a waypoint).
        output_path: Path to write the GPX file.

    Returns:
        The output path written.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    gpx_ns = "http://www.topografix.com/GPX/1/1"
    xsi_ns = "http://www.w3.org/2001/XMLSchema-instance"
    schema_loc = f"{gpx_ns} http://www.topografix.com/GPX/1/1/gpx.xsd"

    gpx = ET.Element("gpx", {
        "version": "1.1",
        "creator": "ShredFinder",
        "xmlns": gpx_ns,
        "xmlns:xsi": xsi_ns,
        "xsi:schemaLocation": schema_loc,
    })

    # Add event waypoints
    for event in events:
        wpt = ET.SubElement(gpx, "wpt", {
            "lat": "0.0",
            "lon": "0.0",
        })
        name = ET.SubElement(wpt, "name")
        name.text = event.event_type
        desc = ET.SubElement(wpt, "desc")
        # Build description based on event type
        desc_parts = [f"peak_ts={event.peak_ts}s"]
        if event.peak_speed_mph > 0:
            desc_parts.append(f"speed={event.peak_speed_mph}mph")
        if event.airtime_sec > 0:
            desc_parts.append(f"airtime={event.airtime_sec}s")
        if event.spin_degrees > 0:
            desc_parts.append(f"spin={event.spin_degrees}deg")
        if event.crash_severity > 0:
            desc_parts.append(f"severity={event.crash_severity}")
        if event.confidence > 0:
            desc_parts.append(f"confidence={event.confidence}")
        desc.text = ", ".join(desc_parts)

    # Add tracks from telemetry
    for telem in telemetry_list:
        if not telem.has_gps or telem.gps_df.empty:
            continue

        trk = ET.SubElement(gpx, "trk")
        trk_name = ET.SubElement(trk, "name")
        trk_name.text = telem.source_file.name
        trkseg = ET.SubElement(trk, "trkseg")

        for _, row in telem.gps_df.iterrows():
            lat = row.get("lat", 0.0)
            lon = row.get("lon", 0.0)
            alt = row.get("alt_m", 0.0)

            # Skip invalid GPS points
            if abs(lat) < 0.001 and abs(lon) < 0.001:
                continue

            trkpt = ET.SubElement(trkseg, "trkpt", {
                "lat": f"{lat:.7f}",
                "lon": f"{lon:.7f}",
            })
            ele = ET.SubElement(trkpt, "ele")
            ele.text = f"{alt:.1f}"

    # Write XML
    tree = ET.ElementTree(gpx)
    ET.indent(tree, space="  ")
    tree.write(str(output_path), xml_declaration=True, encoding="utf-8")

    track_count = len([t for t in telemetry_list if t.has_gps and not t.gps_df.empty])
    logger.info("GPX written to %s (%d tracks, %d waypoints)", output_path, track_count, len(events))
    return output_path

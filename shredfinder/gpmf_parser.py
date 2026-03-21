"""Parse GoPro GPMF binary telemetry format.

GPMF is a KLV (Key-Length-Value) format documented at:
https://github.com/gopro/gpmf-parser/blob/main/docs/README.md

Each entry: 4-byte FourCC key + 1 byte type + 1 byte struct_size + 2 byte repeat_count + payload.
Payloads are 32-bit aligned. Type=0 means the payload contains nested KLV entries.
"""

import struct
from dataclasses import dataclass, field


# GPMF type codes → struct format characters
TYPE_FORMATS = {
    ord("b"): "b",  # int8
    ord("B"): "B",  # uint8
    ord("s"): "h",  # int16
    ord("S"): "H",  # uint16
    ord("l"): "i",  # int32
    ord("L"): "I",  # uint32
    ord("f"): "f",  # float32
    ord("d"): "d",  # float64
    ord("j"): "q",  # int64
    ord("J"): "Q",  # uint64
}


@dataclass
class SensorStream:
    """A single sensor data stream extracted from GPMF."""
    name: str  # e.g. "Accelerometer"
    fourcc: str  # e.g. "ACCL"
    units: str = ""
    scale: list | float = 1.0
    orientation: str = ""
    samples: list[list[float]] = field(default_factory=list)


def parse_gpmf(data: bytes) -> list[SensorStream]:
    """Parse a raw GPMF binary blob and return all sensor streams found.

    Returns a flat list of SensorStream objects across all DEVC blocks (time chunks).
    For a 10-second clip at ~1 chunk/second, you'll get 10 ACCL streams, 10 GPS5 streams, etc.
    """
    streams = []
    _parse_level(data, 0, len(data), streams, context={})
    return streams


def _parse_level(data: bytes, start: int, end: int, streams: list, context: dict):
    """Recursively parse KLV entries at one nesting level."""
    offset = start
    current_stream = None

    while offset + 8 <= end:
        # Read 8-byte KLV header
        fourcc_bytes = data[offset:offset + 4]
        type_code = data[offset + 4]
        struct_size = data[offset + 5]
        repeat = struct.unpack(">H", data[offset + 6:offset + 8])[0]

        payload_size = struct_size * repeat
        padded_size = (payload_size + 3) & ~3

        # Bounds check
        if offset + 8 + padded_size > end:
            break

        payload = data[offset + 8:offset + 8 + payload_size]
        fourcc = fourcc_bytes.decode("ascii", errors="replace")

        if type_code == 0 and payload_size > 0:
            # Nested container
            if fourcc == "DEVC":
                _parse_level(data, offset + 8, offset + 8 + padded_size, streams, context={})
            elif fourcc == "STRM":
                _parse_stream(data, offset + 8, offset + 8 + padded_size, streams)
            else:
                _parse_level(data, offset + 8, offset + 8 + padded_size, streams, context)
        # Non-nested entries at DEVC level are metadata (DVNM, DVID) — skip for now

        offset += 8 + padded_size


def _parse_stream(data: bytes, start: int, end: int, streams: list):
    """Parse a single STRM block and extract sensor data."""
    offset = start
    stream_name = ""
    stream_fourcc = ""
    stream_units = ""
    stream_orientation = ""
    stream_scale: list | float = 1.0
    raw_samples: list[list[float]] = []

    # Sensor data FourCCs we care about
    sensor_keys = {"ACCL", "GYRO", "GPS5", "GPS9", "GRAV", "MAGN"}

    while offset + 8 <= end:
        fourcc_bytes = data[offset:offset + 4]
        type_code = data[offset + 4]
        struct_size = data[offset + 5]
        repeat = struct.unpack(">H", data[offset + 6:offset + 8])[0]

        payload_size = struct_size * repeat
        padded_size = (payload_size + 3) & ~3

        if offset + 8 + padded_size > end:
            break

        payload = data[offset + 8:offset + 8 + payload_size]
        fourcc = fourcc_bytes.decode("ascii", errors="replace")

        if fourcc == "STNM":
            stream_name = payload.split(b"\x00")[0].decode("ascii", errors="replace")
        elif fourcc == "SIUN" or fourcc == "UNIT":
            stream_units = payload.split(b"\x00")[0].decode("ascii", errors="replace")
        elif fourcc == "ORIN":
            stream_orientation = payload.split(b"\x00")[0].decode("ascii", errors="replace")
        elif fourcc == "SCAL":
            stream_scale = _decode_scale(type_code, struct_size, repeat, payload)
        elif fourcc in sensor_keys:
            stream_fourcc = fourcc
            raw_samples = _decode_sensor_data(type_code, struct_size, repeat, payload, stream_scale)

        offset += 8 + padded_size

    if stream_fourcc and raw_samples:
        streams.append(SensorStream(
            name=stream_name,
            fourcc=stream_fourcc,
            units=stream_units,
            scale=stream_scale,
            orientation=stream_orientation,
            samples=raw_samples,
        ))


def _decode_scale(type_code: int, struct_size: int, repeat: int, payload: bytes) -> list | float:
    """Decode a SCAL entry. Returns a single float or list of floats."""
    fmt_char = TYPE_FORMATS.get(type_code)
    if not fmt_char:
        return 1.0

    item_size = struct.calcsize(f">{fmt_char}")
    values_per_sample = struct_size // item_size if item_size > 0 else 1
    total_values = values_per_sample * repeat

    try:
        values = list(struct.unpack(f">{total_values}{fmt_char}", payload[:total_values * item_size]))
    except struct.error:
        return 1.0

    if len(values) == 1:
        return values[0]
    return values


def _decode_sensor_data(
    type_code: int, struct_size: int, repeat: int, payload: bytes, scale: list | float
) -> list[list[float]]:
    """Decode sensor data samples, applying SCAL divisor."""
    fmt_char = TYPE_FORMATS.get(type_code)
    if not fmt_char:
        return []

    item_size = struct.calcsize(f">{fmt_char}")
    values_per_sample = struct_size // item_size if item_size > 0 else 0
    if values_per_sample == 0:
        return []

    samples = []
    for i in range(repeat):
        sample_start = i * struct_size
        sample_end = sample_start + values_per_sample * item_size
        if sample_end > len(payload):
            break

        try:
            raw = struct.unpack(
                f">{values_per_sample}{fmt_char}",
                payload[sample_start:sample_end],
            )
        except struct.error:
            break

        # Apply scale
        if isinstance(scale, list):
            scaled = [float(v) / float(s) if s != 0 else float(v) for v, s in zip(raw, scale)]
        else:
            s = float(scale) if scale != 0 else 1.0
            scaled = [float(v) / s for v in raw]

        samples.append(scaled)

    return samples

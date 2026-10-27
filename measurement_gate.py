"""Conservative evidence gate for DeepSeek photo measurements.

The original parser stays backward compatible for offline regression tests.
Production extraction only accepts photo readings with explicit endpoint evidence.
"""
import json
import re


def filter_supported_readings(readings, raw_reply):
    """Return (accepted, rejected) while preserving the parser's existing data schema."""
    from measure import _json_object

    payload = _json_object(raw_reply)
    entries = payload.get("measurements", []) if isinstance(payload, dict) else []
    if not isinstance(entries, list):
        return [], [{"reason": "invalid_model_response"}]
    by_name = {}
    for entry in entries:
        if isinstance(entry, dict):
            by_name.setdefault(str(entry.get("name", "")).strip().lower(), []).append(entry)
    accepted, rejected = [], []
    for reading in readings:
        name = reading["name"]
        source = reading.get("source", "").lower()
        candidates = by_name.get(name, [])
        # Preserve seller-described numerical measurements; garment size labels
        # are already prohibited by the production prompt.
        if source == "text":
            accepted.append(reading)
            continue
        if not re.fullmatch(r"photo \d+", source):
            rejected.append({"name": name, "reason": "unrecognized_source"})
            continue
        valid = any(
            str(e.get("source", "")).strip().lower() == source
            and e.get("start_visible") is True
            and e.get("end_visible") is True
            and e.get("scale_legible") is True
            and str(e.get("evidence_status", "")).lower() == "verified"
            for e in candidates
        )
        if valid:
            accepted.append(reading)
        else:
            rejected.append({"name": name, "source": source,
                             "reason": "photo_endpoints_or_scale_not_verified"})
    return accepted, rejected

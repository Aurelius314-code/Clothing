"""Production photo-evidence gate tests (offline)."""
import json
from measurement_gate import filter_supported_readings


def entry(**kwargs):
    return {"name": "back_length", "source": "photo 2", **kwargs}


def reading():
    return [{"name": "back_length", "source": "photo 2", "value_cm": 77.5}]


def test_photo_requires_complete_evidence():
    raw = json.dumps({"measurements": [entry(start_visible=True, end_visible=False,
                     scale_legible=True, evidence_status="ambiguous")]})
    accepted, rejected = filter_supported_readings(reading(), raw)
    assert accepted == []
    assert rejected[0]["reason"] == "photo_endpoints_or_scale_not_verified"


def test_verified_photo_accepted():
    raw = json.dumps({"measurements": [entry(start_visible=True, end_visible=True,
                     scale_legible=True, evidence_status="verified")]})
    accepted, rejected = filter_supported_readings(reading(), raw)
    assert len(accepted) == 1 and not rejected


def test_missing_evidence_fields_fail_closed():
    accepted, rejected = filter_supported_readings(reading(), json.dumps({"measurements": [entry()]}))
    assert not accepted and len(rejected) == 1


def test_seller_text_measurement_kept():
    accepted, rejected = filter_supported_readings(
        [{"name": "waist", "source": "text", "value_cm": 48.3}],
        json.dumps({"measurements": [{"name": "waist", "source": "text"}]}))
    assert len(accepted) == 1 and not rejected

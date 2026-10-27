"""Evidence policy tests, independent of the DeepSeek API."""
import pytest

from measurement_evidence import EvidenceLabel, evaluate_evidence


def test_ambiguous_measurement_must_not_be_reported_as_verified():
    result = evaluate_evidence(
        [EvidenceLabel("ambiguous", "back_length", reason="Ruler zero outside frame")],
        [{"name": "back_length", "value_cm": 77.5}],
    )
    assert result["unsupported_numeric_types"] == ["back_length"]


def test_verified_measurement_is_allowed():
    result = evaluate_evidence(
        [EvidenceLabel("verified", "waist", 48.3)],
        [{"name": "waist", "value_cm": 48.3}],
    )
    assert result["verified_predicted_types"] == ["waist"]


def test_unlabelled_case_is_not_a_negative_example():
    result = evaluate_evidence([EvidenceLabel("unlabelled")], [])
    assert result["scorable"] is False


def test_entirely_unmeasurable_photo_flags_invented_measurements():
    result = evaluate_evidence(
        [EvidenceLabel("unmeasurable")],
        [{"name": "pit_to_pit", "value_cm": 61.0}],
    )
    assert result["unsupported_numeric_types"] == ["pit_to_pit"]


def test_cannot_assign_number_to_ambiguous_evidence():
    with pytest.raises(ValueError):
        EvidenceLabel("ambiguous", "back_length", 77.5)

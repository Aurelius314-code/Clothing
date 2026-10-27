"""Offline regression tests for blinded second-pass comparison."""
from photo_verification import assess_agreement


FIRST = {"name": "waist", "value_cm": 44.5}


def test_agreement_is_only_provisional():
    result = assess_agreement(FIRST, {"status": "readable", "value": 17.5, "unit": "in",
        "flat": True, "start_visible": True, "end_visible": True, "scale_legible": True})
    assert result["status"] == "provisional_agreement"


def test_second_pass_disagreement_requires_review():
    result = assess_agreement(FIRST, {"status": "readable", "value": 19, "unit": "in",
        "flat": True, "start_visible": True, "end_visible": True, "scale_legible": True})
    assert result["reason"] == "readings_disagree"


def test_missing_zero_requires_review_even_if_numbers_agree():
    result = assess_agreement(FIRST, {"status": "readable", "value": 17.5, "unit": "in",
        "flat": True, "start_visible": False, "end_visible": True, "scale_legible": True})
    assert result["status"] == "manual_review"


def test_unreadable_photo_requires_review():
    assert assess_agreement(FIRST, {"status": "unreadable"})["status"] == "manual_review"

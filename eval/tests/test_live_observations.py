"""Regression fixtures from observed live runs (no images or API credentials).

These are model outputs, NOT human-verified ground truth. Ensure the gate
does not promote unreadable evidence or numeric agreement to verified.
"""
from photo_verification import assess_agreement


CASES = [
    ("cordings_pit_to_pit", {"name": "pit_to_pit", "value_cm": 53.3},
     {"status": "unreadable", "start_visible": False, "end_visible": False, "scale_legible": True}),
    ("cordings_back_length", {"name": "back_length", "value_cm": 76.2},
     {"status": "unreadable", "start_visible": False, "end_visible": False, "scale_legible": True}),
    ("burberry_waist", {"name": "waist", "value_cm": 43.2},
     {"status": "unreadable", "start_visible": False, "end_visible": False, "scale_legible": True}),
    ("burberry_inseam", {"name": "inseam", "value_cm": 76.8},
     {"status": "unreadable", "start_visible": True, "end_visible": False, "scale_legible": True}),
]


def test_all_observed_unreadable_cases_go_to_review():
    for case_id, first, second in CASES:
        result = assess_agreement(first, second)
        assert result["status"] == "manual_review", case_id


def test_matching_numbers_still_not_human_verified():
    first = {"name": "waist", "value_cm": 45.72}
    second = {"status": "readable", "value": 18, "unit": "in", "flat": True,
              "start_visible": True, "end_visible": True, "scale_legible": True}
    assert assess_agreement(first, second)["status"] == "provisional_agreement"

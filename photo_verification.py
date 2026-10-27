"""Blinded, photo-only second pass. Agreement is NOT independent ground truth.

No listing title, description, garment size, or first-pass numerical value is sent.
This is a diagnostic tool; its outputs must not be marked human-verified.
"""
import json
import re

import requests

import measure


def assess_agreement(first, second, tolerance_cm=1.0):
    """Conservative provisional agreement; never labels a result verified."""
    if not second or second.get("status") != "readable":
        return {"status": "manual_review", "reason": "second_pass_not_readable"}
    if not all(second.get(k) is True for k in ("start_visible", "end_visible", "scale_legible")):
        return {"status": "manual_review", "reason": "second_pass_evidence_incomplete"}
    try:
        value = float(second["value"])
        unit = second["unit"]
        if unit not in ("in", "cm"):
            raise ValueError("unknown unit")
        cm = value * 2.54 if unit == "in" else value
        if first["name"] in measure.WIDTHS and second.get("flat") is False:
            cm /= 2
        if not 0 < cm < 200:
            raise ValueError("out of range")
    except (ValueError, TypeError, KeyError):
        return {"status": "manual_review", "reason": "invalid_second_pass_value"}
    delta = round(abs(cm - first["value_cm"]), 2)
    if delta > tolerance_cm:
        return {"status": "manual_review", "reason": "readings_disagree", "difference_cm": delta}
    return {"status": "provisional_agreement", "difference_cm": delta,
            "warning": "Two model calls agreeing does not establish measurement accuracy"}


def verify_photo_blind(url, garment_type, measurement_name, key, model=None):
    """Read ONE photograph in a separate API call, blinded to original prediction."""
    if garment_type not in measure.MEASUREMENTS or measurement_name not in measure.MEASUREMENTS[garment_type]:
        raise ValueError("invalid measurement type")
    prompt = (
        "Examine this garment photograph alone. There is no seller text or prior measurement. "
        f"Target measurement: {measurement_name}. Method: {measure.MEASUREMENTS[garment_type][measurement_name]}. "
        "Do not infer a number from clothing size. Do not guess hidden endpoints. "
        "A visible printed ruler number is not enough: identify the zero/start and actual garment endpoint. "
        "If either endpoint is obscured, the ruler is ambiguous, or the scale is illegible, status must be 'unreadable'. "
        "Reply JSON only: "
        '{"status":"readable|unreadable","value":null,"unit":null,"flat":true,'
        '"start_visible":false,"end_visible":false,"scale_legible":false,"reason":""}. '
        "For readable only, give numeric value and unit in or cm, with all three visibility flags true. "
        "Do not include any other measurements."
    )
    data_url = measure._download(url)
    try:
        response = requests.post(
            measure.DEEPSEEK_URL,
            headers={"Authorization": f"Bearer {key}"},
            timeout=180,
            json={"model": model or measure.model_name(),
                  "messages": [{"role": "user", "content": [
                      {"type": "text", "text": prompt},
                      {"type": "image_url", "image_url": {"url": data_url}}
                  ]}],
                  "thinking": {"type": "disabled"}, "max_tokens": 450},
        )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
    except (requests.RequestException, ValueError, KeyError, IndexError, TypeError) as exc:
        raise measure.AnalysisError(f"Blinded verification failed: {type(exc).__name__}") from exc
    return measure._json_object(content)


def inspect_case(case, key):
    """One full-listing extraction, then one blind call per photo-derived reading."""
    accepted, raw = measure.read_measurements(
        case["photos"], case["garment_type"], case["title"], case["description"], key
    )
    payload = measure._json_object(raw)
    checks = []
    for reading in accepted:
        match = re.fullmatch(r"photo (\d+)", reading.get("source", ""))
        if not match:
            checks.append({"measurement": reading, "status": "seller_text_not_independently_checked"})
            continue
        index = int(match.group(1)) - 1
        if not 0 <= index < len(case["photos"]):
            checks.append({"measurement": reading, "status": "manual_review", "reason": "invalid_photo_number"})
            continue
        try:
            second = verify_photo_blind(case["photos"][index], case["garment_type"], reading["name"], key)
            assessment = assess_agreement(reading, second)
        except Exception as exc:
            second = {"error": f"{type(exc).__name__}: {exc}"}
            assessment = {"status": "manual_review", "reason": "verification_call_failed"}
        checks.append({"measurement": reading, "blind_second_pass": second, **assessment})
    return {"case_id": case["case_id"], "checks": checks,
            "initial_rejections": payload.get("rejected_photo_measurements", []),
            "ground_truth_status": "UNLABELLED; provisional agreement is NOT accuracy"}

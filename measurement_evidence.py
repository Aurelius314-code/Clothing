"""Evidence-aware benchmark labels, separate from exact numeric accuracy.

Do not interpret unknown/unlabelled cases as negative examples.
"""
from dataclasses import dataclass

VALID_STATES = {"verified", "ambiguous", "unmeasurable", "unlabelled"}


@dataclass(frozen=True)
class EvidenceLabel:
    state: str
    name: str | None = None
    value_cm: float | None = None
    reason: str = ""

    def __post_init__(self):
        if self.state not in VALID_STATES:
            raise ValueError(f"Invalid evidence state: {self.state}")
        if self.state == "verified" and (not self.name or self.value_cm is None):
            raise ValueError("Verified measurements require a type and a numeric value")
        if self.state != "verified" and self.value_cm is not None:
            raise ValueError("Only verified measurements may have a ground-truth number")


def evaluate_evidence(labels, predictions):
    """Report unsupported numerical predictions; never score unlabelled as absent.

    Labels are per measurement type. An unmeasurable label can use name=None
    to denote an entirely negative case.
    """
    labels = list(labels)
    predictions = list(predictions)
    if not labels or any(label.state == "unlabelled" for label in labels):
        return {"scorable": False, "reason": "Unlabelled evidence; manual review required"}
    by_name = {label.name: label for label in labels if label.name}
    whole_negative = any(label.state == "unmeasurable" and label.name is None for label in labels)
    unsupported = []
    verified = []
    for prediction in predictions:
        name = prediction["name"]
        label = by_name.get(name)
        if whole_negative or (label is not None and label.state in {"ambiguous", "unmeasurable"}):
            unsupported.append(name)
        elif label is not None and label.state == "verified":
            verified.append(name)
    return {
        "scorable": True,
        "unsupported_numeric_types": sorted(set(unsupported)),
        "verified_predicted_types": sorted(set(verified)),
        "unreviewed_predicted_types": sorted({p["name"] for p in predictions}
                                           - set(unsupported) - set(verified)),
    }

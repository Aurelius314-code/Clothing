"""Offline DeepEval regression tests: no credentials, API calls or database writes."""
import pytest
from deepeval import assert_test
from deepeval.metrics import BaseMetric
from deepeval.test_case import LLMTestCase

import measure
from measurement_benchmark import score


class GarmentMeasurementMetric(BaseMetric):
    """Deterministic evaluator for normalized production measurement JSON."""
    def __init__(self, threshold=1.0):
        self.threshold = threshold
        self.score = 0.0
        self.success = False

    def measure(self, test_case):
        expected = __import__("json").loads(test_case.expected_output)
        actual = __import__("json").loads(test_case.actual_output)
        report = score(expected, actual)
        self.score = float(report["all_correct"])
        self.success = self.score >= self.threshold
        self.reason = str(report)
        return self.score

    async def a_measure(self, test_case):
        return self.measure(test_case)

    def is_successful(self):
        return self.success

    @property
    def __name__(self):
        return "Garment measurement exact-type + 1cm tolerance"


@pytest.mark.parametrize("kind,raw,expected", [
    ("jacket", '{"measurements":[{"name":"pit_to_pit","value":22,"unit":"in","flat":true,"source":"photo 2","confidence":"high"}]}',
     [{"name": "pit_to_pit", "value_cm": 55.9}]),
    ("trousers", '{"measurements":[{"name":"waist","value":40,"unit":"in","flat":false,"source":"text","confidence":"medium"}]}',
     [{"name": "waist", "value_cm": 50.8}]),
    ("knitwear", '{"measurements":[]}', []),
])
def test_production_parser(kind, raw, expected):
    import json
    readings = measure.parse_readings(raw, kind)
    case = LLMTestCase(input=f"Parse {kind} measurements", actual_output=json.dumps(readings),
                       expected_output=json.dumps(expected))
    assert_test(case, [GarmentMeasurementMetric()])


def test_incorrect_type_fails():
    report = score([{"name": "pit_to_pit", "value_cm": 55.9}],
                   [{"name": "sleeve", "value_cm": 55.9}])
    assert not report["all_correct"]
    assert report["missing_types"] == ["pit_to_pit"]
    assert report["extra_types"] == ["sleeve"]


def test_missing_and_extra_measurements_fail():
    assert not score([], [{"name": "waist", "value_cm": 50}])["all_correct"]
    assert not score([{"name": "waist", "value_cm": 50}], [])["all_correct"]

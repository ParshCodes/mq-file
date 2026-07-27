from pathlib import Path
import pytest

from mq_harness.validation import OrderValidationError, OrderValidator

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def validator():
    return OrderValidator(ROOT / "schemas")


def test_valid_xml_and_json_are_normalized(validator):
    assert validator.parse(ROOT / "sample_data/valid_order.xml")["order_id"] == "ORD-XML-001"
    assert validator.parse(ROOT / "sample_data/valid_order.json")["order_id"] == "ORD-JSON-001"


@pytest.mark.parametrize("name, expected", [
    ("invalid_malformed.json", "malformed JSON"),
    ("invalid_schema.xml", "XSD line"),
    ("invalid_total.json", "business validation"),
])
def test_invalid_samples_have_diagnostic_errors(validator, name, expected):
    with pytest.raises(OrderValidationError, match=expected):
        validator.parse(ROOT / "sample_data" / name)


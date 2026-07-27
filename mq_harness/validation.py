import json
from decimal import Decimal
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker
from lxml import etree


class OrderValidationError(ValueError):
    pass


class OrderValidator:
    def __init__(self, schema_dir: Path):
        with (schema_dir / "order.schema.json").open(encoding="utf-8") as stream:
            self.json_validator = Draft202012Validator(
                json.load(stream), format_checker=FormatChecker()
            )
        xsd_doc = etree.parse(str(schema_dir / "order.xsd"))
        self.xml_validator = etree.XMLSchema(xsd_doc)

    def parse(self, path: Path) -> dict[str, Any]:
        suffix = path.suffix.lower()
        if suffix == ".json":
            return self._json(path)
        if suffix == ".xml":
            return self._xml(path)
        raise OrderValidationError(f"unsupported file extension: {suffix or '<none>'}")

    def _json(self, path: Path) -> dict[str, Any]:
        try:
            with path.open(encoding="utf-8") as stream:
                order = json.load(stream, parse_float=Decimal)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise OrderValidationError(f"malformed JSON: {exc}") from exc
        errors = sorted(self.json_validator.iter_errors(order), key=lambda e: list(e.path))
        if errors:
            error = errors[0]
            location = ".".join(str(p) for p in error.absolute_path) or "$"
            raise OrderValidationError(f"JSON Schema at {location}: {error.message}")
        self._check_total(order)
        return order

    def _xml(self, path: Path) -> dict[str, Any]:
        parser = etree.XMLParser(resolve_entities=False, no_network=True, recover=False)
        try:
            document = etree.parse(str(path), parser)
        except (etree.XMLSyntaxError, OSError) as exc:
            raise OrderValidationError(f"malformed XML: {exc}") from exc
        if not self.xml_validator.validate(document):
            error = self.xml_validator.error_log.last_error
            raise OrderValidationError(f"XSD line {error.line}: {error.message}")
        root = document.getroot()
        order = {
            "order_id": root.findtext("order_id"),
            "customer": {key: root.findtext(f"customer/{key}") for key in ("id", "name", "email")},
            "items": [
                {
                    "sku": item.findtext("sku"),
                    "quantity": int(item.findtext("quantity")),
                    "unit_price": Decimal(item.findtext("unit_price")),
                }
                for item in root.findall("items/item")
            ],
            "total": Decimal(root.findtext("total")),
            "timestamp": root.findtext("timestamp"),
        }
        if root.find("force_failure") is not None:
            order["force_failure"] = root.findtext("force_failure").lower() in ("true", "1")
        self._check_total(order)
        return order

    @staticmethod
    def _check_total(order: dict[str, Any]) -> None:
        declared = Decimal(str(order["total"]))
        calculated = sum(
            Decimal(str(item["unit_price"])) * item["quantity"] for item in order["items"]
        )
        if declared != calculated:
            raise OrderValidationError(
                f"business validation: declared total {declared:.2f} does not equal item total {calculated:.2f}"
            )


class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        return super().default(obj)


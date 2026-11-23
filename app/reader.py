"""
Turns a bill document into named fields, each with a confidence and a source line.
Two readers sit behind one interface: a recorded one that replays saved model output,
and a live one used only when a model key is set.
Leaves out: OCR, so a photograph of a bill would need a vision model in front of this.
"""

import json

from app import config
from app.seed import SAMPLE_NAMES

FIELD_NAMES = (
    "business_name",
    "supply_address",
    "postcode",
    "supplier_name",
    "account_number",
    "mpan",
    "period_start",
    "period_end",
    "kwh",
    "unit_rate_p",
    "standing_charge_p",
    "energy_charge",
    "standing_charge_total",
    "climate_change_levy",
    "subtotal",
    "vat",
    "total",
    "contract_end_date",
)

PROMPT_VERSION = "bill-fields-v1"


class ReaderUnavailable(Exception):
    """The reader cannot handle this document at all, so retrying will not help."""


class InvalidExtraction(Exception):
    """The reader answered, but not in the shape the rest of the app relies on."""


def validate(raw) -> dict:
    """
    Check the reader's answer before any of it reaches the database.
    A model that returns the wrong shape should fail here and nowhere later.
    """
    if not isinstance(raw, dict):
        raise InvalidExtraction("The reader returned something that is not an object.")

    fields = raw.get("fields")
    if not isinstance(fields, dict):
        raise InvalidExtraction("The reader returned no fields object.")

    missing = [name for name in FIELD_NAMES if name not in fields]
    if missing:
        raise InvalidExtraction("The reader left out: " + ", ".join(missing))

    for name in FIELD_NAMES:
        field = fields[name]
        if not isinstance(field, dict):
            raise InvalidExtraction(f"The field {name} is not an object.")
        if not isinstance(field.get("value"), str) or not field["value"].strip():
            raise InvalidExtraction(f"The field {name} has no value.")
        confidence = field.get("confidence")
        if not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
            raise InvalidExtraction(f"The field {name} has a confidence of {confidence!r}.")
        if not isinstance(field.get("line"), str) or not field["line"].strip():
            raise InvalidExtraction(f"The field {name} does not say which line it came from.")

    return raw


def read_recorded(bill) -> dict:
    """Replay the model output saved for one of the sample bills."""
    sample = bill["sample_name"]
    if sample not in SAMPLE_NAMES:
        raise ReaderUnavailable(
            "Demo mode reads the sample bills only. Set a model key to read other files."
        )
    path = config.FIXTURES_DIR / "extractions" / f"{sample}.json"
    if not path.exists():
        raise ReaderUnavailable(f"There is no recorded reading for {sample}.")
    return json.loads(path.read_text())


def read_once(bill, document_text: str | None = None) -> dict:
    if config.READER == "model":
        from app import model_reader

        return model_reader.read(bill, document_text or "")
    return read_recorded(bill)


def read(bill, document_text: str | None = None) -> dict:
    """
    Read the bill, and if the answer does not fit the schema try once more.
    A second attempt is worth it for a live model and costs nothing for a recorded one.
    """
    last_error = None
    for _ in range(2):
        try:
            return validate(read_once(bill, document_text))
        except InvalidExtraction as error:
            last_error = error
    raise last_error

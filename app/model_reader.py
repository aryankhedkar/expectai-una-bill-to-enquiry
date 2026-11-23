"""
The live reader, used only when READER=model and a key is set.
It is kept apart from the recorded reader so the default path makes no network
call and the demo cannot depend on a model being up.
Leaves out: retries on rate limits, and any cost tracking.
"""

import json
import re
import urllib.request

from app import config, reader

ENDPOINT = "https://api.anthropic.com/v1/messages"

PROMPT = """You are reading a UK business electricity bill.

Return JSON only, with no explanation and no code fence, in this shape:

{{"fields": {{"<field name>": {{"value": "<string>", "confidence": <0 to 1>, "line": "<line id>"}}}}}}

Rules:
- Return every one of these fields: {fields}
- Dates are ISO, as 2026-10-31. Money is a plain number with no currency symbol.
- kwh, unit_rate_p and standing_charge_p are plain numbers.
- "line" is the data-line attribute of the element you read the value from.
- confidence is how sure you are of the characters you read, not how sensible the
  value seems. Say so when the print is faint or ambiguous.

The bill:

{document}
"""


def extract_json(text: str) -> dict:
    """Models sometimes wrap JSON in prose or a fence. Take the outermost object."""
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise reader.InvalidExtraction("The model did not return any JSON.")
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError as error:
        raise reader.InvalidExtraction(f"The model's JSON would not parse: {error}") from error


def read(bill, document_text: str) -> dict:
    if not config.MODEL_API_KEY:
        raise reader.ReaderUnavailable(
            "READER is set to model but no ANTHROPIC_API_KEY is set."
        )
    if not document_text:
        path = config.SAMPLES_DIR / f"{bill['sample_name']}.html"
        document_text = path.read_text() if bill["sample_name"] and path.exists() else ""
    if not document_text:
        document_text = open(bill["stored_path"], encoding="utf-8", errors="replace").read()

    body = json.dumps(
        {
            "model": config.MODEL_NAME,
            "max_tokens": 2000,
            "messages": [
                {
                    "role": "user",
                    "content": PROMPT.format(
                        fields=", ".join(reader.FIELD_NAMES), document=document_text
                    ),
                }
            ],
        }
    ).encode()

    request = urllib.request.Request(
        ENDPOINT,
        data=body,
        headers={
            "content-type": "application/json",
            "anthropic-version": "2023-06-01",
            "x-api-key": config.MODEL_API_KEY,
        },
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        answer = json.loads(response.read())

    text = "".join(part.get("text", "") for part in answer.get("content", []))
    raw = extract_json(text)
    raw["reader"] = "model"
    raw["model"] = config.MODEL_NAME
    raw["prompt_version"] = reader.PROMPT_VERSION
    for field in raw.get("fields", {}).values():
        if isinstance(field, dict):
            field.setdefault("line_text", "")
    return raw

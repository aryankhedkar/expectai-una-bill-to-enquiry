"""
Every rule that tests what the reader produced, in plain Python with no model call.
These are pure functions: the same values always give the same answer, and each one
can be read on its own and argued with.
Leaves out: rules that need outside data, such as whether a rate is competitive.
"""

import math
from dataclasses import dataclass
from datetime import date

from app import config

# The weights for the meter number's check digit. Eleven is left out on purpose:
# the rule uses the primes from 3 to 43 and skips it.
MPAN_WEIGHTS = (3, 5, 7, 13, 17, 19, 23, 29, 31, 37, 41, 43)

REQUIRED_FIELDS = (
    "business_name",
    "supply_address",
    "postcode",
    "supplier_name",
    "mpan",
    "period_start",
    "period_end",
    "kwh",
    "unit_rate_p",
    "standing_charge_p",
    "total",
    "contract_end_date",
)

FIELD_LABELS = {
    "business_name": "Business name",
    "supply_address": "Supply address",
    "postcode": "Postcode",
    "supplier_name": "Supplier",
    "account_number": "Account number",
    "mpan": "Meter number (MPAN)",
    "period_start": "Billing period start",
    "period_end": "Billing period end",
    "kwh": "Electricity used (kWh)",
    "unit_rate_p": "Unit rate (p per kWh)",
    "standing_charge_p": "Standing charge (p per day)",
    "energy_charge": "Energy charge",
    "standing_charge_total": "Standing charge total",
    "climate_change_levy": "Climate change levy",
    "subtotal": "Subtotal",
    "vat": "VAT",
    "total": "Total",
    "contract_end_date": "Contract end date",
}

MONEY_FIELDS = {
    "energy_charge",
    "standing_charge_total",
    "climate_change_levy",
    "subtotal",
    "vat",
    "total",
}
DATE_FIELDS = {"period_start", "period_end", "contract_end_date"}
NUMBER_FIELDS = MONEY_FIELDS | {"kwh", "unit_rate_p", "standing_charge_p"}


@dataclass(frozen=True)
class CheckResult:
    name: str
    title: str
    passed: bool
    message: str
    fields: tuple[str, ...]


def label(field: str) -> str:
    return FIELD_LABELS.get(field, field.replace("_", " ").capitalize())


def number(text) -> float | None:
    """Read a figure that may carry a pound sign, commas or a p for pence."""
    if text is None:
        return None
    cleaned = str(text).replace("£", "").replace(",", "").replace("p", "").strip()
    try:
        return float(cleaned)
    except ValueError:
        return None


def problem_with(field: str, value: str) -> str | None:
    """Why a value the owner typed cannot be used, or None if it can."""
    if field in NUMBER_FIELDS:
        figure = number(value)
        if figure is None or not math.isfinite(figure) or figure < 0:
            return f"{label(field)} needs to be a number, such as 412.80."
    if field in DATE_FIELDS and parse_date(value) is None:
        return f"{label(field)} needs to be a date, written as 2027-03-31."
    return None


def parse_date(text) -> date | None:
    if text is None:
        return None
    try:
        return date.fromisoformat(str(text).strip())
    except ValueError:
        return None


def pretty_date(text) -> str:
    parsed = parse_date(text)
    if parsed is None:
        return str(text)
    return parsed.strftime("%d %B %Y").lstrip("0")


def pretty_money(value) -> str:
    amount = number(value)
    if amount is None:
        return str(value)
    return f"£{amount:,.2f}"


def mpan_check_digit(core_twelve: str) -> int:
    """Multiply each of the first twelve digits by its weight, then take the
    remainder after dividing by 11, then the remainder of that after 10."""
    total = sum(int(d) * w for d, w in zip(core_twelve, MPAN_WEIGHTS))
    return total % 11 % 10


def mpan_is_valid(mpan: str) -> bool:
    mpan = (mpan or "").replace(" ", "")
    if len(mpan) != 13 or not mpan.isdigit():
        return False
    return mpan_check_digit(mpan[:12]) == int(mpan[12])


def _agree(left: float, right: float) -> bool:
    return abs(left - right) <= config.MONEY_TOLERANCE


def _missing(name: str, title: str, fields: tuple[str, ...]) -> CheckResult:
    names = " and ".join(label(f) for f in fields)
    return CheckResult(name, title, False, f"We could not read {names} from this bill.", fields)


def check_mpan(values) -> CheckResult:
    name, title, fields = "mpan_check_digit", "Meter number", ("mpan",)
    mpan = (values.get("mpan") or "").replace(" ", "")
    if not mpan:
        return _missing(name, title, fields)
    if len(mpan) != 13 or not mpan.isdigit():
        return CheckResult(
            name, title, False,
            f"A meter number has 13 digits. We read {mpan}, which has {len(mpan)}.",
            fields,
        )
    if not mpan_is_valid(mpan):
        expected = mpan_check_digit(mpan[:12])
        return CheckResult(
            name, title, False,
            f"The meter number {mpan} fails its check digit. The last digit should be "
            f"{expected} for the first twelve digits we read, so one digit is wrong.",
            fields,
        )
    return CheckResult(name, title, True, f"{mpan} passes its check digit.", fields)


def check_billing_period(values, today: date) -> CheckResult:
    name, title = "billing_period", "Billing period"
    fields = ("period_start", "period_end")
    start, end = parse_date(values.get("period_start")), parse_date(values.get("period_end"))
    if start is None or end is None:
        return _missing(name, title, fields)
    if start > end:
        return CheckResult(name, title, False, "The billing period starts after it ends.", fields)
    if end > today:
        return CheckResult(
            name, title, False,
            f"The billing period ends on {pretty_date(end)}, which is in the future.",
            fields,
        )
    days = (end - start).days + 1
    if not 1 <= days <= 366:
        return CheckResult(name, title, False, f"The billing period covers {days} days.", fields)
    return CheckResult(name, title, True, f"{days} days, ending {pretty_date(end)}.", fields)


def check_energy_charge(values) -> CheckResult:
    name, title = "energy_charge_arithmetic", "Energy charge"
    fields = ("kwh", "unit_rate_p", "energy_charge")
    kwh, rate, charge = (number(values.get(f)) for f in fields)
    if None in (kwh, rate, charge):
        return _missing(name, title, fields)
    expected = kwh * rate / 100
    if not _agree(expected, charge):
        return CheckResult(
            name, title, False,
            f"{kwh:,.0f} kWh at {rate:.2f}p comes to {pretty_money(expected)}, "
            f"but the bill charges {pretty_money(charge)}.",
            fields,
        )
    return CheckResult(
        name, title, True,
        f"{kwh:,.0f} kWh at {rate:.2f}p comes to {pretty_money(charge)}.", fields,
    )


def check_standing_charge(values) -> CheckResult:
    name, title = "standing_charge_arithmetic", "Standing charge"
    fields = ("period_start", "period_end", "standing_charge_p", "standing_charge_total")
    start, end = parse_date(values.get("period_start")), parse_date(values.get("period_end"))
    rate, total = number(values.get("standing_charge_p")), number(values.get("standing_charge_total"))
    if None in (start, end, rate, total) or start > end:
        return _missing(name, title, fields)
    days = (end - start).days + 1
    expected = days * rate / 100
    if not _agree(expected, total):
        return CheckResult(
            name, title, False,
            f"{days} days at {rate:.2f}p comes to {pretty_money(expected)}, "
            f"but the bill charges {pretty_money(total)}.",
            fields,
        )
    return CheckResult(
        name, title, True, f"{days} days at {rate:.2f}p comes to {pretty_money(total)}.", fields
    )


def check_subtotal(values) -> CheckResult:
    name, title = "subtotal_arithmetic", "Subtotal"
    fields = ("energy_charge", "standing_charge_total", "climate_change_levy", "subtotal")
    energy, standing, levy, subtotal = (number(values.get(f)) for f in fields)
    if None in (energy, standing, levy, subtotal):
        return _missing(name, title, fields)
    expected = energy + standing + levy
    if not _agree(expected, subtotal):
        return CheckResult(
            name, title, False,
            f"The charges add up to {pretty_money(expected)}, "
            f"but the subtotal says {pretty_money(subtotal)}.",
            fields,
        )
    return CheckResult(name, title, True, f"The charges add up to {pretty_money(subtotal)}.", fields)


def check_total(values) -> CheckResult:
    name, title, fields = "total_arithmetic", "Total", ("subtotal", "vat", "total")
    subtotal, vat, total = (number(values.get(f)) for f in fields)
    if None in (subtotal, vat, total):
        return _missing(name, title, fields)
    expected = subtotal + vat
    if not _agree(expected, total):
        return CheckResult(
            name, title, False,
            f"The subtotal and VAT add up to {pretty_money(expected)}, "
            f"but the total says {pretty_money(total)}.",
            fields,
        )
    return CheckResult(name, title, True, f"The bill totals {pretty_money(total)}.", fields)


def check_vat_rate(values) -> CheckResult:
    name, title, fields = "vat_rate", "VAT rate", ("subtotal", "vat")
    subtotal, vat = number(values.get("subtotal")), number(values.get("vat"))
    if None in (subtotal, vat):
        return _missing(name, title, fields)
    for rate in (0.20, 0.05):
        if _agree(subtotal * rate, vat):
            return CheckResult(name, title, True, f"VAT is charged at {rate:.0%}.", fields)
    share = vat / subtotal if subtotal else 0
    return CheckResult(
        name, title, False,
        f"VAT of {pretty_money(vat)} is {share:.1%} of the subtotal, which is neither 20% nor 5%.",
        fields,
    )


def check_contract_end(values, today: date) -> CheckResult:
    name, title, fields = "contract_end_date", "Contract end date", ("contract_end_date",)
    end = parse_date(values.get("contract_end_date"))
    if end is None:
        return _missing(name, title, fields)
    if end <= today:
        return CheckResult(
            name, title, False,
            f"The contract ended on {pretty_date(end)}, so this supply may already be "
            "on out of contract rates.",
            fields,
        )
    return CheckResult(
        name, title, True, f"The contract runs until {pretty_date(end)}, {(end - today).days} days away.", fields
    )


def check_confidence(field: str, confidence: float, value) -> CheckResult:
    name = f"confidence:{field}"
    title = f"Confidence in {label(field).lower()}"
    shown = pretty_date(value) if field in DATE_FIELDS else value
    if confidence >= config.CONFIDENCE_THRESHOLD:
        return CheckResult(name, title, True, f"Read with {confidence:.0%} confidence.", (field,))
    return CheckResult(
        name, title, False,
        f"We read {label(field).lower()} as {shown} but are only {confidence:.0%} sure of it.",
        (field,),
    )


def run_all(values: dict, confidences: dict, today: date | None = None) -> list[CheckResult]:
    """Every check, in the order the bill page shows them."""
    today = today or config.TODAY
    results = [
        check_mpan(values),
        check_billing_period(values, today),
        check_energy_charge(values),
        check_standing_charge(values),
        check_subtotal(values),
        check_total(values),
        check_vat_rate(values),
        check_contract_end(values, today),
    ]
    for field in REQUIRED_FIELDS:
        results.append(check_confidence(field, confidences.get(field, 0.0), values.get(field)))
    return results

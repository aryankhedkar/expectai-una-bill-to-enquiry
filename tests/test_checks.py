"""Each check, with a case that passes and a case that fails."""

from datetime import date

from app import checks

TODAY = date(2026, 11, 23)

GOOD = {
    "business_name": "Harbour Lane Bakery Ltd",
    "supply_address": "14 Harbour Lane, Bristol",
    "postcode": "BS1 4QT",
    "supplier_name": "Northwind Energy",
    "mpan": "1200012345679",
    "period_start": "2026-10-01",
    "period_end": "2026-10-31",
    "kwh": "4820",
    "unit_rate_p": "28.40",
    "standing_charge_p": "60.00",
    "energy_charge": "1368.88",
    "standing_charge_total": "18.60",
    "climate_change_levy": "37.35",
    "subtotal": "1424.83",
    "vat": "284.97",
    "total": "1709.80",
    "contract_end_date": "2027-03-31",
}

CONFIDENT = {field: 0.97 for field in checks.REQUIRED_FIELDS}


def test_a_valid_meter_number_passes():
    assert checks.mpan_is_valid("1200012345679")
    assert checks.check_mpan(GOOD).passed


def test_one_wrong_digit_fails_the_check_digit():
    assert not checks.mpan_is_valid("1200012845679")
    result = checks.check_mpan({"mpan": "1200012845679"})
    assert not result.passed
    assert "check digit" in result.message


def test_a_meter_number_of_the_wrong_length_fails():
    assert not checks.check_mpan({"mpan": "12000123456"}).passed
    assert not checks.check_mpan({"mpan": ""}).passed


def test_billing_period():
    assert checks.check_billing_period(GOOD, TODAY).passed
    backwards = GOOD | {"period_start": "2026-10-31", "period_end": "2026-10-01"}
    assert not checks.check_billing_period(backwards, TODAY).passed
    future = GOOD | {"period_start": "2026-12-01", "period_end": "2026-12-31"}
    assert not checks.check_billing_period(future, TODAY).passed


def test_energy_charge_arithmetic():
    assert checks.check_energy_charge(GOOD).passed
    assert not checks.check_energy_charge(GOOD | {"energy_charge": "1400.00"}).passed


def test_standing_charge_arithmetic():
    assert checks.check_standing_charge(GOOD).passed
    assert not checks.check_standing_charge(GOOD | {"standing_charge_total": "25.00"}).passed


def test_subtotal_arithmetic():
    assert checks.check_subtotal(GOOD).passed
    assert not checks.check_subtotal(GOOD | {"subtotal": "1500.00"}).passed


def test_total_arithmetic_catches_two_transposed_digits():
    assert checks.check_total(GOOD).passed
    swapped = GOOD | {"total": "1790.80"}
    result = checks.check_total(swapped)
    assert not result.passed
    assert "£1,709.80" in result.message


def test_five_pence_is_within_tolerance_and_ten_is_not():
    assert checks.check_total(GOOD | {"total": "1709.85"}).passed
    assert not checks.check_total(GOOD | {"total": "1709.90"}).passed


def test_vat_rate_accepts_twenty_and_five_percent():
    assert checks.check_vat_rate(GOOD).passed
    reduced = {"subtotal": "1000.00", "vat": "50.00"}
    assert checks.check_vat_rate(reduced).passed
    assert not checks.check_vat_rate({"subtotal": "1000.00", "vat": "120.00"}).passed


def test_contract_end_date_must_be_in_the_future():
    assert checks.check_contract_end(GOOD, TODAY).passed
    assert not checks.check_contract_end({"contract_end_date": "2026-01-31"}, TODAY).passed
    assert not checks.check_contract_end({}, TODAY).passed


def test_low_confidence_fails_and_high_confidence_passes():
    assert checks.check_confidence("contract_end_date", 0.97, "2027-03-31").passed
    low = checks.check_confidence("contract_end_date", 0.55, "2027-03-31")
    assert not low.passed
    assert "31 March 2027" in low.message


def test_a_clean_bill_passes_every_check():
    results = checks.run_all(GOOD, CONFIDENT, TODAY)
    assert [r.name for r in results if not r.passed] == []


def test_an_unreadable_figure_fails_rather_than_crashing():
    results = checks.run_all(GOOD | {"total": "not a number"}, CONFIDENT, TODAY)
    failed = [r.name for r in results if not r.passed]
    assert "total_arithmetic" in failed

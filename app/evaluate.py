"""
Measures the reader against the known right answers, one field at a time.
An overall score hides the field that always fails, and the field that always
fails is the one that costs a customer their trust.
Leaves out: a real evaluation set. Four bills is a shape to fill, not a measurement.
"""

import json

from app import checks, config, reader


def load(folder: str, name: str) -> dict:
    return json.loads((config.FIXTURES_DIR / folder / f"{name}.json").read_text())


def sample_names() -> list[str]:
    return sorted(p.stem for p in (config.FIXTURES_DIR / "expected").glob("*.json"))


def compare(name: str) -> dict:
    """What the reader said against what the bill actually says."""
    expected = load("expected", name)
    got = {k: v["value"] for k, v in load("extractions", name)["fields"].items()}
    return {field: (got.get(field) == value, got.get(field), value) for field, value in expected.items()}


def caught_by(name: str) -> list[str]:
    """Which checks notice the planted error on this bill."""
    extraction = load("extractions", name)["fields"]
    values = {k: v["value"] for k, v in extraction.items()}
    confidences = {k: v["confidence"] for k, v in extraction.items()}
    results = checks.run_all(values, confidences, config.TODAY)
    return [r.name for r in results if not r.passed]


def main() -> None:
    names = sample_names()
    fields = list(reader.FIELD_NAMES)
    rows = {name: compare(name) for name in names}

    width = max(len(f) for f in fields) + 2
    print(f"Reader: {config.READER}")
    print(f"Bills:  {', '.join(names)}\n")
    print("Field".ljust(width) + "  " + "  ".join(n[:14].rjust(14) for n in names) + "   Correct")
    print("-" * (width + 2 + 16 * len(names) + 10))

    correct_total = 0
    for field in fields:
        marks = []
        right = 0
        for name in names:
            ok = rows[name].get(field, (False,))[0]
            right += 1 if ok else 0
            marks.append(("ok" if ok else "WRONG").rjust(14))
        correct_total += right
        print(field.ljust(width) + "  " + "  ".join(marks) + f"   {right}/{len(names)}")

    total = len(fields) * len(names)
    print(f"\nFields correct: {correct_total} of {total} ({correct_total / total:.1%})")

    print("\nWhat each bill plants, and what notices it")
    for name in names:
        wrong = [field for field, (ok, _, _) in rows[name].items() if not ok]
        failures = caught_by(name)
        print(f"\n  {name}")

        if wrong:
            for field in wrong:
                _, got, want = rows[name][field]
                print(f"    reader: {field} read as {got}, the bill says {want}")
        else:
            print("    reader: every field read correctly")

        if failures:
            for failure in failures:
                print(f"    checks: {failure} fails")
        else:
            print("    checks: all pass")

        if wrong and not failures:
            print("    nothing catches it, which is the case to worry about")


if __name__ == "__main__":
    main()

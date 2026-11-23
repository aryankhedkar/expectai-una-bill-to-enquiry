"""
Creates the data folders and the database tables.
Run before the app starts so a fresh clone works with one command.
On a hosted instance it also opens the four sample bills, because that instance
starts with an empty disk and an empty app would be a dead end for a visitor.
"""

from app import config, db

SAMPLE_NAMES = ("clean", "total_mismatch", "faint_contract_date", "misread_mpan")


def open_samples(conn) -> int:
    """Put the four samples in front of a visitor on a fresh instance."""
    from app import bills

    opened = 0
    for name in SAMPLE_NAMES:
        path = config.SAMPLES_DIR / f"{name}.html"
        if not path.exists():
            continue
        _, created = bills.create_from_sample(conn, name)
        opened += 1 if created else 0
    return opened


def main() -> None:
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    config.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    conn = db.connect()
    db.setup(conn)
    if config.DEMO_SEED:
        open_samples(conn)
    conn.close()
    print(f"Database ready at {config.DB_PATH}")


if __name__ == "__main__":
    main()

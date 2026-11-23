"""
Creates the data folders and the database tables.
Run before the app starts so a fresh clone works with one command.
Leaves out: loading any bills, because the home page offers the samples.
"""

from app import config, db


def main() -> None:
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    config.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    conn = db.connect()
    db.setup(conn)
    conn.close()
    print(f"Database ready at {config.DB_PATH}")


if __name__ == "__main__":
    main()

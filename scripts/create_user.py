"""Create a doctor/staff login. Run: .venv/bin/python scripts/create_user.py <username> <doctor|staff>
Password is prompted (not echoed, not stored anywhere but as a salted hash in data/users.json)."""
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from ocr.auth import add_user  # noqa: E402
from ocr.config import load_settings  # noqa: E402


def main():
    if len(sys.argv) != 3:
        sys.exit("usage: create_user.py <username> <doctor|staff>")
    pw = getpass.getpass("Password (min 8 chars): ")
    if pw != getpass.getpass("Repeat password: "):
        sys.exit("passwords do not match")
    try:
        add_user(load_settings().users_file, sys.argv[1], pw, sys.argv[2])
    except ValueError as e:
        sys.exit(str(e))
    print(f"created {sys.argv[1].lower()} ({sys.argv[2]})")


if __name__ == "__main__":
    main()

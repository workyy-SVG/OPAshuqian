"""Run interactively locally; the raw password never appears in shell arguments."""
from getpass import getpass
from services.access_service import password_hash

if __name__ == '__main__':
    password = getpass('New password (12+ characters): ')
    confirm = getpass('Repeat password: ')
    if password != confirm:
        raise SystemExit('Passwords do not match.')
    print(password_hash(password))

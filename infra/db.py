"""Back up and restore the local development database (infra/docker-compose.yml).

    uv run python infra/db.py backup
    uv run python infra/db.py restore backups/nextpay-20261122-143000.dump

A backup is a pg_dump in PostgreSQL's custom format, written to ``backups/``
(git-ignored) with a timestamp in its name, and checked by listing it with
pg_restore. A restore replaces everything in the database with the backup's
contents; it asks first, and takes a backup of the current data before it
starts, so a restore can itself be undone.

pg_dump and pg_restore run inside the database container, so nothing needs to be
installed on the host and their version always matches the server. The dump is
moved as raw bytes through Python, never through a shell redirect, which on
Windows PowerShell would re-encode it as text and corrupt it.

Standard library only: this runs before the app's dependencies are installed.
"""

import argparse
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COMPOSE = ["docker", "compose", "-f", str(ROOT / "infra" / "docker-compose.yml")]
BACKUPS = ROOT / "backups"
# As in infra/docker-compose.yml.
SERVICE, USER, DATABASE = "postgres", "nextpay", "nextpay"


def in_container(*command: str, stdin: bytes | None = None) -> bytes:
    """Run ``command`` in the database container; its stdout, or exit with its error."""
    result = subprocess.run(
        [*COMPOSE, "exec", "-T", SERVICE, *command],
        input=stdin,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        message = result.stderr.decode("utf-8", errors="replace").strip()
        sys.exit(f"{command[0]} failed: {message or f'exit code {result.returncode}'}")
    return result.stdout


def backup(database: str, label: str = "") -> Path:
    """Dump ``database`` to a new timestamped file in backups/ and return its path."""
    dump = in_container("pg_dump", "-U", USER, "-d", database, "--format=custom")
    # A dump the restore tool can read back; an empty or cut-off one fails here.
    in_container("pg_restore", "--list", stdin=dump)
    BACKUPS.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    suffix = f"-{label}" if label else ""
    path = BACKUPS / f"{database}-{stamp}{suffix}.dump"
    if path.exists():
        sys.exit(f"{path} already exists; try again in a second.")
    path.write_bytes(dump)
    return path


def restore(path: Path, database: str, assume_yes: bool) -> None:
    """Replace everything in ``database`` with the contents of the backup at ``path``."""
    if not path.is_file():
        sys.exit(f"No backup at {path}.")
    dump = path.read_bytes()
    in_container("pg_restore", "--list", stdin=dump)  # refuse a broken file before touching data
    if not assume_yes:
        answer = input(
            f"Replace ALL data in the '{database}' database with {path.name}? "
            "Stop the API first. Type 'restore' to go on: "
        )
        if answer.strip() != "restore":
            sys.exit("Nothing changed.")
    safety = backup(database, label="before-restore")
    print(f"Current data backed up first to {safety.relative_to(ROOT)}")
    in_container(
        "pg_restore",
        "-U",
        USER,
        "-d",
        database,
        "--clean",
        "--if-exists",
        "--no-owner",
        "--single-transaction",
        stdin=dump,
    )
    print(f"Restored {path.name} into '{database}'.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--database", default=DATABASE, help=f"database to use (default {DATABASE})"
    )
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("backup", help="write a timestamped dump to backups/")
    restoring = commands.add_parser("restore", help="replace the database with a backup")
    restoring.add_argument("file", type=Path, help="a .dump file from backups/")
    restoring.add_argument("--yes", action="store_true", help="don't ask for confirmation")
    args = parser.parse_args()

    if args.command == "backup":
        path = backup(args.database)
        size = path.stat().st_size
        print(f"Backed up '{args.database}' to {path.relative_to(ROOT)} ({size:,} bytes)")
    else:
        restore(args.file.resolve(), args.database, args.yes)


if __name__ == "__main__":
    main()

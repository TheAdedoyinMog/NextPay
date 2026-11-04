"""Write the API's OpenAPI schema to a file, without starting a server or a database.

The mobile app's types are generated from this file (ADR 0012). Run it through
``npm run api:generate`` in ``mobile/``.
"""

import json
import sys
from pathlib import Path

from app.main import app


def export_openapi(output: Path) -> None:
    # Always LF, so the output is byte-identical on Windows and in CI.
    with output.open("w", encoding="utf-8", newline="\n") as file:
        json.dump(app.openapi(), file, indent=2)
        file.write("\n")


if __name__ == "__main__":
    export_openapi(Path(sys.argv[1]))

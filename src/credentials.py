"""Local Fantasy Challenge login file. Never commit the filled copy."""

from __future__ import annotations

from pathlib import Path

EXAMPLE_NAME = "fantasy_credentials.example"
FILE_NAME = "fantasy_credentials.properties"


def credentials_path(root: Path) -> Path:
    return root / "data" / FILE_NAME


def example_path(root: Path) -> Path:
    return root / "data" / EXAMPLE_NAME


def load_credentials(root: Path) -> dict[str, str]:
    """Read KEY=value pairs from the private properties file."""
    path = credentials_path(root)
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def fantasy_login(root: Path) -> tuple[str, str] | None:
    """Return (email, password) when both are filled in."""
    values = load_credentials(root)
    email = values.get("FANTASY_EMAIL", "").strip()
    password = values.get("FANTASY_PASSWORD", "").strip()
    if not email or not password or email.endswith("@example.com") or password == "your-password":
        return None
    return email, password

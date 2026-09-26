"""Build helper for standalone AOT/PyInstaller binaries with prompt cloaking."""

import base64
from pathlib import Path
from typing import Any


def cloak_prompt_string(prompt: str, key_byte: int = 0x5A) -> str:
    """XOR mask and base64 encode sensitive prompt strings to deter casual string extraction."""
    raw_bytes = prompt.encode("utf-8")
    masked = bytes([b ^ key_byte for b in raw_bytes])
    return base64.b64encode(masked).decode("utf-8")


def decloak_prompt_string(cloaked: str, key_byte: int = 0x5A) -> str:
    """Decode and unmask a cloaked prompt string at runtime."""
    masked = base64.b64decode(cloaked.encode("utf-8"))
    raw_bytes = bytes([b ^ key_byte for b in masked])
    return raw_bytes.decode("utf-8")


def get_binary_packaging_spec(package_root: Path) -> dict[str, Any]:
    """Return the PyInstaller/Nuitka bundling configuration for Migration Agent."""
    static_ui_dir = package_root / "src" / "migration_agent" / "ui" / "static"
    return {
        "entry_point": "src/migration_agent/cli.py",
        "binary_name": "migration-agent",
        "hidden_imports": [
            "google_genai",
            "openai_agents",
            "pydantic",
            "pydantic_settings",
            "typer",
            "migration_agent.adapters.control_api",
        ],
        "data_files": [
            (str(static_ui_dir), "migration_agent/ui/static"),
        ],
        "enable_lto": True,
        "strip_binaries": True,
    }

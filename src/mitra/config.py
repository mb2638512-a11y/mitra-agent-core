"""Instance configuration and safe local data paths."""

from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

_SAFE_ID = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,63}$")


def default_data_root() -> Path:
    override = os.getenv("MITRA_HOME")
    if override:
        return Path(override).expanduser().resolve()
    if sys.platform == "win32":
        base = Path(os.getenv("LOCALAPPDATA", Path.home() / "AppData/Local"))
        return base / "MITRA"
    if sys.platform == "darwin":
        return Path.home() / "Library/Application Support/MITRA"
    return Path(os.getenv("XDG_DATA_HOME", Path.home() / ".local/share")) / "mitra"


@dataclass(frozen=True)
class InstanceConfig:
    instance_id: str
    display_name: str
    data_dir: Path

    @classmethod
    def load(cls) -> "InstanceConfig":
        instance_id = os.getenv("MITRA_INSTANCE_ID", "default").strip()
        if not _SAFE_ID.fullmatch(instance_id) or instance_id in {".", ".."}:
            raise ValueError("MITRA_INSTANCE_ID must be 1-64 safe characters.")
        root = default_data_root()
        data_dir = (root / "instances" / instance_id).resolve()
        if root.resolve() not in data_dir.parents:
            raise ValueError("Invalid instance data path.")
        data_dir.mkdir(parents=True, exist_ok=True)
        return cls(
            instance_id=instance_id,
            display_name=os.getenv("MITRA_DISPLAY_NAME", f"MITRA ({instance_id})"),
            data_dir=data_dir,
        )

from dataclasses import dataclass
from pathlib import Path
import os


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    runtime_dir: Path
    bind_host: str = "127.0.0.1"
    bind_port: int = 8766

    @classmethod
    def from_env(cls) -> "Settings":
        root = Path(os.getenv("YIKE_MVP_ROOT", ".runtime")).resolve()
        return cls(data_dir=root / "data", runtime_dir=root / "collector")

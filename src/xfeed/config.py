from __future__ import annotations

import json
import os
import stat
from dataclasses import dataclass
from pathlib import Path


APP_NAME = "xfeed"


@dataclass(frozen=True)
class AppPaths:
    config_dir: Path
    session_file: Path


def get_app_paths() -> AppPaths:
    xdg_config_home = os.environ.get("XDG_CONFIG_HOME")
    if xdg_config_home:
        config_dir = Path(xdg_config_home) / APP_NAME
    else:
        config_dir = Path.home() / ".config" / APP_NAME
    return AppPaths(
        config_dir=config_dir,
        session_file=config_dir / "session.json",
    )


class SessionStore:
    def __init__(self, paths: AppPaths | None = None) -> None:
        self.paths = paths or get_app_paths()

    def save_cookies(self, cookies: dict[str, str]) -> Path:
        self.paths.config_dir.mkdir(parents=True, exist_ok=True)
        payload = {"cookies": cookies}
        self.paths.session_file.write_text(
            json.dumps(payload, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        os.chmod(
            self.paths.session_file,
            stat.S_IRUSR | stat.S_IWUSR,
        )
        return self.paths.session_file

    def load_cookies(self) -> dict[str, str]:
        if not self.paths.session_file.exists():
            raise FileNotFoundError(
                f"No session file found at {self.paths.session_file}. "
                "Run 'xfeed auth import-cookies <path>' first."
            )

        data = json.loads(self.paths.session_file.read_text(encoding="utf-8"))
        cookies = data.get("cookies")
        if not isinstance(cookies, dict) or not cookies:
            raise ValueError(
                f"Session file {self.paths.session_file} does not contain cookies."
            )
        return {str(key): str(value) for key, value in cookies.items()}

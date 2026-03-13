from __future__ import annotations

import json
from pathlib import Path


def load_cookie_mapping(path: str | Path) -> dict[str, str]:
    cookie_path = Path(path).expanduser()
    if not cookie_path.exists():
        raise FileNotFoundError(f"Cookie file not found: {cookie_path}")

    if cookie_path.suffix.lower() == ".json":
        return _parse_json(cookie_path)
    return _parse_netscape(cookie_path)


def _parse_json(path: Path) -> dict[str, str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        if _is_mapping_cookie_dict(data):
            return {str(key): str(value) for key, value in data.items()}
        cookies = data.get("cookies")
        if isinstance(cookies, list):
            return _list_to_mapping(cookies)
    if isinstance(data, list):
        return _list_to_mapping(data)
    raise ValueError(f"Unsupported JSON cookie format in {path}")


def _is_mapping_cookie_dict(data: dict[object, object]) -> bool:
    if not data:
        return False
    if "cookies" in data:
        return False
    return all(isinstance(key, str) and isinstance(value, str) for key, value in data.items())


def _list_to_mapping(cookies: list[object]) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for item in cookies:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        value = item.get("value", item.get("content"))
        if not isinstance(name, str) or value is None:
            continue
        parsed[name] = str(value)
    if not parsed:
        raise ValueError("Could not find any cookies in JSON data.")
    return parsed


def _parse_netscape(path: Path) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        parts = raw_line.split("\t")
        if len(parts) != 7:
            continue
        _, _, _, _, _, name, value = parts
        if name:
            parsed[name] = value
    if not parsed:
        raise ValueError(f"Unsupported Netscape cookie format in {path}")
    return parsed

"""Repository rules (CLAUDE.md) that would otherwise only live in review comments."""
from __future__ import annotations

import ast
import json
import re
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
COMP = ROOT / "custom_components" / "ha_microgreens"
WWW = COMP / "www"
STRINGS = json.loads((COMP / "strings.json").read_text(encoding="utf-8"))
EN_PANEL = json.loads((WWW / "i18n" / "en.json").read_text(encoding="utf-8"))

# Keys built at runtime (`status.${x}` and friends); every other en.json key
# must appear literally in the frontend source.
DYNAMIC_PREFIXES = (
    "status.", "tab.", "task.", "reason.", "outcome.", "legend.", "error.", "stage.",
    "card.view_", "card.field_", "card.title_", "card.help_", "settings.digest_time", "settings.reminder_time",
    "field.",
)
KEY_NAMESPACES = (
    "tab", "panel", "status", "outcome", "reason", "task", "stage", "legend", "rel", "line", "board", "timeline",
    "crop", "crops", "plots", "history", "settings", "field", "hint", "fact", "dialog", "btn", "confirm", "msg",
    "card", "error",
)
EM_DASH = chr(0x2014)  # spelled out, or this file would trip its own test
PLURAL = ("_zero", "_one", "_two", "_few", "_many", "_other")


def _tracked_text_files() -> list[Path]:
    out = subprocess.run(["git", "ls-files", "-co", "--exclude-standard"], cwd=ROOT, capture_output=True, text=True, check=True)
    files = []
    for name in out.stdout.splitlines():
        path = ROOT / name
        if path.suffix in {".png", ".jpg", ".webp", ".gz"} or name == "LICENSE" or not path.is_file():
            continue
        files.append(path)
    return files


def _base_key(key: str) -> str:
    for suffix in PLURAL:
        if key.endswith(suffix):
            return key[: -len(suffix)]
    return key


def _js_sources() -> str:
    return "\n".join(p.read_text(encoding="utf-8") for p in sorted(WWW.glob("*.js")))


def test_no_em_dash_anywhere() -> None:
    offenders = [str(p.relative_to(ROOT)) for p in _tracked_text_files() if EM_DASH in p.read_text(encoding="utf-8", errors="ignore")]
    assert offenders == [], f"em dash (U+2014) in {offenders}; use ' - ' or reword"


def test_strings_json_is_translations_en() -> None:
    assert json.loads((COMP / "translations" / "en.json").read_text(encoding="utf-8")) == STRINGS


def test_const_is_import_free() -> None:
    tree = ast.parse((COMP / "const.py").read_text(encoding="utf-8"))
    assert not [n for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom))]
    namespace: dict = {}
    exec(compile(tree, "const.py", "exec"), namespace)  # noqa: S102
    assert namespace["DOMAIN"] == "ha_microgreens"


def test_services_yaml_strings_and_handlers_agree() -> None:
    from custom_components.ha_microgreens import services

    services_yaml = yaml.safe_load((COMP / "services.yaml").read_text(encoding="utf-8"))
    assert set(services_yaml) == set(STRINGS["services"]) == set(services.HANDLERS) == set(services.SCHEMAS)
    for name, spec in services_yaml.items():
        yaml_fields = set((spec or {}).get("fields", {}))
        assert yaml_fields == set(STRINGS["services"][name].get("fields", {})), name
        schema_fields = {str(k) for k in services.SCHEMAS[name].schema}
        assert yaml_fields == schema_fields, name


def test_every_raised_error_key_is_translated() -> None:
    keys: set[str] = set()
    for path in COMP.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        keys |= set(re.findall(r'MicrogreensError\(\s*"([a-z_]+)"', text))
        keys |= set(re.findall(r'translation_key="([a-z_]+)"', text))
    keys.discard("legacy_entry")  # an issue, not an exception
    exceptions = set(STRINGS["exceptions"])
    assert keys - exceptions == set()
    # The panel shows the same messages: error.<key> for every exception key.
    assert {f"error.{k}" for k in exceptions} - set(EN_PANEL) == set()


def test_entity_translation_keys_exist() -> None:
    text = "\n".join(p.read_text(encoding="utf-8") for p in COMP.glob("*.py"))
    keys = set(re.findall(r'super\(\).__init__\(manager(?:, plot)?, "([a-z_]+)"\)', text))
    known = {k for platform in STRINGS["entity"].values() for k in platform}
    assert keys and keys <= known
    icons = json.loads((COMP / "icons.json").read_text(encoding="utf-8"))
    assert {k for p in icons["entity"].values() for k in p} == known
    assert set(icons["services"]) == set(STRINGS["services"])


def test_panel_keys_used_exist_and_none_are_dead() -> None:
    source = _js_sources()
    literals = set(re.findall(r"'((?:%s)\.[a-z_]+)'" % "|".join(KEY_NAMESPACES), source))
    bases = {_base_key(k) for k in EN_PANEL}
    missing = sorted(k for k in literals if k not in bases)
    assert missing == [], f"used in JS but missing from i18n/en.json: {missing}"
    dead = sorted(k for k in bases if k not in literals and not k.startswith(DYNAMIC_PREFIXES))
    assert dead == [], f"in i18n/en.json but never used: {dead}"


def test_dynamic_keys_cover_every_value() -> None:
    from custom_components.ha_microgreens import const

    for status in const.PLOT_STATUSES:
        assert f"status.{status}" in EN_PANEL
        assert status in STRINGS["entity"]["sensor"]["status"]["state"]
    for kind in const.TASK_ORDER:
        assert f"task.{kind}" in EN_PANEL
        assert f"task_{kind}" in STRINGS["common"]
        assert f"line_{kind}" in STRINGS["common"]
    for reason in const.DISCARD_REASONS:
        assert f"reason.{reason}" in EN_PANEL
        assert reason in STRINGS["selector"]["discard_reason"]["options"]
    for key, *_ in const.DEFAULT_PROFILES:
        assert f"crop_{key}" in STRINGS["common"]


def _placeholders(text: str) -> set[str]:
    return set(re.findall(r"\{(\w+)\}", text))


def _flatten(d: dict, prefix: str = "") -> dict[str, str]:
    out: dict[str, str] = {}
    for k, v in d.items():
        if isinstance(v, dict):
            out.update(_flatten(v, f"{prefix}{k}."))
        else:
            out[f"{prefix}{k}"] = v
    return out


@pytest.mark.parametrize("path", sorted((COMP / "translations").glob("*.json")), ids=lambda p: p.name)
def test_ha_translation_placeholders_match_english(path: Path) -> None:
    english = _flatten(STRINGS)
    other = _flatten(json.loads(path.read_text(encoding="utf-8")))
    assert set(other) <= set(english), f"{path.name} has keys English does not"
    for key, text in other.items():
        assert _placeholders(text) == _placeholders(english[key]), f"{path.name}: {key}"


@pytest.mark.parametrize("path", sorted((WWW / "i18n").glob("*.json")), ids=lambda p: p.name)
def test_panel_translation_placeholders_match_english(path: Path) -> None:
    other = json.loads(path.read_text(encoding="utf-8"))
    bases = {_base_key(k): k for k in EN_PANEL}
    for key, text in other.items():
        base = _base_key(key)
        assert base in bases, f"{path.name}: {key} is not an English key"
        reference = EN_PANEL.get(key) or EN_PANEL.get(f"{base}_other") or EN_PANEL[base]
        assert _placeholders(text) <= _placeholders(reference) | {"count"}, f"{path.name}: {key}"


def test_manifest_version_matches_changelog() -> None:
    version = json.loads((COMP / "manifest.json").read_text(encoding="utf-8"))["version"]
    heading = re.search(r"^## (\S+)", (ROOT / "CHANGELOG.md").read_text(encoding="utf-8"), re.M)
    assert heading and heading.group(1) == version


def test_hacs_floor_matches_tested_ha() -> None:
    hacs = json.loads((ROOT / "hacs.json").read_text(encoding="utf-8"))
    assert re.match(r"^\d{4}\.\d+\.\d+$", hacs["homeassistant"])

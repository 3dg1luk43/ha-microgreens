"""Frontend checks driven through node: syntax of every module, and the core unit tests."""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
WWW = ROOT / "custom_components" / "ha_microgreens" / "www"
NODE = shutil.which("node")

pytestmark = pytest.mark.skipif(NODE is None, reason="node is not installed (CI installs it)")


@pytest.mark.parametrize("path", sorted(WWW.glob("*.js")), ids=lambda p: p.name)
def test_module_parses(path: Path, tmp_path: Path) -> None:
    # As .mjs, so node parses it as the ES module the browser loads.
    copy = tmp_path / f"{path.stem}.mjs"
    copy.write_bytes(path.read_bytes())
    result = subprocess.run([NODE, "--check", str(copy)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_core_unit_tests() -> None:
    result = subprocess.run(
        [NODE, str(ROOT / "tests" / "js" / "core.test.mjs")],
        capture_output=True,
        text=True,
        env={**os.environ, "TZ": "Europe/Prague"},
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "passed" in result.stdout

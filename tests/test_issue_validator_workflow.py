"""Regression tests for .github/workflows/issue_validator.yml.

A report filed over the API (``gh issue create`` with the template text pasted in)
arrives with no labels, because GitHub applies an issue form's ``labels:`` only on the
web path, and usually with ``##`` headings where the form renders ``###``. The
validator must restore the label and still read every field.

Actions cannot run locally, so the job scripts are extracted from the workflow and
executed by ``devtools/issue_validator_harness.mjs`` against a stubbed GitHub API.
The tests run the shipped script text, not a copy, so they fail if the workflow drifts.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parent.parent
WORKFLOW = REPO / ".github" / "workflows" / "issue_validator.yml"
HARNESS = REPO / "devtools" / "issue_validator_harness.mjs"
BUG_TEMPLATE = REPO / ".github" / "ISSUE_TEMPLATE" / "bug_report.yml"

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node is required to run the workflow scripts")


def _script(job: str) -> str:
    data = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    return data["jobs"][job]["steps"][0]["with"]["script"]


def _run(scenarios: list[dict]) -> dict[str, dict]:
    spec = {
        "restoreScript": _script("restore-template-label"),
        "validateScript": _script("validate-bug-report"),
        "scenarios": scenarios,
    }
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
        json.dump(spec, fh)
        path = fh.name
    try:
        proc = subprocess.run(["node", str(HARNESS), path], capture_output=True, text=True, timeout=60, check=False)
    finally:
        Path(path).unlink(missing_ok=True)
    assert proc.returncode == 0, f"harness failed:\n{proc.stderr}"
    return {r["name"]: r for r in json.loads(proc.stdout)}


def _bug_body(heading: str, version: str = "0.2.0", ha: str = "2026.10.3") -> str:
    """A complete bug report at the given heading level."""
    h = heading
    return "\n".join(
        [
            f"{h} Before You Submit",
            "",
            "- [x] I have searched the existing issues.",
            "",
            f"{h} Describe the Bug",
            "",
            "Pressing Uncover on plot A2 leaves the tray covered.",
            "",
            f"{h} Affected Area",
            "",
            "Sidebar panel",
            "",
            f"{h} Microgreens Version",
            "",
            version,
            "",
            f"{h} Home Assistant Version",
            "",
            ha,
            "",
            f"{h} Reproduction Steps",
            "",
            "1. Sow radish on A2 three days ago.",
            "2. Press Uncover on the board.",
            "",
            f"{h} Expected Behavior",
            "",
            "The tray shows as growing.",
            "",
            f"{h} Logs / Error Evidence",
            "",
            "```",
            "2026-11-06 08:00:01.120 ERROR (MainThread) [custom_components.ha_microgreens.manager]",
            "  Error handling planting/action: planting_not_found",
            "```",
            "",
            f"{h} Additional Context",
            "",
            "Started after the update.",
        ]
    )


def _scenario(name: str, body: str, labels: list[str] | None = None) -> dict:
    return {"name": name, "body": body, "labels": labels or [], "latestRelease": "v0.2.1"}


def test_api_filed_bug_report_gets_its_template_label_back() -> None:
    res = _run([_scenario("api-bug", _bug_body("##"))])["api-bug"]
    assert res["restore"]["addedLabels"] == ["bug"]


def test_api_filed_bug_report_is_validated() -> None:
    """The validator runs for it and flags only the outdated version."""
    res = _run([_scenario("api-bug", _bug_body("##"))])["api-bug"]
    (comment,) = res["validate"]["comments"]
    assert "Outdated version" in comment
    assert "`0.2.0`" in comment and "v0.2.1" in comment
    for field in ("**Home Assistant Version** is missing", "**Logs / Error Evidence** are missing"):
        assert field not in comment, f"{field!r} wrongly reported for a ## body"
    assert res["validate"]["addedLabels"] == ["more info required"]


@pytest.mark.parametrize("heading", ["##", "###", "####"])
def test_fields_are_read_at_any_heading_level(heading: str) -> None:
    res = _run([_scenario("h", _bug_body(heading, version="0.2.1"), ["bug"])])["h"]
    assert res["validate"]["comments"] == []
    assert res["validate"]["addedLabels"] == []


def test_web_form_report_with_blank_fields_is_flagged() -> None:
    body = "\n".join(
        [
            "### Describe the Bug",
            "",
            "It breaks.",
            "",
            "### Microgreens Version",
            "",
            "_No response_",
            "",
            "### Home Assistant Version",
            "",
            "_No response_",
            "",
            "### Logs / Error Evidence",
            "",
            "_No response_",
        ]
    )
    (comment,) = _run([_scenario("blank", body, ["bug"])])["blank"]["validate"]["comments"]
    for field in ("Microgreens Version", "Home Assistant Version", "Logs / Error Evidence"):
        assert field in comment


def test_home_assistant_below_the_minimum_is_flagged() -> None:
    res = _run([_scenario("old", _bug_body("###", version="0.2.1", ha="2025.12.4"), ["bug"])])["old"]
    (comment,) = res["validate"]["comments"]
    assert "Home Assistant 2025.12 is not supported" in comment


def test_the_minimum_itself_is_accepted() -> None:
    """2026.2.0 is also the form's placeholder; a real report may carry exactly that."""
    res = _run([_scenario("min", _bug_body("###", version="0.2.1", ha="2026.2.0"), ["bug"])])["min"]
    assert res["validate"]["comments"] == []


def test_minimum_matches_hacs_json_and_the_template() -> None:
    floor = json.loads((REPO / "hacs.json").read_text(encoding="utf-8"))["homeassistant"]
    major_minor = ".".join(floor.split(".")[:2])
    assert f"const MIN_HA = '{major_minor}';" in _script("validate-bug-report")
    assert f"needs {major_minor} or newer" in BUG_TEMPLATE.read_text(encoding="utf-8")


def test_feature_request_is_labelled_and_not_bug_validated() -> None:
    body = "\n".join(
        [
            "## Before You Submit",
            "",
            "- [x] yes",
            "",
            "## Problem or Motivation",
            "",
            "I grow two trays of radish.",
            "",
            "## Proposed Solution",
            "",
            "Name both in the notification.",
            "",
            "## Related Area",
            "",
            "Notifications",
            "",
            "## Contributing an Implementation",
            "",
            "- [ ] no",
        ]
    )
    res = _run([_scenario("fr", body)])["fr"]
    assert res["restore"]["addedLabels"] == ["feature request"]
    assert res["validate"]["comments"] == []


def test_free_form_issue_is_never_labelled() -> None:
    res = _run([_scenario("free", "# Summary\n\nIt is broken.\n\n# Impact\n\nBad.\n")])["free"]
    assert res["restore"]["addedLabels"] == []
    assert res["validate"]["comments"] == []


def test_a_single_stray_heading_does_not_mislabel() -> None:
    res = _run([_scenario("stray", "# Notes\n\n## Proposed Solution\n\nmaybe do X.\n")])["stray"]
    assert res["restore"]["addedLabels"] == []


def test_existing_template_label_is_left_alone() -> None:
    res = _run([_scenario("kept", _bug_body("###", version="0.2.1"), ["bug"])])["kept"]
    assert res["restore"]["addedLabels"] == []


def test_heading_lists_match_the_templates() -> None:
    """Every field label in the issue forms is a heading the workflows know."""
    labels = set()
    for path in (REPO / ".github" / "ISSUE_TEMPLATE").glob("*.yml"):
        form = yaml.safe_load(path.read_text(encoding="utf-8"))
        if "body" in form:
            labels |= {f["attributes"]["label"] for f in form["body"] if f["type"] != "markdown"}
    for workflow, job in (("issue_validator.yml", "close-templateless-issues"), ("auto_assign_issues.yml", "assign")):
        data = yaml.safe_load((REPO / ".github" / "workflows" / workflow).read_text(encoding="utf-8"))
        script = data["jobs"][job]["steps"][0]["with"]["script"]
        listed = set(re.findall(r"'([^']+)'", script.split("KNOWN_HEADINGS = [", 1)[1].split("];", 1)[0]))
        assert listed == labels, f"{workflow}: {sorted(listed ^ labels)}"


def test_job_triggers_are_scoped_correctly() -> None:
    """``restore-template-label`` stays opened/reopened-only (an ``edited`` run would
    re-add a label a maintainer removed on purpose); ``validate-bug-report`` keeps
    ``always()`` or a skipped ``needs`` would skip it too."""
    data = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    restore = data["jobs"]["restore-template-label"]["if"]
    assert "'opened'" in restore and "'reopened'" in restore
    assert "'edited'" not in restore
    validate = data["jobs"]["validate-bug-report"]
    assert validate["needs"] == "restore-template-label"
    assert "always()" in validate["if"]
    assert "labels.*.name" not in validate["if"]

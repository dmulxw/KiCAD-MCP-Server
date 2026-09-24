"""Tests for issue: run_drc reported only `violations` from kicad-cli's JSON.

kicad-cli writes unrouted pads under a separate top-level `unconnected_items`
key, and `run_drc` never read it -- so a board with hundreds of unconnected
pads came back as "Found 66 DRC violations" with nothing to suggest it was
unrouted. `get_drc_violations` read the same truncated file, so the count that
decides whether a board is finished was the one silently dropped.

Measured on the touch-panel build: the 00:11 board had 3 unconnected items
against 145 violations at 00:04; the tool reported neither number correctly,
and the unconnected count was absent entirely.

These tests drive run_drc against a stubbed subprocess so the parsing, the
summary and the on-disk violations file are all checked without kicad-cli.
"""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent / "python"))

from commands.design_rules import DesignRuleCommands  # noqa: E402


def _drc_payload(violations=None, unconnected=None):
    """A minimal kicad-cli `--format json` DRC document."""
    return {
        "date": "2026-09-11T16:02:34+0000",
        "violations": violations or [],
        "unconnected_items": unconnected or [],
    }


def _violation(vtype="clearance", severity="error", description="Clearance violation"):
    return {
        "type": vtype,
        "severity": severity,
        "description": description,
        "items": [{"description": "Track [A]", "pos": {"x": 1.5, "y": 2.5}}],
    }


def _unconnected(severity="error"):
    return {
        "description": "Missing connection between items",
        "severity": severity,
        "items": [
            {"description": "Pad 4 [ROW3] of J1", "pos": {"x": 127.25, "y": 243.15}},
            {"description": "Track [ROW3]", "pos": {"x": 118.65, "y": 129.25}},
        ],
    }


def _make_commands(board_path, kicad_cli="/usr/bin/kicad-cli"):
    """A DesignRuleCommands whose board reports `board_path` as its file."""
    board = MagicMock(name="BOARD")
    board.GetFileName.return_value = str(board_path)
    return DesignRuleCommands(board), kicad_cli


def _run(command, board_path, payload, kicad_cli="/usr/bin/kicad-cli", params=None):
    """Run run_drc with subprocess stubbed to write `payload` to --output.

    Returns (result, captured_cmd) so callers can also assert on the argv.
    """
    captured = {}

    def fake_run(cmd, *args, **kwargs):
        captured["cmd"] = cmd
        out = cmd[cmd.index("--output") + 1]
        Path(out).write_text(json.dumps(payload), encoding="utf-8")
        return MagicMock(returncode=0, stderr="", stdout="")

    with patch("commands.design_rules.resolve_kicad_cli", return_value=kicad_cli):
        with patch("subprocess.run", side_effect=fake_run):
            result = command.run_drc(params or {})
    return result, captured["cmd"]


# --- run_drc surfaces unconnected items -------------------------------------


def test_run_drc_reports_unconnected_count_in_summary(tmp_path):
    board = tmp_path / "board.kicad_pcb"
    board.write_text("", encoding="utf-8")
    command, _ = _make_commands(board)

    payload = _drc_payload(
        violations=[_violation()],
        unconnected=[_unconnected(), _unconnected()],
    )
    result, _ = _run(command, board, payload)

    assert result["success"] is True
    assert result["summary"]["total"] == 1
    assert result["summary"]["total_unconnected"] == 2


def test_run_drc_mentions_unconnected_in_message(tmp_path):
    board = tmp_path / "board.kicad_pcb"
    board.write_text("", encoding="utf-8")
    command, _ = _make_commands(board)

    payload = _drc_payload(unconnected=[_unconnected()])
    result, _ = _run(command, board, payload)

    # An agent that reads only `message` is exactly the caller this used to
    # mislead, so the count has to be in the prose too.
    assert "unconnected" in result["message"]
    assert "1" in result["message"]


def test_run_drc_counts_unconnected_severity(tmp_path):
    board = tmp_path / "board.kicad_pcb"
    board.write_text("", encoding="utf-8")
    command, _ = _make_commands(board)

    payload = _drc_payload(
        violations=[_violation(severity="warning")],
        unconnected=[_unconnected()],
    )
    result, _ = _run(command, board, payload)

    assert result["summary"]["by_severity"]["error"] == 1
    assert result["summary"]["by_severity"]["warning"] == 1


def test_run_drc_writes_unconnected_to_violations_file(tmp_path):
    board = tmp_path / "board.kicad_pcb"
    board.write_text("", encoding="utf-8")
    command, _ = _make_commands(board)

    payload = _drc_payload(
        violations=[_violation()],
        unconnected=[_unconnected()],
    )
    result, _ = _run(command, board, payload)

    data = json.loads(Path(result["violationsFile"]).read_text(encoding="utf-8"))
    assert data["total_unconnected"] == 1
    assert len(data["unconnected_items"]) == 1
    # Kept apart from `violations`: an unrouted pad is not a rule breach, and
    # merging them would inflate `total_violations`.
    assert data["total_violations"] == 1
    assert len(data["violations"]) == 1

    entry = data["unconnected_items"][0]
    assert entry["type"] == "unconnected_items"
    assert entry["severity"] == "error"
    assert entry["location"]["x"] == 127.25
    assert entry["location"]["y"] == 243.15


def test_run_drc_omits_unconnected_key_when_none(tmp_path):
    board = tmp_path / "board.kicad_pcb"
    board.write_text("", encoding="utf-8")
    command, _ = _make_commands(board)

    result, _ = _run(command, board, _drc_payload(violations=[_violation()]))

    assert "total_unconnected" not in result["summary"]
    assert result["message"] == "Found 1 DRC violations"


# --- the --severity-all opt-in ----------------------------------------------


def test_run_drc_omits_severity_all_by_default(tmp_path):
    board = tmp_path / "board.kicad_pcb"
    board.write_text("", encoding="utf-8")
    command, _ = _make_commands(board)

    _, cmd = _run(command, board, _drc_payload(violations=[_violation()]))

    assert "--severity-all" not in cmd


def test_run_drc_passes_severity_all_when_asked(tmp_path):
    board = tmp_path / "board.kicad_pcb"
    board.write_text("", encoding="utf-8")
    command, _ = _make_commands(board)

    _, cmd = _run(command, board, _drc_payload(violations=[_violation()]),
                  params={"severityAll": True})

    assert "--severity-all" in cmd
    # The board path must stay last -- kicad-cli takes it positionally.
    assert cmd[-1] == str(board)


# --- get_drc_violations includes them ---------------------------------------


def _violations_file(tmp_path, payload):
    """A violations file as run_drc would have written it."""
    out = tmp_path / "board_drc_violations.json"
    out.write_text(
        json.dumps(
            {
                "total_violations": len(payload["violations"]),
                "total_unconnected": len(payload["unconnected_items"]),
                "violations": [
                    {"type": v["type"], "severity": v["severity"],
                     "message": v["description"],
                     "location": {"x": 0, "y": 0, "unit": "mm"}}
                    for v in payload["violations"]
                ],
                "unconnected_items": [
                    {"type": "unconnected_items", "severity": u["severity"],
                     "message": u["description"],
                     "location": {"x": u["items"][0]["pos"]["x"],
                                  "y": u["items"][0]["pos"]["y"], "unit": "mm"}}
                    for u in payload["unconnected_items"]
                ],
            }
        ),
        encoding="utf-8",
    )
    return str(out)


def _run_get_violations(tmp_path, payload, params=None):
    board = tmp_path / "board.kicad_pcb"
    board.write_text("", encoding="utf-8")
    command, _ = _make_commands(board)
    violations_file = _violations_file(tmp_path, payload)

    with patch.object(
        command, "run_drc", return_value={"success": True, "violationsFile": violations_file}
    ):
        return command.get_drc_violations(params or {})


def test_get_drc_violations_includes_unconnected_by_default(tmp_path):
    payload = _drc_payload(
        violations=[_violation()],
        unconnected=[_unconnected(), _unconnected()],
    )
    result = _run_get_violations(tmp_path, payload)

    types = [v["type"] for v in result["violations"]]
    assert types.count("unconnected_items") == 2
    assert "clearance" in types


def test_get_drc_violations_can_exclude_unconnected(tmp_path):
    payload = _drc_payload(
        violations=[_violation()],
        unconnected=[_unconnected()],
    )
    result = _run_get_violations(tmp_path, payload, {"includeUnconnected": False})

    assert [v["type"] for v in result["violations"]] == ["clearance"]


def test_get_drc_violations_severity_filter_applies_to_unconnected(tmp_path):
    payload = _drc_payload(
        violations=[_violation(severity="warning")],
        unconnected=[_unconnected()],
    )
    result = _run_get_violations(tmp_path, payload, {"severity": "error"})

    assert [v["type"] for v in result["violations"]] == ["unconnected_items"]


def test_get_drc_violations_explicit_null_still_includes_unconnected(tmp_path):
    # dict.get(k, default) returns None for an explicit null, which would
    # switch the unconnected report off by accident -- the same silent drop
    # this change exists to fix.
    payload = _drc_payload(
        violations=[_violation()],
        unconnected=[_unconnected()],
    )
    result = _run_get_violations(tmp_path, payload, {"includeUnconnected": None})

    types = [v["type"] for v in result["violations"]]
    assert types.count("unconnected_items") == 1


def test_run_drc_explicit_null_severity_all_is_off(tmp_path):
    board = tmp_path / "board.kicad_pcb"
    board.write_text("", encoding="utf-8")
    command, _ = _make_commands(board)

    _, cmd = _run(command, board, _drc_payload(violations=[_violation()]),
                  params={"severityAll": None})

    assert "--severity-all" not in cmd

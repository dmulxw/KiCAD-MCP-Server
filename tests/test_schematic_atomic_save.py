"""Regression test for atomic schematic saves.

``SchematicManager.save_schematic`` used to write straight to the target path.
Both kicad-skip's ``write`` and the prettify pass that follows open with mode
"w", which truncates on open -- so a worker killed after the truncate but
before the write left a 0-byte .kicad_sch and every symbol in it was gone.

This was not hypothetical: building a 210-component schematic through
``batch_add_and_connect``, the bridge abandoned a call at its 30 s default
while the Python worker was still saving. The next tool call then failed
against an empty file.

The save now builds in a temp file beside the target and renames into place,
so the path holds either the previous schematic or the complete new one.
"""

import sys
import tempfile
from pathlib import Path

PYTHON_DIR = Path(__file__).parent.parent / "python"
sys.path.insert(0, str(PYTHON_DIR))

from commands.schematic import SchematicManager  # noqa: E402

ORIGINAL = "(kicad_sch (version 20241209) (generator eeschema))\n"


class _WriterThatDiesMidSave:
    """Stands in for a worker killed between truncate and write."""

    def write(self, path: str) -> None:
        # kicad-skip truncates the destination before anything is serialised,
        # so by the time the kill lands the file is already empty.
        with open(path, "w", encoding="utf-8") as f:
            f.write("")
        raise RuntimeError("worker killed mid-save")


class _WorkingWriter:
    def write(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            f.write(ORIGINAL)


def test_failed_save_leaves_the_previous_schematic_intact(tmp_path):
    target = tmp_path / "board.kicad_sch"
    target.write_text(ORIGINAL, encoding="utf-8")

    assert SchematicManager.save_schematic(_WriterThatDiesMidSave(), str(target)) is False

    # The whole point: not truncated, not partially written.
    assert target.read_text(encoding="utf-8") == ORIGINAL


def test_failed_save_does_not_leave_a_temp_file_behind(tmp_path):
    target = tmp_path / "board.kicad_sch"
    target.write_text(ORIGINAL, encoding="utf-8")

    SchematicManager.save_schematic(_WriterThatDiesMidSave(), str(target))

    assert [p.name for p in tmp_path.iterdir()] == [target.name]


def test_successful_save_replaces_the_file_and_cleans_up(tmp_path):
    target = tmp_path / "board.kicad_sch"
    target.write_text(ORIGINAL, encoding="utf-8")

    assert SchematicManager.save_schematic(_WorkingWriter(), str(target)) is True

    assert "(kicad_sch" in target.read_text(encoding="utf-8")
    # Renamed into place, not copied-and-left: no stray temp file alongside.
    assert [p.name for p in tmp_path.iterdir()] == [target.name]


def test_save_creates_the_file_when_none_exists(tmp_path):
    target = tmp_path / "fresh.kicad_sch"

    assert SchematicManager.save_schematic(_WorkingWriter(), str(target)) is True

    assert target.exists()
    assert "(kicad_sch" in target.read_text(encoding="utf-8")


def test_temp_file_is_built_beside_the_target(tmp_path):
    """os.replace is only atomic within a filesystem; /tmp may be another mount."""
    seen: list[str] = []

    class _RecordingWriter:
        def write(self, path: str) -> None:
            seen.append(path)
            with open(path, "w", encoding="utf-8") as f:
                f.write(ORIGINAL)

    target = tmp_path / "board.kicad_sch"
    SchematicManager.save_schematic(_RecordingWriter(), str(target))

    assert seen, "kicad-skip was never asked to write"
    assert Path(seen[0]).parent == tmp_path
    assert Path(seen[0]) != target


def test_temp_file_keeps_the_kicad_sch_suffix(tmp_path):
    """kicad-skip infers the output format from the extension."""
    seen: list[str] = []

    class _RecordingWriter:
        def write(self, path: str) -> None:
            seen.append(path)
            with open(path, "w", encoding="utf-8") as f:
                f.write(ORIGINAL)

    SchematicManager.save_schematic(_RecordingWriter(), str(tmp_path / "board.kicad_sch"))

    assert seen[0].endswith(".kicad_sch")


def test_temp_file_uses_a_hidden_name(tmp_path):
    """A crashed build should be recognisable, not look like a real sheet."""
    seen: list[str] = []

    class _RecordingWriter:
        def write(self, path: str) -> None:
            seen.append(path)
            with open(path, "w", encoding="utf-8") as f:
                f.write(ORIGINAL)

    SchematicManager.save_schematic(_RecordingWriter(), str(tmp_path / "board.kicad_sch"))

    assert Path(seen[0]).name.startswith(".")


def test_temp_file_comes_from_mkstemp(tmp_path):
    """Distinct names per call, so concurrent saves cannot clobber each other."""
    seen: list[str] = []

    class _RecordingWriter:
        def write(self, path: str) -> None:
            seen.append(path)
            with open(path, "w", encoding="utf-8") as f:
                f.write(ORIGINAL)

    target = tmp_path / "board.kicad_sch"
    SchematicManager.save_schematic(_RecordingWriter(), str(target))
    SchematicManager.save_schematic(_RecordingWriter(), str(target))

    assert len(set(seen)) == 2


def test_original_survives_a_save_that_never_starts(tmp_path):
    """A writer that fails before touching its target leaves the old file alone."""
    target = tmp_path / "board.kicad_sch"
    target.write_text(ORIGINAL, encoding="utf-8")

    class _RefusesToStart:
        def write(self, path: str) -> None:
            raise OSError("no space left on device")

    assert SchematicManager.save_schematic(_RefusesToStart(), str(target)) is False
    assert target.read_text(encoding="utf-8") == ORIGINAL

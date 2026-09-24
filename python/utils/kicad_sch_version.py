"""Which ``.kicad_sch`` file-format version to stamp on a schematic we create.

eeschema and kicad-cli refuse to open a schematic whose ``(version ...)`` is
newer than the release reading it, and the only symptom is a bare "Failed to
load schematic" -- no version, no line number, nothing to grep for. So the
header has to follow the KiCad actually installed, not the release that
happened to be current when this code was written.

That distinction is load-bearing for this project's own workflow. Syncing a
schematic to its board shells out to ``kicad-cli sch export netlist`` to
enumerate components, and that path has no fallback: an unreadable schematic
yields an empty component list, so ``sync_schematic_to_board`` reports success
while adding zero footprints.

Writing an *older* format than the installed KiCad is always safe -- newer
releases read older files -- so the failure mode only goes one way and the
fallback below is chosen accordingly.
"""

from typing import Dict, Tuple

#: KiCad major version -> (file format token, generator_version string), taken
#: from what each release writes for a new schematic.
_SCH_FORMATS: Dict[int, Tuple[int, str]] = {
    8: (20231120, "8.0"),
    9: (20250114, "9.0"),
    10: (20260101, "10.0"),
}


def installed_kicad_major() -> int:
    """Major version of the KiCad we are running inside, or 0 if unknown.

    ``pcbnew.Version()`` is the same probe ``_hierplace`` uses to pick between
    KiCad 5 and 7 APIs, so it is known to be present on the backends that load
    the Python module at all.
    """
    try:
        import pcbnew  # type: ignore
    except ImportError:
        return 0

    for attr in ("Version", "GetBuildVersion"):
        probe = getattr(pcbnew, attr, None)
        if probe is None:
            continue
        try:
            return int(str(probe()).split(".")[0])
        except (TypeError, ValueError):
            continue
    return 0


def schematic_format() -> Tuple[int, str]:
    """``(version token, generator_version)`` for a schematic this build writes.

    Picks the newest format the installed KiCad understands. If the running
    release cannot be identified, or predates every format listed above, fall
    back to the oldest one -- a stale header is readable, a future one is not.
    """
    major = installed_kicad_major()
    if major:
        usable = [m for m in sorted(_SCH_FORMATS) if m <= major]
        if usable:
            return _SCH_FORMATS[usable[-1]]
    return _SCH_FORMATS[min(_SCH_FORMATS)]

"""
Regression tests for BoardOutlineCommands.add_mounting_hole.

Covers four prior bugs:

1. Empty FPID
   The footprint was created with no id at all, producing
   `(footprint "" ...)` in the .kicad_pcb. KiCad's GUI Move tool refuses to
   select footprints with no id, so users couldn't drag the resulting MHs in
   the editor. Fixed by giving it a name -- a *board-local* name, not a
   library link, because the footprint is synthesized and a `lib:name` claim
   makes library parity report `lib_footprint_mismatch` on every board.

2. NPTH pad on copper layers
   The pad was emitted with the default LSET (`*.Cu` + `*.Mask`) even when
   `plated:false`. With `padDiameter > diameter` that produces phantom
   copper annular rings on every Cu layer, which trigger DRC clearance
   errors against neighbouring nets.

3. NPTH mask aperture wider than the hole
   `padDiameter` defaulted to `diameter + 1mm` unconditionally. For an NPTH
   pad the pad size *is* the mask aperture, so the default punched a hole in
   the mask 1mm wider than the hole itself: 0.5mm of bare laminate all round,
   which bridges any track passing through it.

4. No courtyard, so DRC could not see the screw head
   The synthesized footprint carried none of the geometry the library has, so
   the courtyard check skipped it entirely and parts could sit under a screw
   head with nothing reported. Every `MountingHole_*mm` library footprint
   draws the hole on Cmts.User at the drill *diameter* and the screw-head
   keep-out on F.CrtYd at `diameter + 0.25` (2.1 -> 2.35, 2.5 -> 2.75,
   2.7 -> 2.95), and marks itself `exclude_from_pos_files exclude_from_bom`.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "python"))

import pcbnew  # noqa: E402  — pcbnew is stubbed by conftest


class _V2I:
    """
    Value-comparing stand-in for pcbnew.VECTOR2I, which is in nanometres.

    `pcbnew` is process-wide, and other test modules replace VECTOR2I with a
    class of their own that compares by identity. Asserting against a freshly
    constructed call argument then only works when this module runs alone.
    monkeypatch puts this one back on teardown, so the ordering stops mattering.
    """

    def __init__(self, x=0, y=0):
        self.x, self.y = x, y

    def __eq__(self, other):
        return isinstance(other, _V2I) and (self.x, self.y) == (other.x, other.y)

    def __hash__(self):
        return hash((self.x, self.y))

    def __repr__(self):
        return f"VECTOR2I({self.x}, {self.y})"


@pytest.fixture
def fresh_pcbnew_mock(monkeypatch):
    """
    The conftest pcbnew is a long-lived MagicMock. Reset its call history
    before each test so we can make precise assertions about what
    add_mounting_hole calls on the pcbnew API.
    """
    pcbnew.reset_mock()
    monkeypatch.setattr(pcbnew, "VECTOR2I", _V2I)
    # PAD_ATTRIB constants must compare unequal so the conditional in the
    # implementation picks the right branch.
    pcbnew.PAD_ATTRIB_NPTH = "NPTH"
    pcbnew.PAD_ATTRIB_PTH = "PTH"
    pcbnew.PAD_SHAPE_CIRCLE = "circle"
    pcbnew.F_Mask = "F.Mask"
    pcbnew.B_Mask = "B.Mask"
    # Real ints, not mocks: `A | B` on two MagicMocks builds a fresh mock on
    # every evaluation, so the value passed would never compare equal to the
    # value asserted.
    pcbnew.FP_EXCLUDE_FROM_POS_FILES = 4
    pcbnew.FP_EXCLUDE_FROM_BOM = 8
    # Likewise compared by value in the assertions below.
    pcbnew.Cmts_User = "Cmts.User"
    pcbnew.F_CrtYd = "F.CrtYd"
    pcbnew.SHAPE_T_CIRCLE = "circle"
    return pcbnew


@pytest.fixture
def cmds(fresh_pcbnew_mock):
    from commands.board.outline import BoardOutlineCommands

    board = MagicMock(name="board")
    board.GetFootprints.return_value = []  # no existing MHs
    return BoardOutlineCommands(board=board)


def _captured_module(pcbnew_mock):
    """Return the FOOTPRINT mock instance created by the call under test."""
    return pcbnew_mock.FOOTPRINT.return_value


def _captured_pad(pcbnew_mock):
    """Return the PAD mock instance created by the call under test."""
    return pcbnew_mock.PAD.return_value


# ---------------------------------------------------------------------------
# Bug #1: empty FPID
# ---------------------------------------------------------------------------


class TestFootprintLibIdSet:
    def test_default_fpid_is_board_local_not_a_library_claim(
        self, cmds, fresh_pcbnew_mock
    ):
        result = cmds.add_mounting_hole(
            {
                "position": {"x": 117, "y": 84.5, "unit": "mm"},
                "diameter": 3.2,
                "padDiameter": 3.5,
            }
        )

        assert result["success"] is True

        # Empty nickname: the footprint is built here, not loaded from a
        # library. Claiming `MountingHole:MountingHole_3.2mm` makes DRC
        # compare it against a library file it was not built from, which
        # reports lib_footprint_mismatch on every board that uses this call.
        fresh_pcbnew_mock.LIB_ID.assert_called_once_with("", "MountingHole_3.2mm")
        # Still non-empty, so the GUI Move tool can select it.
        _captured_module(fresh_pcbnew_mock).SetFPID.assert_called_once_with(
            fresh_pcbnew_mock.LIB_ID.return_value
        )
        # The response surfaces the id used, without a stray leading colon.
        assert result["mountingHole"]["footprintLibId"] == "MountingHole_3.2mm"

    def test_default_fpid_strips_trailing_zeros(self, cmds, fresh_pcbnew_mock):
        cmds.add_mounting_hole(
            {
                "position": {"x": 0, "y": 0, "unit": "mm"},
                "diameter": 3.0,  # would become "3.0mm" with %f, "3" with %g
            }
        )

        # %g formatting: 3.0 → "3"
        fresh_pcbnew_mock.LIB_ID.assert_called_once_with("", "MountingHole_3mm")

    def test_explicit_fpid_override_keeps_the_library_link(
        self, cmds, fresh_pcbnew_mock
    ):
        # A caller naming a library part explicitly gets that link verbatim --
        # it is then their job to make the geometry match.
        cmds.add_mounting_hole(
            {
                "position": {"x": 50, "y": 50, "unit": "mm"},
                "diameter": 3.2,
                "footprintLibId": "MountingHole:MountingHole_3.2mm_M3",
            }
        )

        fresh_pcbnew_mock.LIB_ID.assert_called_once_with("MountingHole", "MountingHole_3.2mm_M3")

    def test_explicit_fpid_without_colon_is_board_local(self, cmds, fresh_pcbnew_mock):
        cmds.add_mounting_hole(
            {
                "position": {"x": 0, "y": 0, "unit": "mm"},
                "diameter": 2.5,
                "footprintLibId": "MyCustomHole",
            }
        )

        # No colon means no library was named, so none is claimed. Silently
        # filing it under "MountingHole" (the old behaviour) invented a link
        # the caller never asked for and could not satisfy.
        fresh_pcbnew_mock.LIB_ID.assert_called_once_with("", "MyCustomHole")


# ---------------------------------------------------------------------------
# Bug #2: NPTH pad layers
# ---------------------------------------------------------------------------


class TestNpthPadLayers:
    def test_npth_pad_layers_are_mask_only(self, cmds, fresh_pcbnew_mock):
        cmds.add_mounting_hole(
            {
                "position": {"x": 117, "y": 84.5, "unit": "mm"},
                "diameter": 3.2,
                "padDiameter": 3.5,
                "plated": False,
            }
        )

        pad = _captured_pad(fresh_pcbnew_mock)

        # The pad must have been set to NPTH attr
        pad.SetAttribute.assert_called_once_with("NPTH")

        # SetLayerSet was called exactly once with an LSET that has
        # F_Mask and B_Mask added — and nothing on Cu layers.
        pad.SetLayerSet.assert_called_once()
        lset_arg = pad.SetLayerSet.call_args.args[0]

        added_layers = [c.args[0] for c in lset_arg.AddLayer.call_args_list]
        assert "F.Mask" in added_layers
        assert "B.Mask" in added_layers
        assert all(
            "Cu" not in str(layer) for layer in added_layers
        ), f"NPTH pad must not include any Cu layers, got: {added_layers}"

    def test_npth_is_default(self, cmds, fresh_pcbnew_mock):
        # Omit `plated` entirely; default must be NPTH.
        cmds.add_mounting_hole(
            {
                "position": {"x": 0, "y": 0, "unit": "mm"},
                "diameter": 3.2,
            }
        )

        pad = _captured_pad(fresh_pcbnew_mock)
        pad.SetAttribute.assert_called_once_with("NPTH")
        pad.SetLayerSet.assert_called_once()

    def test_pth_keeps_default_layers(self, cmds, fresh_pcbnew_mock):
        cmds.add_mounting_hole(
            {
                "position": {"x": 0, "y": 0, "unit": "mm"},
                "diameter": 3.2,
                "padDiameter": 3.5,
                "plated": True,
            }
        )

        pad = _captured_pad(fresh_pcbnew_mock)
        pad.SetAttribute.assert_called_once_with("PTH")

        # For PTH, the default LSET (*.Cu + *.Mask) is correct, so we must
        # NOT override it via SetLayerSet.
        pad.SetLayerSet.assert_not_called()


# ---------------------------------------------------------------------------
# Bug #3: NPTH mask aperture wider than the hole
# ---------------------------------------------------------------------------


class TestNpthMaskAperture:
    def test_npth_default_pad_is_exactly_the_drill(self, cmds, fresh_pcbnew_mock):
        result = cmds.add_mounting_hole(
            {
                "position": {"x": 0, "y": 0, "unit": "mm"},
                "diameter": 2.7,
            }
        )

        pad = _captured_pad(fresh_pcbnew_mock)
        # No +1mm: the pad *is* the mask aperture on an NPTH, so a wider pad
        # is bare laminate around the hole, not copper.
        pad.SetSize.assert_called_once_with(fresh_pcbnew_mock.VECTOR2I(2700000, 2700000))
        pad.SetDrillSize.assert_called_once_with(
            fresh_pcbnew_mock.VECTOR2I(2700000, 2700000)
        )
        assert result["mountingHole"]["padDiameter"] == 2.7

    def test_pth_default_pad_keeps_its_annular_ring(self, cmds, fresh_pcbnew_mock):
        result = cmds.add_mounting_hole(
            {
                "position": {"x": 0, "y": 0, "unit": "mm"},
                "diameter": 2.7,
                "plated": True,
            }
        )

        pad = _captured_pad(fresh_pcbnew_mock)
        # A plated hole does want copper around it, so the +1mm default stands.
        pad.SetSize.assert_called_once_with(fresh_pcbnew_mock.VECTOR2I(3700000, 3700000))
        pad.SetDrillSize.assert_called_once_with(
            fresh_pcbnew_mock.VECTOR2I(2700000, 2700000)
        )
        assert result["mountingHole"]["padDiameter"] == 3.7

    def test_explicit_pad_diameter_wins_over_the_default(
        self, cmds, fresh_pcbnew_mock
    ):
        result = cmds.add_mounting_hole(
            {
                "position": {"x": 0, "y": 0, "unit": "mm"},
                "diameter": 2.7,
                "padDiameter": 4.0,
                "plated": True,
            }
        )

        pad = _captured_pad(fresh_pcbnew_mock)
        pad.SetSize.assert_called_once_with(fresh_pcbnew_mock.VECTOR2I(4000000, 4000000))
        assert result["mountingHole"]["padDiameter"] == 4.0


# ---------------------------------------------------------------------------
# Bug #4: no courtyard, and hardware that claims to be a component
# ---------------------------------------------------------------------------


class TestScrewHeadKeepOut:
    def test_excluded_from_bom_and_pos_files(self, cmds, fresh_pcbnew_mock):
        cmds.add_mounting_hole(
            {
                "position": {"x": 0, "y": 0, "unit": "mm"},
                "diameter": 2.7,
            }
        )

        module = _captured_module(fresh_pcbnew_mock)
        module.SetAttributes.assert_called_once_with(
            fresh_pcbnew_mock.FP_EXCLUDE_FROM_POS_FILES
            | fresh_pcbnew_mock.FP_EXCLUDE_FROM_BOM
        )

    def test_carries_the_hole_and_courtyard_circles(self, cmds, fresh_pcbnew_mock):
        cmds.add_mounting_hole(
            {
                "position": {"x": 0, "y": 0, "unit": "mm"},
                "diameter": 2.7,
            }
        )

        # One circle per layer, both centred on the hole.
        assert fresh_pcbnew_mock.PCB_SHAPE.call_count == 2
        shape = fresh_pcbnew_mock.PCB_SHAPE.return_value
        assert shape.SetShape.call_count == 2
        shape.SetShape.assert_called_with("circle")
        assert shape.SetFilled.call_count == 2
        shape.SetFilled.assert_called_with(False)
        shape.SetStart.assert_called_with(fresh_pcbnew_mock.VECTOR2I(0, 0))

        # Cmts.User marks the hole itself; F.CrtYd marks the screw head.
        # Without the courtyard DRC skips the footprint entirely, which is how
        # parts ended up underneath a screw head with nothing reported.
        shape.SetLayer.assert_any_call("Cmts.User")
        shape.SetLayer.assert_any_call("F.CrtYd")
        shape.SetEnd.assert_any_call(fresh_pcbnew_mock.VECTOR2I(2700000, 0))
        shape.SetEnd.assert_any_call(fresh_pcbnew_mock.VECTOR2I(2950000, 0))
        shape.SetWidth.assert_any_call(150000)
        shape.SetWidth.assert_any_call(50000)

        module = _captured_module(fresh_pcbnew_mock)
        assert module.Add.call_count == 3  # the pad plus the two circles

    @pytest.mark.parametrize(
        "diameter, cmts_radius_mm, courtyard_radius_mm",
        [
            # The published footprints, read off MountingHole.pretty.
            (2.1, 2.1, 2.35),
            (2.5, 2.5, 2.75),
            (2.7, 2.7, 2.95),
        ],
    )
    def test_circle_radii_match_the_published_footprints(
        self, cmds, fresh_pcbnew_mock, diameter, cmts_radius_mm, courtyard_radius_mm
    ):
        """
        Cmts.User is the drill *diameter*, and the courtyard clears it by 0.25.

        Both are taken from the library at each size rather than computed from
        a "sensible-looking" formula: 2.5mm is the counter-example that catches
        a radius-based guess, since drill/2 + 1.3 would give 2.55 where the
        library has 2.75.
        """
        cmds.add_mounting_hole(
            {
                "position": {"x": 0, "y": 0, "unit": "mm"},
                "diameter": diameter,
            }
        )

        shape = fresh_pcbnew_mock.PCB_SHAPE.return_value
        shape.SetEnd.assert_any_call(
            fresh_pcbnew_mock.VECTOR2I(int(cmts_radius_mm * 1000000), 0)
        )
        shape.SetEnd.assert_any_call(
            fresh_pcbnew_mock.VECTOR2I(int(courtyard_radius_mm * 1000000), 0)
        )

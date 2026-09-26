---
name: add-fiducials
description: Add standard SMT fiducial / MARK points (0.5-1.0 mm copper, 2.0 mm mask aperture, no drill) to a KiCad PCB — site selection with a validated clearance scanner, footprint creation via the pcbnew Python API when the Fiducial library is unavailable, and a DRC self-check that reports the final coordinates. Use when asked to add MARK点 / 基准点 / fiducials for SMT assembly, panel alignment, or optical positioning.
---

# Adding SMT fiducials (MARK points) to a KiCad PCB

## What the user normally asks for

Place 3 top-layer fiducials, L-shaped / non-collinear, ≥5 mm from the board edge,
each with a clear ring around it, refs MK1/MK2/MK3, self-checked with DRC and
reported as a coordinate list.

## The requirement to aim for, and the one to actually verify

| Item | Typical ask | Reality check |
|---|---|---|
| Copper pad | 1.0 mm diameter | exact, trivial |
| Mask aperture | 2.0 mm diameter | `solder_mask_margin 0.5` |
| Drill | none | `PAD_ATTRIB_SMD`, size 0 |
| Edge margin | ≥5 mm | check `min(x-x0, x1-x, y-y0, y1-y)` |
| Clear ring | 3 mm, free of tracks/vias/silk/components | **often impossible — measure first** |

The 3 mm ring is the part that fails on dense boards. **Measure before promising.**
The industry-standard ring is `mask opening radius + 1 mm` (≈2 mm for a 1/2 mm
fiducial); 3 mm is stricter than most fabs require. Report the achieved number and
the board's hard ceiling rather than silently placing marks that violate the ask.

## Step 1 — measure the board before choosing anything

Do not eyeball the render. Write a scanner that, for a grid of candidate points,
computes the distance to the nearest obstacle of each class **on the side the
fiducial will sit on**:

- **Top-side fiducial** → F.Cu tracks and vias, F.SilkS (drawings + footprint
  silk *and reference text*), F.Mask apertures (pads, F.Mask drawings), footprint
  bodies. **B.Cu is invisible from above — never include it.** Including B.Cu is
  the single most common way to wrongly conclude a spot is unusable.
- **Bottom-side fiducial** → the B.* equivalents.

Use a spatial hash (4 mm cells) — a naive O(points × primitives) scan over a
220-footprint board times out. Distance to a segment for tracks, point-to-box for
everything else. Report, per candidate, the classes separately
(`F.Cu / silk / aperture`) so you can see *what* limits the spot.

Then answer, with numbers:
1. What is the **maximum achievable ring** anywhere on the board?
2. How many grid points reach the requested ring? Where are they?
3. Is a **non-collinear** triple actually available? Collinear fiducials give
   X/Y/rotation but no skew or Y-scale — three marks in one horizontal band are
   barely better than two.

Respect the mounting holes. A 6 mm mounting-hole pad eats a board corner
completely; a 5 mm edge margin plus a 3 mm ring often cannot coexist with it.

## Step 2 — place them

Prefer the official library when it resolves:
`Fiducial:Fiducial_1mm_Mask2mm`. When it does not, build the footprint directly —
do not block on the library.

```python
import pcbnew
IU = 1000000.0
def V(x, y): return pcbnew.VECTOR2I(int(round(x*IU)), int(round(y*IU)))

fp = pcbnew.FOOTPRINT(board)
fp.SetReference(ref); fp.SetValue("Fiducial_1mm_Mask2mm")
fp.SetPosition(V(x, y)); fp.SetLayer(pcbnew.F_Cu)
fp.SetAttributes(pcbnew.FP_EXCLUDE_FROM_BOM | pcbnew.FP_EXCLUDE_FROM_POS_FILES)

ls = pcbnew.LSET(); ls.AddLayer(pcbnew.F_Cu); ls.AddLayer(pcbnew.F_Mask)
pad = pcbnew.PAD(fp)
pad.SetNumber("")
pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
pad.SetShape(pcbnew.PAD_SHAPE_CIRCLE)
pad.SetSize(pcbnew.VECTOR2I(int(1.0*IU), int(1.0*IU)))
pad.SetDrillSize(pcbnew.VECTOR2I(0, 0))
pad.SetLayerSet(ls)
pad.SetLocalSolderMaskMargin(int(0.5*IU))   # 1.0 + 2*0.5 = 2.0 mm aperture
pad.SetPosition(V(x, y)); fp.Add(pad)

# keep the refdes off F.SilkS or it will collide; F.Fab is the safe home
rf = fp.Reference(); rf.SetLayer(pcbnew.F_Fab); rf.SetPosition(V(x, y-1.4))
rf.SetTextSize(pcbnew.VECTOR2I(int(0.6*IU), int(0.6*IU)))
fp.Value().SetVisible(False)
board.Add(fp)
board.Save(path)
```

API gotchas hit in practice:
- `FOOTPRINT` has **no `SetDescription`** — it is `SetLibDescription`. Keywords are
  `SetLibKeywords`. Easiest is to omit both.
- `LSET` has no `GetLayerName`; use `board.GetLayerName(i)` to print layers.
- A no-net pad is fine — it is not an "unconnected" DRC error.
- Exclude fiducials from BOM and position files; they are landmarks, not parts.

## Step 3 — self-check and report

Run DRC **in the project directory**, never from a temp copy — a temp copy loses
`fp-lib-table` and invents `lib_footprint_issues` that swamp the diff.

```bash
kicad-cli pcb drc --format json --output drc.json --severity-all board.kicad_pcb
```

Compare the violation **count and type histogram** against a pre-change baseline,
and separately assert that **zero violations name MK1/MK2/MK3**. Both matter: the
count can match while a violation moved.

Also verify the written file, not just the in-memory object:

```
(pad "" smd circle (at 0 0) (size 1 1)
   (layers "F.Cu" "F.Mask") (solder_mask_margin 0.5))
(attr exclude_from_pos_files exclude_from_bom)
```

Visual confirmation: export **F.Mask alone**. The fiducial apertures appear as
clean circles and their measured pixel diameter should equal the intended
aperture (2.0 mm). A mixed F.Cu+F.Mask view is ambiguous — vias and pads look the
same. `cairosvg` is often unusable (missing `libcairo-2.dll`); the MCP
`get_board_2d_view` tool rasterizes server-side, then crop with PIL.

Finally report, per mark: centre coordinates, achieved ring radius broken down by
class, edge margin, distance to J1/connectors and to each mounting screw — and
state plainly any requirement that could not be met, with the measured ceiling
that proves it.

## Deliverable checklist

- [ ] 3 footprints MK1/MK2/MK3, SMD circle, 1.0 mm copper, 2.0 mm mask, no drill
- [ ] ≥5 mm from board edge; ≥2 mm (or the requested ring) clear
- [ ] Confirm against J1, mounting screws, and the enclosure keep-out
- [ ] Bottom-layer marks only if the bottom layer actually carries SMT parts
- [ ] Copper pour / keepout around each mark if the board has pours
- [ ] DRC unchanged vs baseline and nothing naming the new refs
- [ ] Final coordinate list reported to the user

"""Where a symbol's pins land on a sheet, and what is sitting on them.

One definition, because the sign of the rotation is not guessable and getting it
wrong is silent: J8 and J10 are placed at 90 degrees, and the wrong sign moved
all forty of their pins ten millimetres away from their labels, which reads
exactly like two connectors that were never wired up.

Library pins are Y-up, a sheet is Y-down, so even the unrotated case is a
reflection:
    rot   0 : (sx + lx, sy - ly)
    rot  90 : (sx - ly, sy - lx)
    rot 180 : (sx - lx, sy + ly)
    rot 270 : (sx + ly, sy + lx)
"""
import math
import re

import _sexp


def sub_block(text, start):
    """Span of the balanced form beginning at `start`."""
    depth = 0
    in_str = esc = False
    j = start
    while j < len(text):
        c = text[j]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
        elif c == '"':
            in_str = True
        elif c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return text[start:j + 1]
        j += 1
    raise ValueError("unbalanced form at %d" % start)


def place(sx, sy, angle, mirror, lx, ly):
    """Library point -> sheet point for one symbol instance."""
    if mirror == "y":
        lx = -lx
    elif mirror == "x":
        ly = -ly
    a = math.radians(angle % 360.0)
    cos, sin = math.cos(a), math.sin(a)
    return (sx + lx * cos - ly * sin, sy - lx * sin - ly * cos)


def lib_block(text, lib_id):
    """The definition of `lib_id` inside lib_symbols, or None."""
    for head, i0, i1 in _sexp.children(text):
        if head != "lib_symbols":
            continue
        libs = text[i0:i1]
        at = libs.find('(symbol "%s"' % lib_id)
        return sub_block(libs, at) if at >= 0 else None
    return None


def lib_pins(text, lib_id):
    """{number: (local_x, local_y, name)} in the library's own Y-up frame."""
    block = lib_block(text, lib_id)
    if block is None:
        return {}
    out = {}
    i = 0
    while True:
        i = block.find("(pin ", i)
        if i < 0:
            break
        form = sub_block(block, i)
        m = re.search(r"\(at ([-\d.]+) ([-\d.]+) ([-\d.]+)\)", form)
        n = re.search(r'\(number "([^"]+)"', form)
        nm = re.search(r'\(name "([^"]*)"', form)
        if m and n:
            out[n.group(1)] = (float(m.group(1)), float(m.group(2)),
                               nm.group(1) if nm else "")
        i += len(form)
    return out


def symbols(text):
    """Every placed symbol: ref, lib_id, value, placement, mirror, span."""
    out = []
    for head, i0, i1 in _sexp.children(text):
        if head != "symbol":
            continue
        b = text[i0:i1]
        lib = re.search(r'\(lib_id "([^"]+)"\)', b)
        ref = re.search(r'\(property "Reference" "([^"]+)"', b)
        if not lib or not ref:
            continue
        val = re.search(r'\(property "Value" "([^"]*)"', b)
        mir = re.search(r"\(mirror ([xy])\)", b)
        out.append({
            "ref": ref.group(1),
            "lib_id": lib.group(1),
            "value": val.group(1) if val else "",
            "at": _sexp.find_at(b),
            "mirror": mir.group(1) if mir else None,
            "i0": i0, "i1": i1,
        })
    return out


def pin_points(text, sym):
    """[(number, sheet_x, sheet_y, name)] for one symbol instance."""
    x, y, a = sym["at"]
    pins = lib_pins(text, sym["lib_id"])
    return [(n, ) + place(x, y, a, sym["mirror"], lx, ly) + (nm, )
            for n, (lx, ly, nm) in sorted(
                pins.items(), key=lambda kv: int(kv[0]) if kv[0].isdigit() else 0)]


def labels(text):
    """[(name, x, y, angle, i0, i1)] for every top-level label."""
    out = []
    for head, i0, i1 in _sexp.children(text):
        if head != "label":
            continue
        at = _sexp.find_at(text[i0:i1])
        if at:
            out.append((text[i0:i1].split('"')[1], at[0], at[1], at[2], i0, i1))
    return out

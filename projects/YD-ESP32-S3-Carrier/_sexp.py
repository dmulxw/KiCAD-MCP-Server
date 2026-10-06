"""Split a .kicad_sch into its top-level children, losslessly.

Every edit to this sheet is "rename a label", "delete an instance", "insert a
symbol", and all of those are operations on one top-level child of the root
(kicad_sch ...) form.  Doing them by regular expression over 34k lines means
guessing where a block ends; doing them by bracket depth means knowing.  The
child spans this returns are byte ranges in the original text, so a caller can
splice new children in and leave every untouched byte untouched -- which
matters when the file is 594 KB and the alternative is a writer that
re-serialises the whole thing.

  python _sexp.py PATH                 list the children with their head token
  python _sexp.py PATH --head symbol   list only children starting with symbol
"""
import sys


def children(text, start=0):
    """[(head, i0, i1)] for each child of the outermost form at `start`.

    i0 is the index of the child's '(' and i1 is one past its matching ')'.
    A head is the token after the '(', e.g. 'label' or 'symbol'.
    """
    i = start
    n = len(text)
    while i < n and text[i] != "(":
        i += 1
    if i >= n:
        return []
    depth = 0
    out = []
    in_str = False
    esc = False
    child_start = None
    child_head = None
    while i < n:
        c = text[i]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
            i += 1
            continue
        if c == '"':
            in_str = True
            i += 1
            continue
        if c == "(":
            depth += 1
            if depth == 2:
                child_start = i
                j = i + 1
                while j < n and text[j] in " \t\r\n":
                    j += 1
                k = j
                while k < n and (text[k].isalnum() or text[k] in "_+-."):
                    k += 1
                child_head = text[j:k]
            i += 1
            continue
        if c == ")":
            depth -= 1
            if depth == 1 and child_start is not None:
                out.append((child_head, child_start, i + 1))
                child_start = None
            elif depth == 0:
                break
            i += 1
            continue
        i += 1
    return out


def head_of(block):
    i = block.find("(") + 1
    while i < len(block) and block[i] in " \t\r\n":
        i += 1
    j = i
    while j < len(block) and (block[j].isalnum() or block[j] in "_+-."):
        j += 1
    return block[i:j]


def find_at(block):
    """(x, y, angle) of a top-level item's placement, or None."""
    depth = 0
    in_str = False
    esc = False
    i = 0
    n = len(block)
    while i < n:
        c = block[i]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
            i += 1
            continue
        if c == '"':
            in_str = True
            i += 1
            continue
        if c == "(":
            depth += 1
            if depth == 2 and block.startswith("at", i + 1):
                j = i + 4
                nums = []
                while len(nums) < 3 and j < n:
                    while j < n and block[j] in " \t\r\n":
                        j += 1
                    k = j
                    while k < n and block[k] not in " \t\r\n()":
                        k += 1
                    tok = block[j:k]
                    if not tok:
                        break
                    try:
                        nums.append(float(tok))
                    except ValueError:
                        break
                    j = k
                return tuple(nums) if nums else None
            i += 1
            continue
        if c == ")":
            depth -= 1
            i += 1
            continue
        i += 1
    return None


def load(path):
    with open(path, encoding="utf-8", newline="") as f:
        return f.read()


def save(path, text):
    """Write via a sibling temp file, then rename over the target.

    A half-written schematic is indistinguishable from a corrupt one and there
    are 34k lines of them; the rename is the only step that can be interrupted.
    """
    import os
    tmp = path + ".tmp-write"
    with open(tmp, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    os.replace(tmp, path)


if __name__ == "__main__":
    p = sys.argv[1]
    want = None
    if "--head" in sys.argv:
        want = sys.argv[sys.argv.index("--head") + 1]
    t = load(p)
    ch = children(t)
    print("%s: %d byte(s), %d top-level child(ren)" % (p, len(t), len(ch)))
    seen = {}
    for head, i0, i1 in ch:
        seen[head] = seen.get(head, 0) + 1
    for k in sorted(seen):
        print("   %-18s %d" % (k, seen[k]))
    if want:
        print()
        for head, i0, i1 in ch:
            if head == want:
                print("--- %d..%d  %s" % (i0, i1, find_at(t[i0:i1])))

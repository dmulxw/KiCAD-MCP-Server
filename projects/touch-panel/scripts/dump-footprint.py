#!/usr/bin/env python3
"""Print one footprint block from a .kicad_pcb, verbatim.

    python projects/touch-panel/scripts/dump-footprint.py <board> <ref-or-libid>
"""

import sys


def find_blocks(text, needle):
    """Yield each balanced `(footprint ...)` block whose header contains needle."""
    marker = '(footprint "'
    start = 0
    while True:
        i = text.find(marker, start)
        if i < 0:
            return
        depth = 0
        j = i
        while j < len(text):
            ch = text[j]
            if ch == '"':
                j += 1
                while j < len(text) and text[j] != '"':
                    j += 2 if text[j] == "\\" else 1
            elif ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0:
                    j += 1
                    break
            j += 1
        block = text[i:j]
        if needle in block:
            yield block
        start = j


def main():
    if len(sys.argv) < 3:
        raise SystemExit(__doc__)
    board, needle = sys.argv[1], sys.argv[2]
    limit = int(sys.argv[3]) if len(sys.argv) > 3 else 1
    text = open(board, encoding="utf-8").read()
    n = 0
    for block in find_blocks(text, needle):
        n += 1
        if n > 1:
            print("\n/* --- next match --- */\n")
        print(block)
        if n >= limit:
            break
    if not n:
        raise SystemExit(f"no footprint matching {needle!r}")


if __name__ == "__main__":
    main()

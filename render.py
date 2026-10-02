#!/usr/bin/env python3
import sys
import re
import os
import subprocess
import tempfile
import html as html_mod

WIDTH = 1920
HEIGHT = 1080
BG = "#202020"
FG = "#cdd6f4"
BLUE = "#89b4fa"
CYAN = "#89dceb"
GREEN = "#a6e3a1"
DIM = "#6c7086"
FONT = "Monocraft Nerd Font"
PAD_X = 80
PAD_Y = 70
LINE_SCALE = 1.65

SIZES = {"h1": 38, "h2": 30, "h3": 23, "body": 18}

# Monospace: char width ≈ font_size * 0.601
CHAR_RATIO = 0.601


def max_chars(font_size, available_px):
    return int(available_px / (font_size * CHAR_RATIO))


def word_wrap(text, font_size, avail_px):
    limit = max_chars(font_size, avail_px)
    if not text.strip():
        return [""]
    if len(text) <= limit:
        return [text]
    lines = []
    while len(text) > limit:
        break_at = text.rfind(" ", 0, limit)
        if break_at <= 0:
            break_at = limit
        lines.append(text[:break_at])
        text = text[break_at + 1:]
    if text:
        lines.append(text)
    return lines or [""]


def parse_inline(text):
    """Return list of (segment_text, bold, color_override|None)."""
    # Handle markdown links [label](url) → render label in blue
    # Handle **bold**, *italic* (render italic as dim), `code` (green)
    token_re = re.compile(
        r'\[([^\]]+)\]\([^)]+\)'   # [label](url)
        r'|\*\*(.+?)\*\*'          # **bold**
        r'|\*(.+?)\*'              # *italic*
        r'|`([^`]+)`'              # `code`
        r'|([^*`\[]+)'             # plain text
        r'|(\[)'                   # bare [ not part of a link
    )
    spans = []
    for m in token_re.finditer(text):
        link_label, bold_t, italic_t, code_t, plain, bare = m.groups()
        if link_label is not None:
            spans.append((link_label, False, BLUE))
        elif bare is not None:
            spans.append((bare, False, None))
        elif bold_t is not None:
            spans.append((bold_t, True, None))
        elif italic_t is not None:
            # Italic may wrap links etc.; parse inside, dim whatever has no color
            spans.extend((t, b, c or DIM) for t, b, c in parse_inline(italic_t))
        elif code_t is not None:
            spans.append((code_t, False, GREEN))
        elif plain is not None:
            spans.append((plain, False, None))
    return spans or [(text, False, None)]


def make_tspan(text, bold=False, color=None):
    attrs = []
    if bold:
        attrs.append('font-weight="bold"')
    if color:
        attrs.append(f'fill="{color}"')
    # Renderer trims plain spaces at tspan edges; keep them as NBSP
    core = text.strip(" ")
    lead = len(text) - len(text.lstrip(" "))
    trail = len(text) - len(text.rstrip(" "))
    body = " " * lead + html_mod.escape(core) + " " * trail
    if attrs:
        return f'<tspan {" ".join(attrs)}>{body}</tspan>'
    return f'<tspan>{body}</tspan>'


def text_el(x, y, fs, color, bold, content_tspans, extra=""):
    return (
        f'  <text x="{x}" y="{round(y)}" font-size="{fs}" fill="{color}" '
        f'font-family="{FONT}, monospace"'
        + (' font-weight="bold"' if bold else "")
        + extra
        + f">{content_tspans}</text>"
    )


def render_line(out, raw, x, y, fs, color=None, bold=False):
    color = color or FG
    spans = parse_inline(raw)
    tspans = "".join(make_tspan(t, b or bold, c or (color if color != FG else None)) for t, b, c in spans)
    out.append(text_el(x, y, fs, color, bold, tspans))


def layout(md_text, columns):
    """Render md into SVG elements. Returns (elements, overflowed).

    The leading H1 is a full-width header. Content flows below it; with
    columns=2, overflow restarts at the top of the right half, under the header.
    """
    out = []
    y = float(PAD_Y + SIZES["h1"])  # baseline of first line
    lines = md_text.splitlines()

    if lines and lines[0].startswith("# "):
        fs = SIZES["h1"]
        for wl in word_wrap(lines[0][2:], fs, WIDTH - 2 * PAD_X):
            render_line(out, wl, PAD_X, y, fs, BLUE, bold=True)
            y += fs * LINE_SCALE
        lines = lines[1:]
        last_fs = fs
    else:
        last_fs = None  # font size of previously rendered element (None = start of page)

    top_y = y
    col = 0
    col_w = WIDTH - 2 * PAD_X if columns == 1 else WIDTH // 2 - PAD_X
    x0 = PAD_X
    avail = col_w

    def fit(n_lines, fs):
        """Ensure n_lines of size fs fit in the current column, moving to the next if needed."""
        nonlocal y, col, x0
        if y + (n_lines - 1) * fs * LINE_SCALE <= HEIGHT - PAD_Y:
            return True
        if col + 1 >= columns:
            return False
        col += 1
        x0 = WIDTH // 2
        y = top_y
        return True

    def at_col_top():
        return y == top_y

    for raw in lines:
        heading = re.match(r"^(#{1,4}) (.*)", raw)

        # Headings
        if heading:
            level = len(heading.group(1))
            fs = {1: SIZES["h1"], 2: SIZES["h2"], 3: SIZES["h3"], 4: SIZES["body"] + 2}[level]
            color = BLUE if level <= 2 else CYAN
            wrapped = word_wrap(heading.group(2), fs, avail)
            if last_fs is not None and fs > last_fs and not at_col_top():
                y += (fs - last_fs) * LINE_SCALE
            if not fit(len(wrapped), fs):
                return out, True
            for wl in wrapped:
                render_line(out, wl, x0, y, fs, color, bold=level <= 3)
                y += fs * LINE_SCALE
            last_fs = fs

        # Horizontal rule
        elif re.match(r"^[-*_]{3,}\s*$", raw):
            if not fit(1, SIZES["body"]):
                return out, True
            ry = round(y - SIZES["body"] / 2)
            out.append(f'  <line x1="{x0}" y1="{ry}" x2="{x0 + avail}" y2="{ry}" stroke="{DIM}" stroke-width="1"/>')
            y += SIZES["body"] * LINE_SCALE * 0.6

        # Checkbox done: - [x]
        elif re.match(r"^- \[[xX]\] ", raw):
            fs = SIZES["body"]
            wrapped = word_wrap(raw[6:], fs, avail - 30)
            if not fit(len(wrapped), fs):
                return out, True
            out.append(
                f'  <text x="{x0 + 10}" y="{round(y)}" font-size="{fs}" fill="{GREEN}" font-family="{FONT}, monospace">☑</text>'
            )
            for wl in wrapped:
                escaped = html_mod.escape(wl)
                out.append(
                    f'  <text x="{x0 + 30}" y="{round(y)}" font-size="{fs}" fill="{DIM}" '
                    f'font-family="{FONT}, monospace" text-decoration="line-through"><tspan>{escaped}</tspan></text>'
                )
                y += fs * LINE_SCALE
            last_fs = fs

        # Checkbox open: - [ ]
        elif re.match(r"^- \[ \] ", raw):
            fs = SIZES["body"]
            wrapped = word_wrap(raw[6:], fs, avail - 30)
            if not fit(len(wrapped), fs):
                return out, True
            out.append(
                f'  <text x="{x0 + 10}" y="{round(y)}" font-size="{fs}" fill="{FG}" font-family="{FONT}, monospace">☐</text>'
            )
            for wl in wrapped:
                render_line(out, wl, x0 + 30, y, fs)
                y += fs * LINE_SCALE
            last_fs = fs

        # List item
        elif raw.startswith("- ") or raw.startswith("* "):
            fs = SIZES["body"]
            wrapped = word_wrap(raw[2:], fs, avail - 28)
            if not fit(len(wrapped), fs):
                return out, True
            out.append(
                f'  <text x="{x0 + 8}" y="{round(y)}" font-size="{fs}" fill="{BLUE}" font-family="{FONT}, monospace">•</text>'
            )
            for wl in wrapped:
                render_line(out, wl, x0 + 28, y, fs)
                y += fs * LINE_SCALE
            last_fs = fs

        # Blockquote
        elif raw.startswith("> "):
            fs = SIZES["body"]
            wrapped = word_wrap(raw[2:], fs, avail - 22)
            if not fit(len(wrapped), fs):
                return out, True
            bar_top = round(y - fs)
            bar_h = round(fs * LINE_SCALE)
            out.append(f'  <rect x="{x0}" y="{bar_top}" width="3" height="{bar_h}" fill="{BLUE}"/>')
            for wl in wrapped:
                render_line(out, wl, x0 + 18, y, fs, DIM)
                y += fs * LINE_SCALE
            last_fs = fs

        # Blank line — don't update last_fs so heading sizing ignores blank gaps
        elif not raw.strip():
            if not at_col_top():
                y += SIZES["body"] * LINE_SCALE * 0.45

        # Normal paragraph
        else:
            fs = SIZES["body"]
            wrapped = word_wrap(raw, fs, avail)
            if not fit(len(wrapped), fs):
                return out, True
            for wl in wrapped:
                render_line(out, wl, x0, y, fs)
                y += fs * LINE_SCALE
            last_fs = fs

    return out, False


def md_to_svg(md_text):
    body, overflowed = layout(md_text, 1)
    if overflowed:
        body, _ = layout(md_text, 2)
    return "\n".join([
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg width="{WIDTH}" height="{HEIGHT}">',
        f'  <rect width="{WIDTH}" height="{HEIGHT}" fill="{BG}"/>',
        *body,
        "</svg>",
    ])


def main():
    if len(sys.argv) < 3:
        print(f"Usage: {sys.argv[0]} <input.md> <output.png>", file=sys.stderr)
        sys.exit(1)

    md_file, output_png = sys.argv[1], sys.argv[2]

    with open(md_file) as f:
        md_text = f.read()

    svg = md_to_svg(md_text)

    with tempfile.NamedTemporaryFile(mode="w", suffix=".svg", delete=False) as tf:
        tf.write(svg)
        svg_path = tf.name

    try:
        r = subprocess.run(["magick", svg_path, output_png], capture_output=True, text=True)
        if r.returncode != 0:
            print(f"magick error: {r.stderr}", file=sys.stderr)
            sys.exit(1)
    finally:
        os.unlink(svg_path)


if __name__ == "__main__":
    main()

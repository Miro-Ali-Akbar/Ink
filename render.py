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
            spans.append((italic_t, False, DIM))
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
    stripped = text.lstrip()
    nbsps = " " * (len(text) - len(stripped))
    body = nbsps + html_mod.escape(stripped)
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


def md_to_svg(md_text):
    out = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg width="{WIDTH}" height="{HEIGHT}">',
        f'  <rect width="{WIDTH}" height="{HEIGHT}" fill="{BG}"/>',
    ]

    y = float(PAD_Y + SIZES["h1"])  # start y is baseline of first line
    avail = WIDTH - 2 * PAD_X
    last_fs = None  # font size of previously rendered element (None = start of page)

    for raw in md_text.splitlines():
        if y > HEIGHT - PAD_Y:
            break

        # H1
        if raw.startswith("# "):
            fs = SIZES["h1"]
            if last_fs is not None and fs > last_fs:
                y += (fs - last_fs) * LINE_SCALE
            for wl in word_wrap(raw[2:], fs, avail):
                render_line(out, wl, PAD_X, y, fs, BLUE, bold=True)
                y += fs * LINE_SCALE
            last_fs = fs

        # H2
        elif raw.startswith("## "):
            fs = SIZES["h2"]
            if last_fs is not None and fs > last_fs:
                y += (fs - last_fs) * LINE_SCALE
            for wl in word_wrap(raw[3:], fs, avail):
                render_line(out, wl, PAD_X, y, fs, BLUE, bold=True)
                y += fs * LINE_SCALE
            last_fs = fs

        # H3
        elif raw.startswith("### "):
            fs = SIZES["h3"]
            if last_fs is not None and fs > last_fs:
                y += (fs - last_fs) * LINE_SCALE
            for wl in word_wrap(raw[4:], fs, avail):
                render_line(out, wl, PAD_X, y, fs, CYAN, bold=True)
                y += fs * LINE_SCALE
            last_fs = fs

        # H4+
        elif raw.startswith("#### "):
            fs = SIZES["body"] + 2
            if last_fs is not None and fs > last_fs:
                y += (fs - last_fs) * LINE_SCALE
            for wl in word_wrap(raw[5:], fs, avail):
                render_line(out, wl, PAD_X, y, fs, CYAN)
                y += fs * LINE_SCALE
            last_fs = fs

        # Horizontal rule
        elif re.match(r"^[-*_]{3,}\s*$", raw):
            ry = round(y - SIZES["body"] / 2)
            out.append(f'  <line x1="{PAD_X}" y1="{ry}" x2="{WIDTH - PAD_X}" y2="{ry}" stroke="{DIM}" stroke-width="1"/>')
            y += SIZES["body"] * LINE_SCALE * 0.6

        # Checkbox done: - [x]
        elif re.match(r"^- \[[xX]\] ", raw):
            fs = SIZES["body"]
            text = raw[6:]
            out.append(
                f'  <text x="{PAD_X + 10}" y="{round(y)}" font-size="{fs}" fill="{GREEN}" font-family="{FONT}, monospace">☑</text>'
            )
            for wl in word_wrap(text, fs, avail - 30):
                escaped = html_mod.escape(wl)
                out.append(
                    f'  <text x="{PAD_X + 30}" y="{round(y)}" font-size="{fs}" fill="{DIM}" '
                    f'font-family="{FONT}, monospace" text-decoration="line-through"><tspan>{escaped}</tspan></text>'
                )
                y += fs * LINE_SCALE
            last_fs = fs

        # Checkbox open: - [ ]
        elif re.match(r"^- \[ \] ", raw):
            fs = SIZES["body"]
            text = raw[6:]
            out.append(
                f'  <text x="{PAD_X + 10}" y="{round(y)}" font-size="{fs}" fill="{FG}" font-family="{FONT}, monospace">☐</text>'
            )
            for wl in word_wrap(text, fs, avail - 30):
                render_line(out, wl, PAD_X + 30, y, fs)
                y += fs * LINE_SCALE
            last_fs = fs

        # List item
        elif raw.startswith("- ") or raw.startswith("* "):
            fs = SIZES["body"]
            text = raw[2:]
            out.append(
                f'  <text x="{PAD_X + 8}" y="{round(y)}" font-size="{fs}" fill="{BLUE}" font-family="{FONT}, monospace">•</text>'
            )
            for wl in word_wrap(text, fs, avail - 28):
                render_line(out, wl, PAD_X + 28, y, fs)
                y += fs * LINE_SCALE
            last_fs = fs

        # Blockquote
        elif raw.startswith("> "):
            fs = SIZES["body"]
            text = raw[2:]
            bar_top = round(y - fs)
            bar_h = round(fs * LINE_SCALE)
            out.append(f'  <rect x="{PAD_X}" y="{bar_top}" width="3" height="{bar_h}" fill="{BLUE}"/>')
            for wl in word_wrap(text, fs, avail - 22):
                render_line(out, wl, PAD_X + 18, y, fs, DIM)
                y += fs * LINE_SCALE
            last_fs = fs

        # Blank line — don't update last_fs so heading sizing ignores blank gaps
        elif not raw.strip():
            y += SIZES["body"] * LINE_SCALE * 0.45

        # Normal paragraph
        else:
            fs = SIZES["body"]
            for wl in word_wrap(raw, fs, avail):
                render_line(out, wl, PAD_X, y, fs)
                y += fs * LINE_SCALE
            last_fs = fs

    out.append("</svg>")
    return "\n".join(out)


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

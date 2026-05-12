#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"
LOGS_DIR="$SCRIPT_DIR/logs"
TODAY=$(date +%y-%m-%d)
TODAY_FULL=$(date +%Y-%m-%d)
TODAY_FILE="$LOGS_DIR/$TODAY.md"
EDITOR="${EDITOR:-nvim}"
OUTPUT_IMG="$SCRIPT_DIR/background.png"

mkdir -p "$LOGS_DIR"

if [ ! -f "$TODAY_FILE" ]; then
    PREV_FILE=$(ls -t "$LOGS_DIR"/*.md 2>/dev/null | grep -v "/$TODAY.md$" | head -1)

    if [ -n "$PREV_FILE" ]; then
        PREV_NAME=$(basename "$PREV_FILE")
        PREV_SHORT="${PREV_NAME%.md}"
        # Expand 2-digit year to 4-digit for the link label
        PREV_FULL="20${PREV_SHORT:0:2}-${PREV_SHORT:3:2}-${PREV_SHORT:6:2}"
        # Clone prev before modifying it so the build step works from clean content
        PREV_CLONE=$(mktemp)
        cp "$PREV_FILE" "$PREV_CLONE"

        # Append "continued on" to the previous file (2 lines below, no separator)
        if ! grep -q '^\*Continued on \[' "$PREV_FILE"; then
            printf '\n\n*Continued on [%s](%s)*\n' "$TODAY_FULL" "$TODAY.md" >> "$PREV_FILE"
        fi

        {
            printf '# Todo %s\n\n' "$TODAY_FULL"
            {
                if tail -4 "$PREV_CLONE" | grep -q '^\*Continued from \['; then
                    head -n -4 "$PREV_CLONE"
                else
                    cat "$PREV_CLONE"
                fi
            } | tail -n +3
            printf '\n---\n\n*Continued from [%s](%s)*\n\n' "$PREV_FULL" "$PREV_NAME"
        } > "$TODAY_FILE"

        rm "$PREV_CLONE"
    else
        printf '# Todo %s\n\n- \n' "$TODAY_FULL" > "$TODAY_FILE"
    fi
fi

"$EDITOR" "$TODAY_FILE"

(python3 "$SCRIPT_DIR/render.py" "$TODAY_FILE" "$OUTPUT_IMG" \
    && gsettings set org.gnome.desktop.background picture-uri     "file://$OUTPUT_IMG" \
    && gsettings set org.gnome.desktop.background picture-uri-dark "file://$OUTPUT_IMG" \
    && gsettings set org.gnome.desktop.background picture-options  "zoom") &
disown

#!/usr/bin/env bash
# One-time setup: installs local Playwright venv + macOS LaunchAgent
# for automatic monthly newsletter subscriber count updates.
#
# Run once from anywhere:
#   bash scripts/setup_auto_update.sh
#
# After setup, the script will run automatically on the 1st of every month
# at 9:00 AM. You can also run it manually at any time:
#   ~/.local/ritikasharma-site/venv/bin/python3 \
#     /path/to/personal-website/scripts/auto_update_newsletters.py

set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
VENV_DIR="$HOME/.local/ritikasharma-site/venv"
LI_AT_FILE="$HOME/.config/ritikasharma/linkedin_li_at"
PLIST="$HOME/Library/LaunchAgents/com.ritikasharma.newsletter.plist"
SCRIPT="$REPO_DIR/scripts/auto_update_newsletters.py"
LOG_DIR="$HOME/Library/Logs/ritikasharma"
PYTHON3=/Library/Frameworks/Python.framework/Versions/3.13/bin/python3

echo ""
echo "══════════════════════════════════════════════════════"
echo " Newsletter auto-updater setup"
echo "══════════════════════════════════════════════════════"
echo ""

# ── 1. Python venv ─────────────────────────────────────────────
echo "▶ Creating Python venv at $VENV_DIR…"
mkdir -p "$(dirname "$VENV_DIR")"
"$PYTHON3" -m venv "$VENV_DIR"
"$VENV_DIR/bin/pip" install --quiet --upgrade pip
"$VENV_DIR/bin/pip" install --quiet playwright
"$VENV_DIR/bin/playwright" install chromium
echo "  ✓ venv ready"

# ── 2. li_at cookie ────────────────────────────────────────────
mkdir -p "$(dirname "$LI_AT_FILE")"
chmod 700 "$(dirname "$LI_AT_FILE")"

if [[ -f "$LI_AT_FILE" && -s "$LI_AT_FILE" ]]; then
    echo "▶ li_at already saved at $LI_AT_FILE — skipping prompt."
else
    echo ""
    echo "▶ LinkedIn li_at cookie"
    echo "  Open Chrome → linkedin.com → F12 → Application → Cookies"
    echo "  → .linkedin.com → li_at → copy the Value field"
    echo ""
    read -rsp "  Paste your li_at value (hidden): " LI_AT_VALUE
    echo ""
    if [[ -z "$LI_AT_VALUE" ]]; then
        echo "  ⚠ No value entered. You can add it later:"
        echo "    echo 'YOUR_LI_AT' > $LI_AT_FILE && chmod 600 $LI_AT_FILE"
    else
        printf '%s' "$LI_AT_VALUE" > "$LI_AT_FILE"
        chmod 600 "$LI_AT_FILE"
        echo "  ✓ li_at saved (permissions: 600)"
    fi
fi

# ── 3. Log directory ───────────────────────────────────────────
mkdir -p "$LOG_DIR"

# ── 4. LaunchAgent plist ───────────────────────────────────────
echo "▶ Writing LaunchAgent plist to $PLIST…"
cat > "$PLIST" <<PLIST_EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.ritikasharma.newsletter</string>

  <key>ProgramArguments</key>
  <array>
    <string>${VENV_DIR}/bin/python3</string>
    <string>${SCRIPT}</string>
  </array>

  <!-- Run on the 1st of every month at 9:00 AM local time -->
  <key>StartCalendarInterval</key>
  <dict>
    <key>Day</key>
    <integer>1</integer>
    <key>Hour</key>
    <integer>9</integer>
    <key>Minute</key>
    <integer>0</integer>
  </dict>

  <key>WorkingDirectory</key>
  <string>${REPO_DIR}</string>

  <key>StandardOutPath</key>
  <string>${LOG_DIR}/newsletter-update.log</string>

  <key>StandardErrorPath</key>
  <string>${LOG_DIR}/newsletter-update-error.log</string>

  <!-- Run as soon as possible if the computer was off at trigger time -->
  <key>RunAtLoad</key>
  <false/>
</dict>
</plist>
PLIST_EOF

# ── 5. Load agent ──────────────────────────────────────────────
echo "▶ Loading LaunchAgent…"
# Unload first in case it was previously loaded (ignore error if not loaded)
launchctl unload "$PLIST" 2>/dev/null || true
launchctl load "$PLIST"
echo "  ✓ LaunchAgent loaded"

# ── 6. Quick sanity test ───────────────────────────────────────
echo ""
echo "▶ Running sanity check (Python + Playwright import)…"
"$VENV_DIR/bin/python3" - <<'PYEOF'
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    b.close()
print("  ✓ Playwright + Chromium working")
PYEOF

# ── Done ───────────────────────────────────────────────────────
echo ""
echo "══════════════════════════════════════════════════════"
echo " Setup complete!"
echo "══════════════════════════════════════════════════════"
echo ""
echo " Schedule : 1st of every month at 9:00 AM"
echo " Script   : $SCRIPT"
echo " Logs     : $LOG_DIR/newsletter-update.log"
echo " li_at    : $LI_AT_FILE"
echo ""
echo " To run manually now:"
echo "   $VENV_DIR/bin/python3 $SCRIPT"
echo ""
echo " To check logs:"
echo "   tail -f $LOG_DIR/newsletter-update.log"
echo ""
echo " To uninstall:"
echo "   launchctl unload $PLIST && rm $PLIST"
echo ""

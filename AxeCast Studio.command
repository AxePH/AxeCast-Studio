#!/usr/bin/env bash
cd "$(dirname "$0")"

if command -v python3 &>/dev/null; then
    python3 app.py &
elif command -v python &>/dev/null; then
    python app.py &
fi
osascript -e 'tell application "Terminal" to close (every window whose name contains "AxeCast")' &>/dev/null &
exit

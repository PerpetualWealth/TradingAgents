#!/bin/bash
# Wrapper script to run analyze.sh from skill directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"
./analyze.sh "$@"

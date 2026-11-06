#!/bin/sh
# Point git at the tracked hooks in devtools/hooks (a local setting; affects only this clone).
#
#   devtools/install_hooks.sh            install
#   git config --unset core.hooksPath    uninstall
set -eu
cd "$(git rev-parse --show-toplevel)"
chmod +x devtools/hooks/*
git config core.hooksPath devtools/hooks
echo "Installed: $(ls devtools/hooks | tr '\n' ' ')"

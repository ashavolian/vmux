#!/bin/sh
# Symlink vmux into ~/.local/bin so a `git pull` in this checkout updates the
# installed command in place, then run the setup wizard if there's no config
# yet. Safe to rerun.
set -eu

here=$(cd "$(dirname "$0")" && pwd)
src="$here/vmux"
bindir="${VMUX_BIN_DIR:-$HOME/.local/bin}"
target="$bindir/vmux"
config="${VMUX_CONFIG:-${XDG_CONFIG_HOME:-$HOME/.config}/vmux/config.json}"

if ! command -v python3 >/dev/null 2>&1; then
    echo "python3 not found on PATH; vmux needs Python 3.9 or newer." >&2
    exit 1
fi
if ! python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)'; then
    echo "python3 is $(python3 --version 2>&1); vmux needs 3.9 or newer." >&2
    exit 1
fi

chmod +x "$src"
mkdir -p "$bindir"

if [ -L "$target" ]; then
    rm "$target"
elif [ -e "$target" ]; then
    mv "$target" "$target.orig"
    echo "moved the existing $target aside to $target.orig"
fi

ln -s "$src" "$target"
echo "installed  $target -> $src"

case ":$PATH:" in
    *":$bindir:"*) ;;
    *)
        echo
        echo "note: $bindir is not on your PATH. Add this to your shell rc:"
        echo "  export PATH=\"$bindir:\$PATH\""
        ;;
esac

if [ -e "$config" ]; then
    echo "config     $config (kept; 'vmux setup' edits it)"
elif [ -t 0 ]; then
    "$src" setup
else
    echo
    echo "no config yet: run 'vmux setup' to write one, or"
    echo "'vmux setup --from FILE' to install a shared one."
fi

echo
echo "run 'vmux' to open the picker. Optional short alias for your shell rc:  alias vmc=vmux"

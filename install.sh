#!/usr/bin/env bash
#
# Arvel installer.
#
# Installs the `arvel` global binary (from the `arvel` package) using uv.
# Bootstraps uv itself if it isn't already on PATH.
#
# Usage:
#
#   curl -fsSL https://arvel.dev/install.sh | bash
#
#   # or with options
#   curl -fsSL https://arvel.dev/install.sh \
#     | bash -s -- --ref v0.1.0
#
# Options:
#   --ref <git-ref>   Install from a specific tag, branch, or commit (default: main)
#   --from-pypi       Install the published `arvel` package from PyPI instead of git
#   --help            Show this help and exit
#
# Exit codes:
#   0  success
#   1  uv bootstrap failed
#   2  arvel install failed
#   3  bad argument
#
# Inspect the script before piping to bash:
#   curl -fsSL https://arvel.dev/install.sh | less

set -euo pipefail

REPO_URL="https://github.com/mohamed-rekiba/arvel.git"
SUBDIR="packages/arvel"
REF="main"
FROM_PYPI=0

# ──────────────────────────────────────────────────────────────────────────────
# Output helpers — colored if stderr is a TTY, plain otherwise.
# ──────────────────────────────────────────────────────────────────────────────
if [[ -t 2 ]]; then
  _bold="$(printf '\033[1m')"; _dim="$(printf '\033[2m')"
  _green="$(printf '\033[32m')"; _yellow="$(printf '\033[33m')"
  _red="$(printf '\033[31m')"; _reset="$(printf '\033[0m')"
else
  _bold=""; _dim=""; _green=""; _yellow=""; _red=""; _reset=""
fi

info()  { printf '%s==>%s %s\n'        "${_bold}${_green}"  "${_reset}" "$*" >&2; }
warn()  { printf '%s warn:%s %s\n'     "${_bold}${_yellow}" "${_reset}" "$*" >&2; }
fail()  { printf '%s error:%s %s\n'    "${_bold}${_red}"    "${_reset}" "$*" >&2; }
hint()  { printf '%s  %s%s\n'          "${_dim}"            "$*"        "${_reset}" >&2; }

usage() {
  sed -n '3,28p' "$0" | sed 's/^# \{0,1\}//'
  exit 0
}

# ──────────────────────────────────────────────────────────────────────────────
# Arg parsing.
# ──────────────────────────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case "$1" in
    --ref)
      [[ $# -ge 2 ]] || { fail "--ref requires a value"; exit 3; }
      REF="$2"; shift 2 ;;
    --ref=*)
      REF="${1#--ref=}"; shift ;;
    --from-pypi)
      FROM_PYPI=1; shift ;;
    --help|-h)
      usage ;;
    *)
      fail "unknown option: $1"
      hint "run with --help to see usage"
      exit 3 ;;
  esac
done

# ──────────────────────────────────────────────────────────────────────────────
# Bootstrap uv if missing. Uses the official astral-sh installer.
# ──────────────────────────────────────────────────────────────────────────────
if ! command -v uv >/dev/null 2>&1; then
  info "uv not found — bootstrapping via the official installer"
  if ! curl -fsSL https://astral.sh/uv/install.sh | sh; then
    fail "uv bootstrap failed"
    hint "install uv manually: https://docs.astral.sh/uv/getting-started/installation/"
    exit 1
  fi
  # The uv installer adds ~/.local/bin to PATH for future shells; export it
  # here so the rest of this script can find the binary it just installed.
  export PATH="${HOME}/.local/bin:${PATH}"
fi

UV_VERSION="$(uv --version 2>/dev/null || echo 'unknown')"
info "using ${UV_VERSION}"

# ──────────────────────────────────────────────────────────────────────────────
# Install arvel. PyPI path is the published, dependency-light happy path;
# the git path is for tracking unreleased commits on a branch or tag.
# ──────────────────────────────────────────────────────────────────────────────
if [[ "${FROM_PYPI}" -eq 1 ]]; then
  info "installing arvel from PyPI"
  install_target="arvel"
else
  info "installing arvel from git (${REF})"
  install_target="git+${REPO_URL}@${REF}#subdirectory=${SUBDIR}"
fi

if ! uv tool install --upgrade --force "${install_target}"; then
  fail "arvel install failed"
  exit 2
fi

# ──────────────────────────────────────────────────────────────────────────────
# Next steps.
# ──────────────────────────────────────────────────────────────────────────────
cat >&2 <<EOF

${_bold}${_green}Done.${_reset} The ${_bold}arvel${_reset} binary is now on your PATH.

Next steps:
  ${_dim}\$${_reset} arvel new my-app
  ${_dim}\$${_reset} cd my-app
  ${_dim}\$${_reset} uv run uvicorn public.asgi:asgi --reload

Docs: https://github.com/mohamed-rekiba/arvel
EOF

#requires -Version 5.1
<#
.SYNOPSIS
    Arvel installer for Windows.

.DESCRIPTION
    Installs the `arvel` global binary (from the `arvel` package) using uv.
    Bootstraps uv itself via the official astral.sh installer if it isn't
    already on PATH.

.PARAMETER Ref
    Git ref (tag, branch, commit SHA) to install from. Default: main.

.PARAMETER FromPyPI
    Install the published `arvel` package from PyPI instead of git.

.PARAMETER Help
    Show this help and exit.

.EXAMPLE
    # Default install from main
    powershell -ExecutionPolicy ByPass -c "irm https://arvel.dev/install.ps1 | iex"

.EXAMPLE
    # Install a specific tag (env vars are how you pass options to `irm | iex`)
    $env:ARVEL_REF = 'v0.1.0'
    powershell -ExecutionPolicy ByPass -c "irm https://arvel.dev/install.ps1 | iex"

.EXAMPLE
    # Install from PyPI instead of git
    $env:ARVEL_FROM_PYPI = '1'
    powershell -ExecutionPolicy ByPass -c "irm https://arvel.dev/install.ps1 | iex"

.EXAMPLE
    # Saved the script locally? Pass parameters directly:
    .\install.ps1 -Ref v0.1.0
    .\install.ps1 -FromPyPI

.NOTES
    Exit codes:
      0  success
      1  uv bootstrap failed
      2  arvel install failed
#>
[CmdletBinding()]
param(
    [string]$Ref,
    [switch]$FromPyPI,
    [switch]$Help
)

$ErrorActionPreference = 'Stop'

$RepoUrl = 'https://github.com/mohamed-rekiba/arvel.git'
$SubDir  = 'packages/arvel'

# Env-var overrides — required when invoked via `irm | iex`, which can't bind
# PowerShell parameters across the pipeline boundary.
if (-not $Ref -and $env:ARVEL_REF) {
    $Ref = $env:ARVEL_REF
}
if (-not $Ref) {
    $Ref = 'main'
}
if (-not $FromPyPI -and $env:ARVEL_FROM_PYPI) {
    $FromPyPI = $true
}

function Write-Step {
    param([string]$Message)
    Write-Host '==> ' -ForegroundColor Green -NoNewline
    Write-Host $Message
}

function Write-Fail {
    param([string]$Message)
    Write-Host ' error: ' -ForegroundColor Red -NoNewline
    Write-Host $Message
}

function Write-Hint {
    param([string]$Message)
    Write-Host "  $Message" -ForegroundColor DarkGray
}

function Show-Help {
    Get-Help -Detailed $PSCommandPath
}

if ($Help) {
    Show-Help
    return
}

# ─── Bootstrap uv if missing ────────────────────────────────────────────────
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Step 'uv not found — bootstrapping via the official installer'
    try {
        Invoke-RestMethod 'https://astral.sh/uv/install.ps1' | Invoke-Expression
    }
    catch {
        Write-Fail "uv bootstrap failed: $_"
        Write-Hint 'install uv manually: https://docs.astral.sh/uv/getting-started/installation/'
        exit 1
    }
    # The astral installer updates the persistent user PATH, which only takes
    # effect for new shells. Prepend the bin dir here so the rest of this
    # script can find the binary it just installed.
    $UvBin = Join-Path $env:USERPROFILE '.local\bin'
    if (Test-Path $UvBin) {
        $env:PATH = "$UvBin;$env:PATH"
    }
}

$UvVersion = (& uv --version 2>$null)
if (-not $UvVersion) {
    $UvVersion = 'unknown'
}
Write-Step "using $UvVersion"

# ─── Install arvel ──────────────────────────────────────────────────────────
if ($FromPyPI) {
    Write-Step 'installing arvel from PyPI'
    $Target = 'arvel'
}
else {
    Write-Step "installing arvel from git ($Ref)"
    $Target = "git+$RepoUrl@$Ref#subdirectory=$SubDir"
}

& uv tool install --upgrade --force $Target
if ($LASTEXITCODE -ne 0) {
    Write-Fail "arvel install failed (uv exit $LASTEXITCODE)"
    exit 2
}

# ─── Next steps ─────────────────────────────────────────────────────────────
Write-Host ''
Write-Host 'Done.' -ForegroundColor Green -NoNewline
Write-Host ' The ' -NoNewline
Write-Host 'arvel' -ForegroundColor Cyan -NoNewline
Write-Host ' binary is now on your PATH.'
Write-Host ''
Write-Host 'Next steps:'
Write-Host '  $ arvel new my-app'                          -ForegroundColor DarkGray
Write-Host '  $ cd my-app'                                 -ForegroundColor DarkGray
Write-Host '  $ uv run uvicorn public.asgi:asgi --reload'  -ForegroundColor DarkGray
Write-Host ''
Write-Host 'Docs: https://github.com/mohamed-rekiba/arvel'

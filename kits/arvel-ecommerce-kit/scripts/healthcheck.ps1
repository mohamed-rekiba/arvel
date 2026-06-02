# Wait until the given docker compose services report healthy, with a spinner.
# A service whose container defines no healthcheck is treated as ready.
#
# Usage: healthcheck.ps1 [service ...]   (defaults to: db redis backend frontend)
# Env:   COMPOSE       docker compose invocation (default: "docker compose")
#        WAIT_TIMEOUT  seconds before giving up (default: 300)
#Requires -Version 5.1
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Service
)

$ErrorActionPreference = 'Stop'

if (-not $env:COMPOSE) {
    $env:COMPOSE = 'docker compose'
}
$Timeout = 300
if ($env:WAIT_TIMEOUT) {
    $parsedTimeout = 0
    if (-not [int]::TryParse($env:WAIT_TIMEOUT, [ref]$parsedTimeout)) {
        Write-Error "WAIT_TIMEOUT must be an integer, got: $($env:WAIT_TIMEOUT)"
    }
    $Timeout = $parsedTimeout
}

if (-not $Service -or $Service.Count -eq 0) {
    $Service = @('db', 'redis', 'backend', 'frontend')
}

function Get-ComposeParts {
    @($env:COMPOSE -split '\s+') | Where-Object { $_ }
}

function Invoke-Compose {
    param([Parameter(Mandatory = $true)][string[]]$Args)
    $parts = Get-ComposeParts
    if ($parts.Count -eq 0) {
        throw 'COMPOSE is empty'
    }
    $exe = $parts[0]
    $rest = @()
    if ($parts.Count -gt 1) {
        $rest = $parts[1..($parts.Count - 1)]
    }
    & $exe @rest @Args
}

function Get-ServiceHealth {
    param([Parameter(Mandatory = $true)][string]$Name)

    $cid = $null
    try {
        $cid = Invoke-Compose -Args @('ps', '-q', $Name) 2>$null
    }
    catch {
        $cid = $null
    }

    if (-not $cid) {
        return 'not-started'
    }

    $cid = ($cid | Select-Object -First 1).ToString().Trim()
    if (-not $cid) {
        return 'not-started'
    }

    $status = $null
    try {
        $status = docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}no-healthcheck{{end}}' $cid 2>$null
    }
    catch {
        $status = $null
    }

    if (-not $status) {
        return 'unknown'
    }
    return $status.ToString().Trim()
}

$spin = @('|', '/', '-', '\')
$index = 0
$start = Get-Date
$isTty = -not [Console]::IsOutputRedirected

while ($true) {
    $allOk = $true
    $summary = ''
    foreach ($svc in $Service) {
        $status = Get-ServiceHealth -Name $svc
        if ($status -ne 'healthy' -and $status -ne 'no-healthcheck') {
            $allOk = $false
        }
        $summary += " ${svc}=${status}"
    }

    $elapsed = [int][Math]::Floor(((Get-Date) - $start).TotalSeconds)

    if ($allOk) {
        if ($isTty) {
            Write-Host "`r`e[0K" -NoNewline
        }
        Write-Host "✔ services ready in ${elapsed}s:${summary}"
        exit 0
    }

    if ($elapsed -ge $Timeout) {
        if ($isTty) {
            Write-Host "`r`e[0K" -NoNewline
        }
        Write-Host "✖ timed out after ${elapsed}s waiting for services:${summary}"
        try {
            Invoke-Compose -Args (@('ps') + $Service) | Out-Host
        }
        catch {
            # Best-effort status dump before exit.
        }
        exit 1
    }

    $frame = $spin[$index % $spin.Count]
    $index++

    if ($isTty) {
        Write-Host "`r`e[0K${frame} waiting for services…${summary} (${elapsed}s)" -NoNewline
    }
    else {
        Write-Host "waiting for services…${summary} (${elapsed}s)"
    }

    Start-Sleep -Seconds 1
}

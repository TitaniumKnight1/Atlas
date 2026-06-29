# Resets the PrevailRP Pathway 2 test fixture to its pristine "freshly inherited messy repo" state.
# Idempotent - safe to run before every adopt/wizard test run.
#
# Usage:
#   .\scripts\test-fixtures\reset-prevailrp-fixture.ps1
#   .\scripts\test-fixtures\reset-prevailrp-fixture.ps1 -FixtureRoot "D:\fixtures\PrevailRP"
#
# NOTE: This restores FIXTURE FILES only. Atlas keeps its own adopted-project / Pathway 2
# wizard state in the local Atlas app database (SQLite under app-data). To fully re-test
# from a blank wizard, also remove the PrevailRP project from Atlas Projects (delete or
# re-import after reset). Otherwise the wizard may resume mid-flow from stored gates/state.

param(
    [string]$FixtureRoot = "C:\Users\Ryan\projects\PrevailRP"
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath $FixtureRoot)) {
    throw "Fixture root not found: $FixtureRoot"
}

$actions = @()

function Remove-IfExists {
    param([string]$Path, [string]$Label)
    if (Test-Path -LiteralPath $Path) {
        Remove-Item -LiteralPath $Path -Force
        $script:actions += "Removed $Label"
    }
}

function Restore-GitignorePristine {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) {
        return
    }
    $lines = Get-Content -LiteralPath $Path -ErrorAction SilentlyContinue |
        Where-Object { $_ -notmatch '^\s*server\.cfg\.local\s*$' }
    $remaining = @($lines | Where-Object { $_.Trim() -ne "" })
    if ($remaining.Count -eq 0) {
        Remove-Item -LiteralPath $Path -Force
        $script:actions += "Removed .gitignore (Atlas-only server.cfg.local entry)"
    } elseif ($remaining.Count -ne @($lines | Where-Object { $_ -ne $null }).Count) {
        Set-Content -LiteralPath $Path -Value ($remaining -join "`n") -Encoding UTF8
        $script:actions += "Stripped server.cfg.local entry from .gitignore"
    }
}

function Restore-BrokenManifest {
    param([string]$ResourceDir)
    if (-not (Test-Path -LiteralPath $ResourceDir)) {
        $script:actions += "Skipped broken-manifest restore (missing $ResourceDir)"
        return
    }
    $manifest = Join-Path $ResourceDir "fxmanifest.lua"
    $bak = Join-Path $ResourceDir "fxmanifest.lua.bak"
    if (Test-Path -LiteralPath $manifest) {
        Remove-Item -LiteralPath $manifest -Force
        $script:actions += "Removed restored fxmanifest.lua (rough edge: manifest intentionally missing)"
    }
    if (-not (Test-Path -LiteralPath $bak)) {
        @"
fx_version 'cerulean'
game 'gta5'

name 'prp-vehicles-1'
description 'PrevailRP test fixture - manifest intentionally renamed to .bak for Pathway 2 tests'
"@ | Set-Content -LiteralPath $bak -Encoding UTF8
        $script:actions += "Recreated fxmanifest.lua.bak (broken-manifest rough edge)"
    } else {
        $script:actions += "Kept fxmanifest.lua.bak (broken-manifest rough edge intact)"
    }
}

# --- Pristine server.cfg: deliberate rough edges preserved (fake secrets, dangling ensures, etc.) ---
$pristineServerCfg = @'
# PrevailRP server.cfg
# This is a test fixture for Atlas

endpoint_add_tcp "0.0.0.0:30120"
endpoint_add_udp "0.0.0.0:30120"

# Fake secrets for P2-1/P2-2 testing
set mysql_connection_string "mysql://user:FAKEpass@prod-host/prevail_db?charset=utf8mb4"
sv_licenseKey "cfxk_FAKE1234567890abcdef_abc123"

# Rough edge: absolute path
setr ox:locale "en"
setr ox:custom_dir "C:/Users/Ryan/projects/PrevailRP/some_custom_dir"

# Add this if you want to have useable doors
setr game_enableDynamicDoorCreation true
# IN RGB FORMAT: [r, g, b] this changes the whole ui color 
setr skeletonnetworks:primaryColor [156, 46, 192]

setr crm-core:language "en"

ensure ox_lib
ensure sn_lib

## Clothing
ensure prp-peds
ensure prp_govclothing
ensure prevail-swat

## Maps
ensure bob74_ipl
ensure cfx-gabz-mapdata
ensure [gabz]
ensure [np]
ensure [fm-maps]

## Vehicles
ensure caraudio
ensure prp-vehicles-1
ensure prp-vehicles-2

# These resources will start by default.
ensure mapmanager
ensure um-chat
ensure spawnmanager
ensure sessionmanager
ensure baseevents
ensure oxmysql

# Qbox & Extra stuff
ensure lation_ui
ensure qbx_core
ensure sd_lib

## Core Scripts
ensure ps-discord
ensure prp-blips
ensure ox_target

# Rough edge: ensure a resource that doesn't exist (teammate repo issue)
ensure missing_custom_map_resource
ensure this_resource_is_missing

# Rough edge: Exec a config from the nested main repo
exec "PrevailRP-main/live_resources.cfg"
'@

$serverCfgPath = Join-Path $FixtureRoot "server.cfg"
Set-Content -LiteralPath $serverCfgPath -Value $pristineServerCfg.TrimEnd() -Encoding UTF8 -NoNewline
$actions += "Rewrote server.cfg to pristine messy state (fake secrets, dangling ensures, tangled exec, no overlay trailer)"

# --- Remove Atlas Pathway 2 normalization / substitution artifacts ---
Remove-IfExists (Join-Path $FixtureRoot "server.cfg.local") "server.cfg.local (Pathway 2 overlay)"
Remove-IfExists (Join-Path $FixtureRoot "server.cfg.local.example") "server.cfg.local.example (normalization template)"

Restore-GitignorePristine (Join-Path $FixtureRoot ".gitignore")

# Also clear overlay artifacts if adopt path pointed at PrevailRP-main (legacy layout)
Remove-IfExists (Join-Path $FixtureRoot "PrevailRP-main\server.cfg.local") "PrevailRP-main\server.cfg.local"
Remove-IfExists (Join-Path $FixtureRoot "PrevailRP-main\server.cfg.local.example") "PrevailRP-main\server.cfg.local.example"
Restore-GitignorePristine (Join-Path $FixtureRoot "PrevailRP-main\.gitignore")

# --- Broken manifest rough edge ---
Restore-BrokenManifest (Join-Path $FixtureRoot "resources\prp-vehicles-1")

Write-Host ""
Write-Host "PrevailRP fixture reset complete"
Write-Host "Fixture root: $FixtureRoot"
Write-Host ""
foreach ($action in $actions) {
    Write-Host "  - $action"
}
Write-Host ""
Write-Host "Rough edges preserved: fake cfxk_/mysql secrets, dangling ensure lines, absolute path,"
Write-Host "tangled exec to PrevailRP-main/live_resources.cfg, missing fxmanifest.lua on prp-vehicles-1."
Write-Host ""
Write-Host "Atlas app state is NOT reset by this script."
Write-Host "To re-run the Join-team wizard from scratch, also remove the PrevailRP project from"
Write-Host "Atlas -> Projects (delete the workspace) so Pathway 2 gates and resume state clear."
Write-Host ""

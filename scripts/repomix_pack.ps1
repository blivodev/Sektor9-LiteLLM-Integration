<#
.SYNOPSIS
    Packages codebase with Repomix for LiteLLM & Sektor9 Agents.
.EXAMPLE
    .\repomix_pack.ps1 -TargetDir "D:\Projects\StarVault" -Style xml -Copy
#>
param(
    [string]$TargetDir = ".",
    [ValidateSet("xml", "markdown", "plain")][string]$Style = "xml",
    [string]$Output = "",
    [switch]$Copy,
    [switch]$Compress
)

$targetPath = (Resolve-Path $TargetDir).Path
$ext = switch ($Style) { "xml" { "xml" } "markdown" { "md" } "plain" { "txt" } }
if (-not $Output) { $Output = Join-Path $targetPath "repomix-output.$ext" }

Write-Host "[*] Packing $targetPath -> $Output ($Style)..." -ForegroundColor Cyan

$argsList = @("-y", "repomix", "`"$targetPath`"", "--style", $Style, "--output", "`"$Output`"")
if ($Compress) { $argsList += @("--remove-comments", "--remove-empty-lines") }

$configCandidate = Join-Path $targetPath "repomix.config.json"
if (-not (Test-Path $configCandidate)) {
    $globalConfig = Join-Path $PSScriptRoot "..\repomix.config.json"
    if (Test-Path $globalConfig) {
        $argsList += @("--config", "`"$globalConfig`"")
    }
}

& npx $argsList

if (Test-Path $Output) {
    $size = (Get-Item $Output).Length / 1KB
    Write-Host "[+] Packed successfully! Size: $([math]::Round($size, 1)) KB" -ForegroundColor Green
    if ($Copy) {
        Get-Content $Output -Raw | Set-Clipboard
        Write-Host "[+] Copied output to clipboard!" -ForegroundColor Green
    }
}

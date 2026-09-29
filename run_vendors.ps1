# PowerShell script to start all 11 Vendor Agents in background on Windows
$env:PYTHONIOENCODING = "utf-8"
$PSScriptRootLocal = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $PSScriptRootLocal) { $PSScriptRootLocal = Get-Location }

Write-Host "🌱 Spawning the OptiVendor Vendor Ecosystem on Windows..." -ForegroundColor Green
Write-Host "---------------------------------------------------"

$vendors = @(
    @{ Name = "Earthly Gourmet"; Port = 8001; Reliability = 0.98 },
    @{ Name = "Feesers Food Dst"; Port = 8002; Reliability = 0.92 },
    @{ Name = "Clark Distributing"; Port = 8003; Reliability = 0.88 },
    @{ Name = "LCG Foods"; Port = 8004; Reliability = 0.95 },
    @{ Name = "Miyokos Creamery"; Port = 8005; Reliability = 0.99 },
    @{ Name = "Rebel Cheese"; Port = 8006; Reliability = 0.96 },
    @{ Name = "Treeline Cheese"; Port = 8007; Reliability = 0.94 },
    @{ Name = "The Vreamery"; Port = 8008; Reliability = 0.97 },
    @{ Name = "The BE Hive"; Port = 8009; Reliability = 0.93 },
    @{ Name = "All Vegetarian Inc"; Port = 8010; Reliability = 0.85 },
    @{ Name = "FakeMeats.com"; Port = 8011; Reliability = 0.99 }
)

foreach ($v in $vendors) {
    Start-Process python -ArgumentList "optivendor_ai/external_vendor/vendor_agent.py --name `"$($v.Name)`" --port $($v.Port) --reliability $($v.Reliability)" -WorkingDirectory $PSScriptRootLocal -WindowStyle Hidden
    Write-Host "  Started $($v.Name) on port $($v.Port)" -ForegroundColor Cyan
}

Start-Sleep -Seconds 3
Write-Host "---------------------------------------------------"
Write-Host "✅ 11 Vendor Agents are active and listening via A2A (Ports 8001-8011)." -ForegroundColor Green
Write-Host "To stop them later, run: .\stop_vendors.ps1"

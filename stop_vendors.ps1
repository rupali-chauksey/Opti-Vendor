# PowerShell script to stop vendor agents running on ports 8001-8011
Write-Host "🧹 Stopping VeganFlow Vendor Agents..." -ForegroundColor Yellow

$ports = 8001..8011
foreach ($port in $ports) {
    $connections = Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue
    if ($connections) {
        foreach ($conn in $connections) {
            $pidToKill = $conn.OwningProcess
            if ($pidToKill -gt 0) {
                Stop-Process -Id $pidToKill -Force -ErrorAction SilentlyContinue
                Write-Host "  Stopped process $pidToKill on port $port" -ForegroundColor Gray
            }
        }
    }
}

Write-Host "✅ All vendor processes on ports 8001-8011 stopped." -ForegroundColor Green

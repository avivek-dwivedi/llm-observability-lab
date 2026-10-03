# sync-keys.ps1
# One command to sync .env keys into collector.env and restart the collector.
# Run this AFTER you edit .env with new Langfuse or LangSmith keys.
#
# Usage:
#   cd d:\Observation_Layer
#   .\infrastructure\sync-keys.ps1

Write-Host ""
Write-Host "  Syncing .env -> collector.env..." -ForegroundColor Cyan
Write-Host ""

# Step 1: regenerate collector.env from .env
& "$PSScriptRoot\generate-collector-env.ps1"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

# Step 2: restart the collector
Write-Host "  Restarting collector..." -ForegroundColor Cyan
docker compose up -d --no-deps --force-recreate otel-collector 2>&1 | Out-Null
Start-Sleep -Seconds 4

# Step 3: verify
$status = docker inspect observation_layer-otel-collector-1 --format '{{.State.Status}}' 2>&1
if ($status -eq "running") {
    Write-Host "  Collector is running." -ForegroundColor Green
    $logs = docker logs observation_layer-otel-collector-1 --tail 2 2>&1
    if ($logs -match "Everything is ready") {
        Write-Host "  Status: Everything is ready." -ForegroundColor Green
    }
} else {
    Write-Host "  WARNING: collector status is '$status'" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "  Done! Traces will now flow to the project matching your .env keys." -ForegroundColor Green
Write-Host ""
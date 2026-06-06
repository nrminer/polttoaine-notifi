# BensaVahti Admin Reboot Script
# Triggers: capture both fuels + run predictions + send notification

$uri = "https://polttoaine-notifi-production-fc06.up.railway.app/api/admin/run"
$token = "syDOHgw2R5HvzHxG1NPHIhIYSWy9U6zvUTqxt5Jk1U2UOwrr"

$headers = @{
    "Content-Type" = "application/json"
    "X-Admin-Token" = $token
}

$body = @{
    password = $token
    action = "all"
    fuel = "all"
    notify = $true
} | ConvertTo-Json

Write-Host "Triggering admin reboot..." -ForegroundColor Cyan

try {
    $response = Invoke-RestMethod -Uri $uri -Method POST -Headers $headers -Body $body
    Write-Host "`nSuccess!" -ForegroundColor Green
    $response | ConvertTo-Json -Depth 10
} catch {
    Write-Host "`nError:" -ForegroundColor Red
    Write-Host $_.Exception.Message
    if ($_.ErrorDetails.Message) {
        Write-Host $_.ErrorDetails.Message
    }
}

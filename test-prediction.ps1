# Test prediction endpoint directly to see detailed error
$uri = "https://polttoaine-notifi-production-fc06.up.railway.app/api/predict/run"
$token = "syDOHgw2R5HvzHxG1NPHIhIYSWy9U6zvUTqxt5Jk1U2UOwrr"

$headers = @{
    "Content-Type" = "application/json"
}

$body = @{
    fuel = "95E10"
    region = "Suomi"
} | ConvertTo-Json

Write-Host "Testing prediction endpoint directly..." -ForegroundColor Cyan

try {
    $response = Invoke-RestMethod -Uri $uri -Method POST -Headers $headers -Body $body
    Write-Host "`nSuccess!" -ForegroundColor Green
    $response | ConvertTo-Json -Depth 10
} catch {
    Write-Host "`nError:" -ForegroundColor Red
    Write-Host $_.Exception.Message
    if ($_.ErrorDetails.Message) {
        Write-Host "`nDetails:" -ForegroundColor Yellow
        $_.ErrorDetails.Message | ConvertFrom-Json | ConvertTo-Json -Depth 10
    }
}

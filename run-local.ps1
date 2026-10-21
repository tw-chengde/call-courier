# 本機測試：開出瀏覽器視窗，預設只填欄位、不按「呼叫」。
# 加上 -Real 才會真的按「呼叫」叫快遞。
param([switch]$Real)

$ErrorActionPreference = "Stop"
Push-Location $PSScriptRoot
try {
    # 已經安裝過的話會直接略過
    uv run playwright install chromium

    # 用提示輸入帳號密碼，不會留在 PowerShell 指令紀錄裡
    $env:MEMBER_USERNAME = Read-Host "帳號"
    $secure = Read-Host "密碼" -AsSecureString
    $env:MEMBER_PASSWORD = [Net.NetworkCredential]::new("", $secure).Password

    $env:HEADLESS = "false"
    $env:FORCE_RUN = "true"
    $env:DRY_RUN = if ($Real) { "false" } else { "true" }

    uv run main.py
}
finally {
    Remove-Item Env:MEMBER_USERNAME, Env:MEMBER_PASSWORD, Env:HEADLESS, Env:FORCE_RUN, Env:DRY_RUN -ErrorAction SilentlyContinue
    Pop-Location
}

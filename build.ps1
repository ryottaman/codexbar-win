# CodexBar for Windows を単一 exe にビルドする。
# 実行: powershell -ExecutionPolicy Bypass -File build.ps1
#
# 出力: dist\CodexBar-Win.exe（コンソール窓なし・常駐アプリ）

$ErrorActionPreference = "Stop"
$appDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $appDir

$py = (Get-Command python).Source  # PATH 上の python を使用

Write-Host "PyInstaller を確認中…"
& $py -m pip install --quiet pyinstaller

Write-Host "ビルド中…（初回は数分かかることがあります）"
& $py -m PyInstaller `
    --noconfirm `
    --clean `
    --onefile `
    --windowed `
    --name "CodexBar-Win" `
    --collect-submodules pystray `
    --collect-submodules PIL `
    run.pyw

Write-Host ""
if (Test-Path "dist\CodexBar-Win.exe") {
    # デフォルト設定を exe の隣に置く（無ければ初期値で動くが、目安として同梱）
    Copy-Item "config.toml" "dist\config.toml" -Force
    Write-Host "完成: dist\CodexBar-Win.exe"
    Write-Host "このexeを配布・実行すればトレイ常駐します（Python不要）。"
} else {
    Write-Host "ビルドに失敗しました。上のログを確認してください。"
}

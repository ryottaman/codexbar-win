# CodexBar for Windows を単一 exe にビルドする。
# 実行: powershell -ExecutionPolicy Bypass -File build.ps1
#       powershell -ExecutionPolicy Bypass -File build.ps1 -Python "C:\path\to\python.exe"
#
# 出力: dist\CodexBar-Win.exe（コンソール窓なし・常駐アプリ）
# 複数の Python が入っている環境では -Python で依存をインストール済みの
# インタープリタを明示すること（PATH の python と食い違うと exe に依存が入らない）。

param([string]$Python = "")

$ErrorActionPreference = "Stop"
$appDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $appDir

if ($Python) {
    $py = $Python
} else {
    # PATH 上の python を使用。無ければ py ランチャーにフォールバック
    $pyCmd = Get-Command python -ErrorAction SilentlyContinue
    if ($pyCmd) {
        $py = $pyCmd.Source
    } elseif (Get-Command py -ErrorAction SilentlyContinue) {
        $py = "py"
    } else {
        Write-Error "Python が見つかりません。https://www.python.org/ からインストールし、PATH に追加してください。"
        exit 1
    }
}
Write-Host "使用する Python: $py"

Write-Host "依存ライブラリと PyInstaller を確認中…"
& $py -m pip install --quiet -r requirements.txt pyinstaller

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

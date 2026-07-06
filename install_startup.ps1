# Windows スタートアップに CodexBar for Windows を登録する。
# 実行: 右クリック →「PowerShell で実行」、または
#   powershell -ExecutionPolicy Bypass -File install_startup.ps1

$ErrorActionPreference = "Stop"

$appDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$pyw = $null
$pyCmd = Get-Command python -ErrorAction SilentlyContinue
if ($pyCmd) {
    $candidate = Join-Path (Split-Path $pyCmd.Source) "pythonw.exe"
    if (Test-Path $candidate) { $pyw = $candidate }
}
if (-not $pyw) {
    # python が PATH に無い場合のフォールバック（環境の pythonw に委ねる）
    $pyw = "pythonw.exe"
}
$target = Join-Path $appDir "run.pyw"

$startup = [Environment]::GetFolderPath("Startup")
$shortcut = Join-Path $startup "CodexBar-Win.lnk"

$shell = New-Object -ComObject WScript.Shell
$lnk = $shell.CreateShortcut($shortcut)
$lnk.TargetPath = $pyw
$lnk.Arguments = "`"$target`""
$lnk.WorkingDirectory = $appDir
$lnk.WindowStyle = 7  # 最小化
$lnk.Description = "CodexBar for Windows"
$lnk.Save()

Write-Host "登録しました: $shortcut"
Write-Host "起動コマンド: $pyw `"$target`""
Write-Host ""
Write-Host "解除する場合はこのショートカットを削除してください:"
Write-Host "  $shortcut"

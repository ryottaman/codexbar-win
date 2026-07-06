# Windows スタートアップに CodexBar for Windows を登録する。
# 実行: 右クリック →「PowerShell で実行」、または
#   powershell -ExecutionPolicy Bypass -File install_startup.ps1

$ErrorActionPreference = "Stop"

$appDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$pyw = Join-Path (Split-Path (Get-Command python).Source) "pythonw.exe"
if (-not (Test-Path $pyw)) {
    # python.exe と同階層に pythonw.exe が無い場合のフォールバック
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

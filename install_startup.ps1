# Windows スタートアップに CodexBar for Windows を登録する。
# 実行: 右クリック →「PowerShell で実行」、または
#   powershell -ExecutionPolicy Bypass -File install_startup.ps1
#   powershell -ExecutionPolicy Bypass -File install_startup.ps1 -Python "C:\path\to\pythonw.exe"
#
# 複数の Python が入っている環境では、依存（pip install -r requirements.txt）を
# 入れたインタープリタの pythonw.exe を -Python で明示すること。
# PATH の python と食い違うと起動時に ModuleNotFoundError で落ちる。

param([string]$Python = "")

$ErrorActionPreference = "Stop"

$appDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$pyw = $null
if ($Python) {
    $pyw = $Python
} else {
    $pyCmd = Get-Command python -ErrorAction SilentlyContinue
    if ($pyCmd) {
        $candidate = Join-Path (Split-Path $pyCmd.Source) "pythonw.exe"
        if (Test-Path $candidate) { $pyw = $candidate }
    }
    if (-not $pyw) {
        # python が PATH に無い場合のフォールバック（環境の pythonw に委ねる）
        $pyw = "pythonw.exe"
    }
}
Write-Host "使用する pythonw: $pyw"

# 依存確認（pystray が無い python を登録すると起動に失敗するため事前チェック）
$pyExe = $pyw -replace "pythonw\.exe$", "python.exe"
if (Test-Path $pyExe) {
    & $pyExe -c "import pystray, httpx, PIL" 2>$null
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "この Python には依存ライブラリがありません。先に以下を実行してください:"
        Write-Warning "  `"$pyExe`" -m pip install -r `"$appDir\requirements.txt`""
        exit 1
    }
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

param(
    [ValidateSet('start', 'stop', 'status', 'check')][string]$Action = 'start',
    [ValidateSet('ticket', 'full')][string]$Mode = 'ticket',
    [switch]$NoBrowser
)
$ErrorActionPreference = 'Stop'
try {
    $configPath = Join-Path $PSScriptRoot 'project-launcher.json'
    $config = Get-Content -LiteralPath $configPath -Raw -Encoding UTF8 | ConvertFrom-Json
    $pythonPath = $config.hazard_python
    if (-not (Test-Path -LiteralPath $pythonPath)) {
        throw "Python not found: $pythonPath. Check project-launcher.json."
    }
    $pythonRoot = Split-Path -Parent $pythonPath
    $env:PATH = "$pythonRoot;$pythonRoot\Library\bin;$pythonRoot\Scripts;$env:PATH"
    $env:PYTHONUTF8 = '1'
    $env:PYTHONIOENCODING = 'utf-8'
    $arguments = @('-I', (Join-Path $PSScriptRoot 'scripts\project_launcher.py'), $Action, '--mode', $Mode)
    if ($NoBrowser) { $arguments += '--no-browser' }
    & $pythonPath @arguments
    exit $LASTEXITCODE
} catch {
    Write-Host $_.Exception.Message -ForegroundColor Red
    exit 1
}

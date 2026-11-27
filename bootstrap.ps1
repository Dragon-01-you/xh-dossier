param(
    [string]$InstallDir = "$env:LOCALAPPDATA\XH-Dossier\python",
    [string]$Version = "3.12.10",
    [string]$ScriptsDir = "",
    [string]$PythonZip = "",
    [switch]$Force
)

$ErrorActionPreference = 'Stop'
$repoScripts = if ($ScriptsDir) { $ScriptsDir } else { Join-Path $PSScriptRoot 'scripts' }

function Update-Pth {
    param([string]$PthPath, [string]$ScriptsPath)
    if (Test-Path -LiteralPath $PthPath) {
        $pthLines = @(
            'python312.zip',
            '.',
            'scripts',
            '..\scripts',
            $ScriptsPath
        )
        Set-Content -LiteralPath $PthPath -Value $pthLines -Encoding ASCII
    }
}

function Test-PythonCandidate {
    param([string]$Exe)
    try {
        & $Exe -c "import sys; raise SystemExit(0 if sys.version_info >= (3,11) else 3)" 2>&1 | Out-Null
        return ($LASTEXITCODE -eq 0)
    } catch {
        return $false
    }
}

function Find-Python {
    $candidates = @(
        (Join-Path $InstallDir 'python.exe'),
        (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\python.exe'),
        (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python311\python.exe'),
        (Join-Path $env:USERPROFILE 'AppData\Local\Programs\Python\Python312\python.exe'),
        (Join-Path $env:USERPROFILE 'AppData\Local\Programs\Python\Python311\python.exe')
    )
    foreach ($candidate in $candidates) {
        if (Test-Path -LiteralPath $candidate) {
            if (Test-PythonCandidate -Exe $candidate) {
                return $candidate
            }
        }
    }
    return $null
}

Write-Output "=== XH-Dossier Python bootstrap ==="
$found = Find-Python
if ($found -and -not $Force) {
    $pthPath = Join-Path $InstallDir 'python312._pth'
    Update-Pth -PthPath $pthPath -ScriptsPath $repoScripts
    $ver = (& $found --version 2>&1 | Out-String).Trim()
    Write-Output "BOOTSTRAP_OK python=$found version=$ver"
    exit 0
}

$zipName = "python-$Version-embed-amd64.zip"
$zipUrl = "https://www.python.org/ftp/python/$Version/$zipName"
$zipPath = if ($PythonZip) { $PythonZip } else { Join-Path $env:TEMP $zipName }
if ($PythonZip) {
    Write-Output "PYTHON_ZIP: $zipPath"
    if (-not (Test-Path -LiteralPath $zipPath)) {
        Write-Output "BOOTSTRAP_FAIL: 指定的 Python 便携包不存在：$zipPath"
        exit 2
    }
} else {
    Write-Output "PYTHON_MISSING: downloading $zipUrl"
    try {
        Invoke-WebRequest -Uri $zipUrl -OutFile $zipPath -UseBasicParsing -TimeoutSec 120
        Write-Output "DOWNLOAD_OK: $zipPath"
    } catch {
        Write-Output "BOOTSTRAP_FAIL: Python 便携包下载失败：$($_.Exception.Message)"
        Write-Output "fallback: 打开 https://www.python.org/downloads/ 手动安装 Python 3.11+，然后重跑 install.ps1"
        exit 2
    }
}

if (-not (Test-Path -LiteralPath $zipPath) -or (Get-Item -LiteralPath $zipPath).Length -lt 1000000) {
    Write-Output "BOOTSTRAP_FAIL: 下载文件不完整：$zipPath"
    exit 2
}

if (Test-Path -LiteralPath $InstallDir) {
    Remove-Item -LiteralPath $InstallDir -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
try {
    Expand-Archive -LiteralPath $zipPath -DestinationPath $InstallDir -Force
    Write-Output "EXTRACT_OK: $InstallDir"
} catch {
    Write-Output "BOOTSTRAP_FAIL: 解压失败：$($_.Exception.Message)"
    exit 2
}

$python = Join-Path $InstallDir 'python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    Write-Output "BOOTSTRAP_FAIL: 解压后未找到 $python"
    exit 2
}

# 便携版默认只看 exe 同目录；XH 的脚本在仓库 scripts/。
# 把当前仓库的 scripts 绝对路径写进 _pth，否则 xh.py 找不到 archive_io。
$pth = Join-Path $InstallDir 'python312._pth'
Update-Pth -PthPath $pth -ScriptsPath $repoScripts
Write-Output "PTH_OK: $pth -> $repoScripts"

$ver = (& $python --version 2>&1 | Out-String).Trim()
& $python -c "import sqlite3; print('SQLITE_OK', sqlite3.sqlite_version)" 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Output "BOOTSTRAP_FAIL: Python 便携版 sqlite3 自检失败"
    exit 2
}
Write-Output "BOOTSTRAP_OK python=$python version=$ver"
exit 0

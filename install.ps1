param(
    [string]$Target = "$env:USERPROFILE\XH-Dossier",
    [string]$Archive = "",
    [string]$PythonZip = "",
    [switch]$RunDemo,
    [switch]$Force,
    [switch]$ForceBootstrap
)

$ErrorActionPreference = 'Stop'
Write-Output "=== XH-Dossier 一键安装 ==="

$src = (Resolve-Path -LiteralPath $PSScriptRoot).Path
Write-Output "source: $src"

# Python detection must happen before creating/copying anything.
# If Python is missing, leave no half-installed target behind.
$pyExe = $null
$pyArgs = @()
if (-not $ForceBootstrap) {
    $portablePy = Join-Path $env:LOCALAPPDATA 'XH-Dossier\python\python.exe'
    if (Test-Path -LiteralPath $portablePy) {
        try {
            & $portablePy -c "import sys; raise SystemExit(0 if sys.version_info >= (3,11) else 3)" 2>&1 | Out-Null
            if ($LASTEXITCODE -eq 0) {
                $pyExe = $portablePy
                $pyArgs = @()
            }
        } catch { }
    }
    foreach ($candidate in @(@('py', '-3'), @('python', ''))) {
        $exe = $candidate[0]
        $args = @($candidate[1..($candidate.Count - 1)] | Where-Object { $_ })
        try {
            & $exe @args -c "import sys; raise SystemExit(0 if sys.version_info >= (3,11) else 3)" 2>&1 | Out-Null
            if ($LASTEXITCODE -eq 0) {
                $pyExe = $exe
                $pyArgs = $args
                break
            }
        } catch { }
    }
}

if (-not $pyExe) {
    $bootstrap = Join-Path $PSScriptRoot 'bootstrap.ps1'
    if (Test-Path -LiteralPath $bootstrap) {
        Write-Output "PYTHON_MISSING: 尝试用 bootstrap.ps1 下载并安装 Python 3.11+。"
        $bootstrapArgs = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $bootstrap, '-InstallDir', "$env:LOCALAPPDATA\XH-Dossier\python", '-ScriptsDir', (Join-Path $Target 'scripts'))
        if ($PythonZip) { $bootstrapArgs += @('-PythonZip', $PythonZip) }
        if ($ForceBootstrap) { $bootstrapArgs += '-Force' }
        $bootstrapOutput = & powershell.exe @bootstrapArgs 2>&1
        $bootstrapOutput | ForEach-Object { Write-Output $_ }
        $bootCode = $LASTEXITCODE
        $candidate = Join-Path $env:LOCALAPPDATA 'XH-Dossier\python\python.exe'
        $bootPy = $null
        if ($bootCode -eq 0) {
            $bootLine = @($bootstrapOutput | Where-Object { "$_" -match 'BOOTSTRAP_OK python=' } | Select-Object -Last 1)
            if ($bootLine.Count -gt 0 -and "$($bootLine[0])" -match 'BOOTSTRAP_OK python=([^\r\n]+?) version=') {
                $bootPy = $Matches[1].Trim()
            }
            if (-not $bootPy) { $bootPy = $candidate }
            if ($bootPy -and (Test-Path -LiteralPath $bootPy)) {
                $pyExe = $bootPy
                $pyArgs = @()
            }
        }
    }
}

if (-not $pyExe) {
    Write-Output "INSTALL_FAIL: 未找到 Python 3.11+，自动安装也没有成功。"
    Write-Output "安装路径（任选其一，装完重跑本脚本）："
    Write-Output "  1) 官方安装包：https://www.python.org/downloads/  选 Python 3.11 或更新版本。"
    Write-Output "  2) winget（如机器有）：winget install Python.Python.3.12"
    Write-Output "  3) 共享机器 / per-user 安装被 launcher 拦截：见 README「per-user 安装退路」，安装参数 Include_launcher=0，装好后用 python 调用。"
    exit 1
}

if ($Archive -and -not (Test-Path -LiteralPath $Archive)) {
    Write-Output "INSTALL_FAIL: 发布包不存在：$Archive"
    exit 1
}

if (-not (Test-Path -LiteralPath $Target)) {
    New-Item -ItemType Directory -Force -Path $Target | Out-Null
}
$Target = (Resolve-Path -LiteralPath $Target).Path
Write-Output "target: $Target"

if ($Archive) {
    # 主路径：Expand-Archive（.NET ZipArchive，认 UTF-8 文件名标志）。
    try {
        Expand-Archive -LiteralPath $Archive -DestinationPath $Target -Force
        Write-Output "extract: Expand-Archive"
    } catch {
        # 退路：Python 标准库 zipfile（同样认 UTF-8 标志）。
        Write-Output "WARN: Expand-Archive 失败，改用 Python zipfile 解压：$_"
        & $pyExe @pyArgs -m zipfile -e $Archive $Target
        if ($LASTEXITCODE -ne 0) {
            Write-Output "INSTALL_FAIL: Python zipfile 解压返回 $LASTEXITCODE"
            exit $LASTEXITCODE
        }
        Write-Output "extract: python zipfile"
    }
} elseif ($src -eq $Target) {
    Write-Output "INSTALL_SKIP: source and target are the same directory"
} else {
    $nonEmpty = $false
    if (Test-Path -LiteralPath $Target) {
        $nonEmpty = @(Get-ChildItem -LiteralPath $Target -Force -ErrorAction SilentlyContinue).Count -gt 0
    }
    if ($nonEmpty -and -not $Force) {
        Write-Output "INSTALL_NOTE: target already exists; existing files will be overwritten. Use -Force to suppress this note."
    }
    $exclude = @('.git', 'work', 'dist', '.pytest_cache', '__pycache__', '.venv')
    Get-ChildItem -LiteralPath $src -Force | Where-Object {
        $_.Name -notin $exclude
    } | ForEach-Object {
        Copy-Item -LiteralPath $_.FullName -Destination $Target -Recurse -Force
    }
}

# GitHub / 发布 zip 常带一个顶层目录（xh-dossier-<ref>/）。install.ps1 的
# target 约定是“仓库根”，所以单层顶层目录要拍平，否则后续 scripts/xh.py
# 会去 target\scripts 找而实际在 target\xh-dossier-...\scripts。
if ($Archive) {
    $children = @(Get-ChildItem -LiteralPath $Target -Force -ErrorAction SilentlyContinue)
    if ($children.Count -eq 1 -and $children[0].PSIsContainer) {
        $nested = $children[0].FullName
        Get-ChildItem -LiteralPath $nested -Force | ForEach-Object {
            Move-Item -LiteralPath $_.FullName -Destination $Target -Force
        }
        Remove-Item -LiteralPath $nested -Recurse -Force
        Write-Output "flatten: $($children[0].Name) -> $Target"
    }
}

$pyCmd = (@($pyExe) + @($pyArgs) + @("-X", "utf8")) -join ' '
$version = (& $pyExe @pyArgs -c "import sys; print(sys.version.split()[0])" 2>&1 | Out-String).Trim()
Write-Output "python: $version ($pyCmd)"

Push-Location $Target
try {
    & $pyExe @pyArgs -X utf8 scripts\xh.py doctor
    if ($LASTEXITCODE -ne 0) {
        Write-Output "INSTALL_FAIL: doctor returned $LASTEXITCODE"
        exit $LASTEXITCODE
    }
    & $pyExe @pyArgs -X utf8 scripts\xh.py init
    if ($LASTEXITCODE -ne 0) {
        Write-Output "INSTALL_FAIL: init returned $LASTEXITCODE"
        exit $LASTEXITCODE
    }
    if ($RunDemo) {
        & $pyExe @pyArgs -X utf8 scripts\xh.py demo
        if ($LASTEXITCODE -ne 0) {
            Write-Output "INSTALL_FAIL: demo returned $LASTEXITCODE"
            exit $LASTEXITCODE
        }
    }
} finally {
    Pop-Location
}

Write-Output "INSTALL_OK"
Write-Output "next: cd `"$Target`" ; $pyCmd scripts\xh.py doctor"
Write-Output "read: $Target\AGENT_START_HERE.md"

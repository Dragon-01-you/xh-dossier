param(
    [string]$Target = "$env:USERPROFILE\XH-Dossier",
    [string]$Archive = "",
    [switch]$RunDemo,
    [switch]$Force
)

$ErrorActionPreference = 'Stop'
Write-Output "=== XH-Dossier 一键安装 ==="

$src = (Resolve-Path -LiteralPath $PSScriptRoot).Path
if (-not (Test-Path -LiteralPath $Target)) {
    New-Item -ItemType Directory -Force -Path $Target | Out-Null
}
$Target = (Resolve-Path -LiteralPath $Target).Path
Write-Output "source: $src"
Write-Output "target: $Target"

# Python detection: prefer py -3 (launcher picks the newest 3.x), then plain python.
$pyExe = $null
$pyArgs = @()
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

if ($Archive) {
    # 主路径：Expand-Archive（.NET ZipArchive，认 UTF-8 文件名标志）。
    if (-not (Test-Path -LiteralPath $Archive)) {
        Write-Output "INSTALL_FAIL: 发布包不存在：$Archive"
        exit 1
    }
    try {
        Expand-Archive -LiteralPath $Archive -DestinationPath $Target -Force
        Write-Output "extract: Expand-Archive"
    } catch {
        # 退路：Python 标准库 zipfile（同样认 UTF-8 标志）。
        if (-not $pyExe) {
            Write-Output "INSTALL_FAIL: Expand-Archive 失败，且未找到 Python 作为退路：$_"
            exit 1
        }
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
    $exclude = @('.git', 'work', 'dist', '.pytest_cache', '__pycache__', '.venv')
    Get-ChildItem -LiteralPath $src -Force | Where-Object {
        $_.Name -notin $exclude
    } | ForEach-Object {
        Copy-Item -LiteralPath $_.FullName -Destination $Target -Recurse -Force:$Force
    }
}

if (-not $pyExe) {
    Write-Output "INSTALL_FAIL: 未找到 Python 3.11+（当前机器没有可用的 Python 解释器）。"
    Write-Output "安装路径（任选其一，装完重跑本脚本）："
    Write-Output "  1) winget（Windows 自带包管理器）：winget install Python.Python.3.12"
    Write-Output "  2) 官网下载页：https://www.python.org/downloads/  选 Python 3.11 或更新版本，安装时勾选 Add python.exe to PATH。"
    Write-Output "  3) 共享机器 / per-user 安装被 launcher 拦截：见 README「per-user 安装退路」，安装参数 Include_launcher=0，装好后用 python 调用。"
    exit 1
}
$version = (& $pyExe @pyArgs -c "import sys; print(sys.version.split()[0])" 2>&1 | Out-String).Trim()
Write-Output "python: $version ($pyExe $($pyArgs -join ' '))"

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
Write-Output "next: cd `"$Target`" ; $pyExe $($pyArgs -join ' ') -X utf8 scripts\xh.py doctor"
Write-Output "read: $Target\AGENT_START_HERE.md"

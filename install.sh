#!/usr/bin/env bash
# XH-Dossier 一键安装（Linux / macOS）。
#
# 用法：
#   ./install.sh [发布包] [目标目录]
#   不带参数：在当前检出目录里跑 doctor 预检。
#
# 解压主路径按 issue #55 选工具：
#   - .zip  ：优先 Python 标准库 zipfile（认 UTF-8 文件名标志）；
#             退路 1 bsdtar（libarchive）；退路 2 才是 unzip（6.00 会乱码，给警告）。
#   - .tar.gz / .tgz：GNU tar / bsdtar，文件名不走 zip 代码页，不会乱码。
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

PY=""
for candidate in python3 python; do
  if command -v "$candidate" >/dev/null 2>&1; then
    PY="$candidate"
    break
  fi
done
if [ -z "$PY" ]; then
  echo "INSTALL_FAIL: 未找到 Python 3。请先安装 Python 3.11+，再重试。"
  exit 1
fi

ARCHIVE="${1:-}"
TARGET="${2:-$SCRIPT_DIR}"

extract_zip() {
  local archive="$1" dest="$2"
  # 主路径：Python 标准库 zipfile（认 UTF-8 EFS 标志，中文文件名不乱码）。
  if "$PY" -m zipfile -e "$archive" "$dest"; then
    echo "extract: python zipfile"
    return 0
  fi
  # 退路 1：bsdtar（libarchive，认 UTF-8）。
  if command -v bsdtar >/dev/null 2>&1; then
    echo "WARN: python zipfile 解压失败，改用 bsdtar。"
    bsdtar -xf "$archive" -C "$dest"
    echo "extract: bsdtar"
    return 0
  fi
  # 退路 2：Info-ZIP unzip 6.00 —— 已知会忽略 UTF-8 标志、把中文文件名解成乱码，最后才用。
  if command -v unzip >/dev/null 2>&1; then
    echo "WARN: 当前环境没有可用的 python zipfile / bsdtar，只能用 unzip 解压。"
    echo "      含中文文件名时可能乱码；若 doctor 报“文件名编码损坏”，请改用："
    echo "      $PY -m zipfile -e \"$archive\" \"$dest\""
    unzip -q "$archive" -d "$dest"
    echo "extract: unzip (last resort, may garble names)"
    return 0
  fi
  echo "INSTALL_FAIL: 没有可用的解压工具（python zipfile / bsdtar / unzip）。"
  exit 1
}

if [ -n "$ARCHIVE" ]; then
  if [ ! -f "$ARCHIVE" ]; then
    echo "INSTALL_FAIL: 发布包不存在：$ARCHIVE"
    exit 1
  fi
  mkdir -p "$TARGET"
  case "$ARCHIVE" in
    *.zip)
      extract_zip "$ARCHIVE" "$TARGET"
      ;;
    *.tar.gz|*.tgz)
      tar -xzf "$ARCHIVE" -C "$TARGET"
      echo "extract: tar"
      ;;
    *)
      echo "INSTALL_FAIL: 仅支持 .zip / .tar.gz / .tgz：$ARCHIVE"
      exit 1
      ;;
  esac
fi

"$PY" -X utf8 "$TARGET/scripts/00_doctor.py" --root "$TARGET"

echo "INSTALL_OK"
echo "next: cd \"$TARGET\" && $PY -X utf8 scripts/xh.py init"
echo "read: $TARGET/AGENT_START_HERE.md"

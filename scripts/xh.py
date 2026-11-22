#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""XH-Dossier one-entry CLI for a fresh local Agent.

Design goals:
- no third-party dependency for the core path;
- every command prints a stable OK/FAIL token and a machine-readable JSON receipt;
- a new Agent only needs to read AGENT_START_HERE.md and call `python scripts/xh.py doctor`.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime, timezone, timedelta

ROOT = pathlib.Path(__file__).resolve().parent.parent
WORK = ROOT / "work"
TEMPLATES = ROOT / "templates"
SAMPLE_RAW = ROOT / "examples" / "sample_raw"

REQUIRED_SCRIPTS = [
    "01_clean_and_index.py",
    "02_four_way_match.py",
    "03_validate_kit.py",
    "04_bootstrap_kit.py",
]
OPTIONAL_SCRIPTS = [
    "00_export_wizard.py",
    "05_deep_backfill.py",
    "05_temporal_index.py",
    "06_graph_index.py",
    "07_recall_time_graph.py",
]
KIT_FILES = [
    "AGENTS.md",
    "00-总入口索引.md",
    "01-身份与当前主线.md",
    "02-核心判断准则.md",
    "03-硬规则与表达黑话.md",
    "04-正反例避坑账.md",
]


def _now() -> str:
    return datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds")


def _receipt(name: str, ok: bool, **data: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "command": name,
        "ok": ok,
        "at": _now(),
        "root": str(ROOT),
    }
    payload.update(data)
    return payload


def _write_receipt(name: str, payload: dict[str, object]) -> pathlib.Path:
    WORK.mkdir(parents=True, exist_ok=True)
    path = WORK / f"xh-{name}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _run(args: list[str]) -> int:
    print("RUN:", " ".join(args))
    proc = subprocess.run(args, cwd=str(ROOT), text=True)
    print("EXIT:", proc.returncode)
    return proc.returncode


def _script(name: str) -> pathlib.Path:
    return ROOT / "scripts" / name


def _kit_actual_name(folder: pathlib.Path, canonical: str) -> pathlib.Path | None:
    aliases = {
        "04-正反例避坑账.md": ["04-正反例避坑账.md", "04-反面案例清单.md"],
    }
    for name in aliases.get(canonical, [canonical]):
        candidate = folder / name
        if candidate.is_file():
            return candidate
    return None


def doctor(args: argparse.Namespace) -> int:
    errors: list[str] = []
    warnings: list[str] = []
    scripts: dict[str, bool] = {}
    for name in REQUIRED_SCRIPTS:
        scripts[name] = _script(name).is_file()
        if not scripts[name]:
            errors.append(f"missing scripts/{name}")
    optional: dict[str, bool] = {}
    for name in OPTIONAL_SCRIPTS:
        optional[name] = _script(name).is_file()
        if not optional[name]:
            warnings.append(f"optional scripts/{name} missing")

    templates: dict[str, bool] = {}
    for name in KIT_FILES:
        templates[name] = _kit_actual_name(TEMPLATES, name) is not None
        if not templates[name]:
            errors.append(f"missing template {name}")

    sample_count = 0
    if SAMPLE_RAW.is_dir():
        sample_count = len([p for p in SAMPLE_RAW.iterdir() if p.is_file()])
    if sample_count == 0:
        errors.append("examples/sample_raw is missing or empty")

    work_writable = False
    try:
        WORK.mkdir(parents=True, exist_ok=True)
        probe = WORK / ".xh-write-probe"
        probe.write_text("ok", encoding="utf-8")
        work_writable = probe.is_file()
        probe.unlink(missing_ok=True)
    except OSError:
        errors.append("work/ is not writable")

    py_ok = sys.version_info >= (3, 10)
    if not py_ok:
        errors.append(f"Python >=3.10 required, got {sys.version.split()[0]}")

    browsers = {
        "edge": pathlib.Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe").is_file()
        or pathlib.Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe").is_file(),
        "chrome": pathlib.Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe").is_file(),
    }
    if not any(browsers.values()):
        warnings.append("no Edge/Chrome found; browser export needs a human/browser Agent")

    payload = _receipt(
        "doctor",
        not errors,
        python=sys.version.split()[0],
        scripts=scripts,
        optional_scripts=optional,
        templates=templates,
        sample_raw_count=sample_count,
        work_writable=work_writable,
        browsers=browsers,
        errors=errors,
        warnings=warnings,
    )
    path = _write_receipt("doctor", payload)
    print("DOCTOR_OK" if not errors else "DOCTOR_FAIL")
    print("receipt:", path)
    for err in errors:
        print("ERROR:", err)
    for warning in warnings:
        print("WARN:", warning)
    return 0 if not errors else 1


def init(args: argparse.Namespace) -> int:
    for name in ["raw", "interview", "kit", "reports", "evidence", "extensions"]:
        (WORK / name).mkdir(parents=True, exist_ok=True)
    kit = WORK / "kit"
    copied: list[str] = []
    if not any(kit.iterdir()):
        for canonical in KIT_FILES:
            src = _kit_actual_name(TEMPLATES, canonical)
            if src is None:
                continue
            dst = kit / canonical
            shutil.copyfile(src, dst)
            copied.append(canonical)
    payload = _receipt("init", True, work=str(WORK), kit=str(kit), copied=copied)
    path = _write_receipt("init", payload)
    print("INIT_OK")
    print("work:", WORK)
    print("kit:", kit)
    print("copied:", ", ".join(copied) if copied else "(already populated)")
    print("receipt:", path)
    return 0


def demo(args: argparse.Namespace) -> int:
    demo_dir = WORK / "demo"
    demo_dir.mkdir(parents=True, exist_ok=True)
    db = demo_dir / "unified_index.db"
    report = demo_dir / "backfill_candidates.md"
    rc = _run([sys.executable, "-X", "utf8", str(_script("01_clean_and_index.py")), "--raw", str(SAMPLE_RAW), "--db", str(db), "--query", "记错"])
    if rc == 0:
        rc = _run([sys.executable, "-X", "utf8", str(_script("02_four_way_match.py")), "--db", str(db), "--out", str(report)])
    if rc == 0:
        rc = _run([sys.executable, "-X", "utf8", str(_script("03_validate_kit.py")), "--target", str(TEMPLATES)])
    payload = _receipt("demo", rc == 0, demo_dir=str(demo_dir), db=str(db), report=str(report))
    path = _write_receipt("demo", payload)
    print("DEMO_OK" if rc == 0 else "DEMO_FAIL")
    print("receipt:", path)
    return rc


def ingest(args: argparse.Namespace) -> int:
    raw = pathlib.Path(args.raw).expanduser()
    db = pathlib.Path(args.db).expanduser()
    return _run([sys.executable, "-X", "utf8", str(_script("01_clean_and_index.py")), "--raw", str(raw), "--db", str(db), "--query", args.query])


def match(args: argparse.Namespace) -> int:
    db = pathlib.Path(args.db).expanduser()
    out = pathlib.Path(args.out).expanduser()
    cmd = [sys.executable, "-X", "utf8", str(_script("02_four_way_match.py")), "--db", str(db), "--out", str(out)]
    if args.keywords:
        cmd += ["--keywords", *args.keywords]
    return _run(cmd)


def bootstrap(args: argparse.Namespace) -> int:
    db = pathlib.Path(args.db).expanduser()
    out = pathlib.Path(args.out).expanduser()
    return _run([sys.executable, "-X", "utf8", str(_script("04_bootstrap_kit.py")), "--db", str(db), "--out", str(out)])


def build(args: argparse.Namespace) -> int:
    """One-command chain: raw chat -> index -> match -> 6-file draft -> L2 proposal -> validate."""
    raw = pathlib.Path(args.raw).expanduser()
    db = pathlib.Path(args.db).expanduser()
    kit = pathlib.Path(args.kit).expanduser()
    l2 = pathlib.Path(args.l2).expanduser()
    report = pathlib.Path(args.report).expanduser()
    steps = [
        [sys.executable, "-X", "utf8", str(_script("01_clean_and_index.py")),
         "--raw", str(raw), "--db", str(db), "--query", args.query],
        [sys.executable, "-X", "utf8", str(_script("02_four_way_match.py")),
         "--db", str(db), "--out", str(report)],
        [sys.executable, "-X", "utf8", str(_script("04_bootstrap_kit.py")),
         "--db", str(db), "--out", str(kit)],
    ]
    for step in steps:
        rc = _run(step)
        if rc != 0:
            return rc
    backfill_script = _script("05_deep_backfill.py")
    if backfill_script.is_file():
        rc = _run([sys.executable, "-X", "utf8", str(backfill_script),
                   "--profiles", str(kit), "--first-pass", str(report),
                   "--db", str(db), "--out", str(l2), "--broad"])
        if rc != 0:
            return rc
    rc = _run([sys.executable, "-X", "utf8", str(_script("03_validate_kit.py")),
               "--target", str(kit), "--strict"])
    payload = _receipt("build", rc == 0, raw=str(raw), db=str(db), kit=str(kit), l2=str(l2), report=str(report))
    path = _write_receipt("build", payload)
    print("BUILD_OK" if rc == 0 else "BUILD_FAIL")
    print("receipt:", path)
    return rc


def retrieval(args: argparse.Namespace) -> int:
    """Build temporal/graph indexes, then run the combined recall query."""
    db = pathlib.Path(args.db).expanduser()
    steps = [
        [sys.executable, "-X", "utf8", str(_script("05_temporal_index.py")), "--db", str(db), "--action", "backfill"],
        [sys.executable, "-X", "utf8", str(_script("06_graph_index.py")), "--db", str(db), "--action", "build", "--rebuild"],
    ]
    for step in steps:
        rc = _run(step)
        if rc != 0:
            return rc
    cmd = [sys.executable, "-X", "utf8", str(_script("07_recall_time_graph.py")), "--db", str(db), "--limit", str(args.limit)]
    if args.as_of:
        cmd += ["--as-of", args.as_of]
    if args.keyword:
        cmd += ["--keyword", args.keyword]
    if args.entity:
        cmd += ["--entity", args.entity]
    if args.hops:
        cmd += ["--hops", str(args.hops)]
    return _run(cmd)


def validate(args: argparse.Namespace) -> int:
    kit = pathlib.Path(args.kit).expanduser()
    cmd = [sys.executable, "-X", "utf8", str(_script("03_validate_kit.py")), "--target", str(kit)]
    if args.strict:
        cmd.append("--strict")
    return _run(cmd)


def verify(args: argparse.Namespace) -> int:
    kit = pathlib.Path(args.kit).expanduser()
    missing = [name for name in KIT_FILES if _kit_actual_name(kit, name) is None]
    if missing:
        print("VERIFY_FAIL")
        print("MISSING:", ", ".join(missing))
        return 1
    return validate(argparse.Namespace(kit=str(kit), strict=bool(args.strict)))


def backfill(args: argparse.Namespace) -> int:
    script = _script("05_deep_backfill.py")
    if not script.is_file():
        print("BACKFILL_MISSING: scripts/05_deep_backfill.py is not in this checkout")
        return 2
    cmd = [sys.executable, "-X", "utf8", str(script)]
    for flag in ["profiles", "first_pass", "db", "out"]:
        value = getattr(args, flag.replace("-", "_"), None)
        if value:
            cmd += ["--" + flag.replace("_", "-"), str(value)]
    if args.apply_signed:
        cmd.append("--apply-signed")
    if args.confirm:
        cmd.append("--confirm")
    if args.broad:
        cmd.append("--broad")
    return _run(cmd)


def package(args: argparse.Namespace) -> int:
    out = pathlib.Path(args.out).expanduser()
    out.parent.mkdir(parents=True, exist_ok=True)
    excluded_dirs = {".git", "work", ".pytest_cache", "__pycache__", "dist"}
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in ROOT.rglob("*"):
            rel = path.relative_to(ROOT)
            if any(part in excluded_dirs for part in rel.parts):
                continue
            if path.is_file():
                zf.write(path, str(rel))
    print("PACKAGE_OK", out)
    print("bytes", out.stat().st_size)
    return 0


def status(args: argparse.Namespace) -> int:
    print("root:", ROOT)
    print("python:", sys.version.split()[0])
    for name in ["raw", "interview", "kit", "reports", "evidence"]:
        folder = WORK / name
        count = len([p for p in folder.iterdir() if p.is_file()]) if folder.is_dir() else 0
        print(f"{name}: {folder} ({count} files)")
    print("scripts:", ", ".join(p.name for p in (ROOT / "scripts").glob("*.py")))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="XH-Dossier one-entry CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("doctor", help="check Python/scripts/templates/work")
    p.set_defaults(func=doctor)

    p = sub.add_parser("init", help="create work dirs and copy the 6 templates")
    p.set_defaults(func=init)

    p = sub.add_parser("demo", help="run the no-third-party sample pipeline")
    p.set_defaults(func=demo)

    p = sub.add_parser("ingest", help="raw -> SQLite FTS5")
    p.add_argument("--raw", default=str(WORK / "raw"))
    p.add_argument("--db", default=str(WORK / "unified_index.db"))
    p.add_argument("--query", default="记错")
    p.set_defaults(func=ingest)

    p = sub.add_parser("match", help="SQLite -> four-way candidates")
    p.add_argument("--db", default=str(WORK / "unified_index.db"))
    p.add_argument("--out", default=str(WORK / "backfill_candidates.md"))
    p.add_argument("--keywords", nargs="*", default=None)
    p.set_defaults(func=match)

    p = sub.add_parser("validate", help="validate a 6-file kit")
    p.add_argument("--kit", default=str(WORK / "kit"))
    p.add_argument("--strict", action="store_true")
    p.set_defaults(func=validate)

    p = sub.add_parser("verify", help="check 6 files exist and validate")
    p.add_argument("--kit", default=str(WORK / "kit"))
    p.add_argument("--strict", action="store_true")
    p.set_defaults(func=verify)

    p = sub.add_parser("bootstrap", help="build six profile drafts from a real chat index")
    p.add_argument("--db", default=str(WORK / "unified_index.db"))
    p.add_argument("--out", default=str(WORK / "kit"))
    p.set_defaults(func=bootstrap)

    p = sub.add_parser("build", help="one-command: raw -> index -> 6 drafts -> L2 proposal -> validate")
    p.add_argument("--raw", default=str(WORK / "raw"))
    p.add_argument("--db", default=str(WORK / "unified_index.db"))
    p.add_argument("--kit", default=str(WORK / "kit"))
    p.add_argument("--l2", default=str(WORK / "layer2"))
    p.add_argument("--report", default=str(WORK / "backfill_candidates.md"))
    p.add_argument("--query", default="记错")
    p.set_defaults(func=build)

    p = sub.add_parser("retrieval", help="build temporal/graph indexes and run recall")
    p.add_argument("--db", default=str(WORK / "unified_index.db"))
    p.add_argument("--as-of", default=None)
    p.add_argument("--keyword", default=None)
    p.add_argument("--entity", default=None)
    p.add_argument("--hops", type=int, default=None, choices=[1, 2])
    p.add_argument("--limit", type=int, default=50)
    p.set_defaults(func=retrieval)

    p = sub.add_parser("backfill", help="run layer-2 deep backfill (if 05 exists)")
    p.add_argument("--profiles", default=None)
    p.add_argument("--first-pass", default=None)
    p.add_argument("--db", default=None)
    p.add_argument("--out", default=None)
    p.add_argument("--apply-signed", action="store_true")
    p.add_argument("--confirm", action="store_true")
    p.add_argument("--broad", action="store_true", help="also propose durable records not cited by the kit")
    p.set_defaults(func=backfill)

    p = sub.add_parser("package", help="build a release zip without .git/work")
    p.add_argument("--out", default=str(ROOT / "dist" / "xh-dossier.zip"))
    p.set_defaults(func=package)

    p = sub.add_parser("status", help="show work dirs and scripts")
    p.set_defaults(func=status)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())

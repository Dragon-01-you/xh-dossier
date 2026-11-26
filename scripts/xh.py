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
import re
import shutil
import sqlite3
import subprocess
import sys
import zipfile
from datetime import datetime, timezone, timedelta

from archive_io import diagnose_missing, encoding_error_message

ROOT = pathlib.Path(__file__).resolve().parent.parent
WORK = ROOT / "work"
TEMPLATES = ROOT / "templates"
SAMPLE_RAW = ROOT / "examples" / "sample_raw"
SAMPLE_INTERVIEW = ROOT / "examples" / "sample_interview"

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
    "09_export_coverage.py",
]
KIT_FILES = [
    "AGENTS.md",
    "00-总入口索引.md",
    "01-身份与当前主线.md",
    "02-核心判断准则.md",
    "03-硬规则与表达黑话.md",
    "04-正反例避坑账.md",
]

# Issue #90: every freshly built draft starts as review_status=pending. Only a
# human `review --confirm` flips it to confirmed; verify / downstream S7 block
# until then. The sidecar lives next to the kit so the gate follows the kit.
REVIEW_STATUS_REL = pathlib.Path("_evidence") / "review.json"
REVIEW_PENDING = "pending_review"
REVIEW_CONFIRMED = "reviewed"


def _review_status_path(kit: pathlib.Path) -> pathlib.Path:
    return kit / REVIEW_STATUS_REL


def _read_review_status(kit: pathlib.Path) -> str:
    path = _review_status_path(kit)
    if not path.is_file():
        return REVIEW_PENDING
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return REVIEW_PENDING
    status = str(data.get("status", REVIEW_PENDING)).strip()
    return status if status in (REVIEW_PENDING, REVIEW_CONFIRMED) else REVIEW_PENDING


def _write_review_status(kit: pathlib.Path, status: str, note: str = "") -> pathlib.Path:
    path = _review_status_path(kit)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"status": status, "at": _now(), "note": note}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def review_block_reason(kit: pathlib.Path) -> str | None:
    """Human-readable blocker when the kit has not been personally confirmed."""
    if _read_review_status(kit) == REVIEW_CONFIRMED:
        return None
    return (
        f"REVIEW_NOT_REVIEWED: 六份档案还没经过本人复核（review_status=pending_review，{kit}）。"
        "下游检索与 S7 三问盲测必须等复核回执落盘后再跑；"
        f"复核命令：py -3.12 -X utf8 scripts/xh.py review --confirm --kit {kit}"
    )


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


def _run_capture(args: list[str]) -> tuple[int, str]:
    """Run a step, echo its output verbatim, and return (exit_code, stdout_text)."""
    print("RUN:", " ".join(args))
    proc = subprocess.run(
        args,
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if proc.stdout:
        print(proc.stdout, end="" if proc.stdout.endswith("\n") else "\n")
    if proc.stderr:
        print(proc.stderr, end="" if proc.stderr.endswith("\n") else "\n", file=sys.stderr)
    print("EXIT:", proc.returncode)
    return proc.returncode, (proc.stdout or "")


def _format_reason_map(reasons: dict[str, int]) -> str:
    if not reasons:
        return "无"
    top = sorted(reasons.items(), key=lambda kv: (-int(kv[1]), kv[0]))[:6]
    return "，".join(f"{k}={v}" for k, v in top)


def _render_build_summary(
    *,
    ingest_out: str,
    match_out: str,
    l2_out: str,
    graph_out: str,
    validate_out: str,
    validate_ok: bool,
    kit_base: pathlib.Path,
    kit_final: pathlib.Path,
    l2_dir: pathlib.Path,
    interview: pathlib.Path | None,
) -> str:
    """Issue #130: Render a 10-second human-readable stage conversion summary."""
    # Step 1: ingest
    m_idx = re.search(r"INDEX_OK\s+total_raw=(\d+)\s+dedup_skipped=(\d+)\s+indexed=(\d+)", ingest_out)
    raw_total = int(m_idx.group(1)) if m_idx else 0
    dedup_skip = int(m_idx.group(2)) if m_idx else 0
    indexed_n = int(m_idx.group(3)) if m_idx else 0

    # Step 2: four-way match
    m_fw = re.search(r"FOUR_WAY_OK\s+records=(\d+)\s+clusters=(\d+)", match_out)
    fw_clusters = int(m_fw.group(2)) if m_fw else 0

    # Step 3: L1 bootstrap stats (read from kit_base/_evidence/build-stats.json)
    stats_file = kit_base / "_evidence" / "build-stats.json"
    bstats: dict[str, object] = {}
    if stats_file.is_file():
        try:
            bstats = json.loads(stats_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            bstats = {}
    user_rows = int(bstats.get("user_rows", 0))
    usable_n = int(bstats.get("usable_records", 0))
    l1_filtered = bstats.get("filtered_by_reason", {}) if isinstance(bstats.get("filtered_by_reason"), dict) else {}
    l1_sections = bstats.get("sections", {}) if isinstance(bstats.get("sections"), dict) else {}
    iv_facts = int(bstats.get("interview_facts", 0))
    iv_warn = str(bstats.get("interview_warning", "") or "")
    highlights = list(bstats.get("highlights", [])) if isinstance(bstats.get("highlights"), list) else []

    # Step 4: L2 backfill
    m_l2 = re.search(
        r"L2_BACKFILL_OK\s+records=(\d+)\s+personal_records=(\d+)\s+candidates=(\d+)\s+dropped=(\d+)\s+cross_ref_L1=(\d+)",
        l2_out,
    )
    l2_personal = int(m_l2.group(2)) if m_l2 else 0
    l2_cands = int(m_l2.group(3)) if m_l2 else 0
    l2_dropped = int(m_l2.group(4)) if m_l2 else 0
    l2_xref = int(m_l2.group(5)) if m_l2 else 0
    l2_reasons: dict[str, int] = {}
    m_dr = re.search(r"dropped_by_reason=(\{.*\})", l2_out)
    if m_dr:
        try:
            l2_reasons = json.loads(m_dr.group(1))
        except json.JSONDecodeError:
            l2_reasons = {}

    # Sample L2 titles/excerpts
    l2_preview: list[str] = []
    l2_md = l2_dir / "l2_candidates.md"
    if l2_md.is_file():
        for ln in l2_md.read_text(encoding="utf-8", errors="replace").splitlines():
            if ln.startswith("- **原文摘录**：> "):
                l2_preview.append(f"[L2待确认] {ln.split('> ', 1)[1][:80]}")
                if len(l2_preview) >= 3:
                    break

    # Step 5: graph
    m_gr = re.search(r"GRAPH_BUILD\s+(\{.*\})", graph_out)
    gr_summary = "已跳过（--skip-retrieval）"
    if m_gr:
        try:
            gd = json.loads(m_gr.group(1))
            gr_summary = f"实体 {gd.get('entities', 0)} 个 / 关系边 {gd.get('edges', 0)} 条（否定拦截 {gd.get('negation_skipped', 0)} 条）"
        except json.JSONDecodeError:
            gr_summary = "已完成"

    # Step 6: validate scorecard lines
    sc_lines = [ln.strip() for ln in validate_out.splitlines() if ln.strip().startswith("- [")]

    l1_out_desc = (
        f"访谈 A 级 {iv_facts} 条；raw B 级（身份 {l1_sections.get('identity', 0)} / "
        f"主线 {l1_sections.get('mainline', 0)} / 准则 {l1_sections.get('principles', 0)} / "
        f"规则 {l1_sections.get('rules', 0)} / 正例 {l1_sections.get('positive', 0)} / "
        f"反例 {l1_sections.get('negative', 0)}）"
    )
    lines = [
        "# XH-Dossier 阶段转化摘要（PIPELINE_SUMMARY）",
        "",
        f"> 生成时间：{_now()} ｜ 交付目录：`{kit_final}` ｜ 严格验收：`{'VALIDATE_OK' if validate_ok else 'VALIDATE_FAIL'}`",
        "",
        "## 一、每步目标与数量转化（输入 → 过滤 → 产出）",
        "",
        "| 步骤 | 设计目标 | 输入数 | 按原因过滤数 | 实际产出 |",
        "|---|---|---|---|---|",
        f"| 1. 冷库清洗入库 | 原始导出只读入 SQLite 并去重 | {raw_total} 条原始记录 | 去重跳过={dedup_skip} | 入库 {indexed_n} 条（四路聚簇 {fw_clusters} 簇） |",
        f"| 2. L1 访谈校准与初稿 | 吸收 A 级访谈、过滤杂句生成 6 份初稿 | {user_rows} 条本人消息"
        + (f" + 访谈输入" if interview else "")
        + f" | {_format_reason_map(l1_filtered)} | 可用 {usable_n} 段 → {l1_out_desc} |",
        f"| 3. L2 差集挖掘 | 找回 6 份档案未覆盖的本人遗漏经验 | {l2_personal} 条本人消息 | 共拦截 {l2_dropped}（{_format_reason_map(l2_reasons)}） | 新增待确认候选 {l2_cands} 条（与 L1 交叉引用 {l2_xref} 条） |",
        f"| 4. 时间线与图索引 | 辅助多跳与双时态溯源检索 | {indexed_n} 条冷库记录 | 仅作辅助检索，不覆写 6 份 | {gr_summary} |",
        f"| 5. 严格结构与语义验收 | 核对出处、占位符、水话、PII 与评分卡 | 6 份档案 | — | {'VALIDATE_OK' if validate_ok else 'VALIDATE_FAIL'} |",
        "",
    ]
    if iv_warn:
        lines += [f"> ⚠️ {iv_warn}", ""]
    if sc_lines:
        lines += ["## 二、评分卡结论", ""] + sc_lines + [""]
    lines += ["## 三、本次挖出的关键条目预览", ""]
    preview = highlights + l2_preview
    if preview:
        for item in preview[:8]:
            lines.append(f"- {item}")
    else:
        lines.append("- （本轮样本较薄，暂无新增预览条目，建议补充访谈或更多导出记录）")
    lines += [
        "",
        "## 四、待本人确认动作清单（机器不代签字）",
        "",
        f"1. 打开 `{kit_final}` 核对带 `[待确认]` 的冲突与候选条目（原文行号在 `_evidence/`）。",
        f"2. 查看 `{l2_dir / 'l2_candidates.md'}` 中 {l2_cands} 条 L2 候选，确认是否亲历、是否值得升格。",
        f"3. 复核无误后由本人执行签字回执：`python -X utf8 scripts/xh.py review --confirm --kit {kit_final}`。",
        "",
    ]
    return "\n".join(lines)


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
    root = (
        pathlib.Path(getattr(args, "root", None)).expanduser()
        if getattr(args, "root", None)
        else ROOT
    )
    scripts_dir = root / "scripts"
    template_dir = root / "templates"
    sample_dir = root / "examples" / "sample_raw"
    work_dir = root / "work"
    errors: list[str] = []
    warnings: list[str] = []
    scripts: dict[str, bool] = {}
    for name in REQUIRED_SCRIPTS:
        scripts[name] = (scripts_dir / name).is_file()
        if not scripts[name]:
            errors.append(f"missing scripts/{name}")
    optional: dict[str, bool] = {}
    for name in OPTIONAL_SCRIPTS:
        optional[name] = (scripts_dir / name).is_file()
        if not optional[name]:
            warnings.append(f"optional scripts/{name} missing")

    template_rels = [f"templates/{name}" for name in KIT_FILES]
    diag = diagnose_missing(root, template_rels)
    templates: dict[str, bool] = {}
    for rel in template_rels:
        name = pathlib.PurePosixPath(rel).name
        templates[name] = _kit_actual_name(template_dir, name) is not None or rel in diag.garbled
    for rel in diag.missing:
        if rel not in diag.garbled:
            errors.append(f"missing template {pathlib.PurePosixPath(rel).name}")
    if diag.garbled:
        errors.append("ENCODING_CORRUPT: " + encoding_error_message(diag).replace("\n", " | "))

    sample_count = 0
    if sample_dir.is_dir():
        sample_count = len([p for p in sample_dir.iterdir() if p.is_file()])
    if sample_count == 0:
        errors.append("examples/sample_raw is missing or empty")

    work_writable = False
    try:
        work_dir.mkdir(parents=True, exist_ok=True)
        probe = work_dir / ".xh-write-probe"
        probe.write_text("ok", encoding="utf-8")
        work_writable = probe.is_file()
        probe.unlink(missing_ok=True)
    except OSError:
        errors.append("work/ is not writable")

    py_ok = sys.version_info >= (3, 11)
    if not py_ok:
        errors.append(f"Python >=3.11 required, got {sys.version.split()[0]}")

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
    payload["root"] = str(root)
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
    payload = _receipt("init", True, work=str(WORK), kit=str(kit), copied=copied,
                       empty_template_note=True)
    path = _write_receipt("init", payload)
    print("INIT_OK")
    print("work:", WORK)
    print("kit:", kit)
    print("copied:", ", ".join(copied) if copied else "(already populated)")
    print("说明：work/kit 现在是空白模板，里面的 <...> 还没填。")
    print("这时直接跑 validate --strict 会报占位符，这不是安装失败。")
    print("下一步：把聊天记录放进 work/raw 后跑 build；或先做 6 个阶段访谈，再校验。")
    print("receipt:", path)
    return 0


def export_setup(args: argparse.Namespace) -> int:
    cmd = [
        sys.executable, "-X", "utf8", str(_script("00_export_wizard.py")),
        "--browser", args.browser,
    ]
    if args.yes:
        cmd.append("--yes")
    if args.download_release:
        cmd.append("--download-release")
    if args.no_afterchat:
        cmd.append("--no-afterchat")
    return _run(cmd)


def demo(args: argparse.Namespace) -> int:
    demo_dir = WORK / "demo"
    if demo_dir.exists():
        # Windows can transiently refuse to remove a directory while a
        # previous demo/antivirus handle is still open. Never make the
        # first-run demo fail because of a stale work/demo; use a fresh
        # timestamped directory as the fallback.
        try:
            shutil.rmtree(demo_dir)
        except OSError:
            demo_dir = WORK / ("demo-" + datetime.now().strftime("%Y%m%d-%H%M%S"))
    demo_dir.mkdir(parents=True, exist_ok=True)
    db = demo_dir / "unified_index.db"
    report = demo_dir / "backfill_candidates.md"
    # The demo is a complete first-run sample: synthetic chat records plus a
    # synthetic 6-stage interview. It must reach a passing scorecard, otherwise
    # `install.ps1 -RunDemo` would print a scary SCORECARD_FAIL on a fresh PC.
    build_args = argparse.Namespace(
        raw=str(SAMPLE_RAW),
        db=str(db),
        kit=str(demo_dir / "kit"),
        l2=str(demo_dir / "layer2"),
        report=str(report),
        interview=str(SAMPLE_INTERVIEW),
        query="记错",
        skip_retrieval=False,
        apply_unsigned=True,
        kit_next=str(demo_dir / "kit_next"),
        enforce_score=True,
    )
    rc = build(build_args)
    payload = _receipt("demo", rc == 0, demo_dir=str(demo_dir), db=str(db),
                       report=str(report), interview=str(SAMPLE_INTERVIEW))
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
    cmd = [sys.executable, "-X", "utf8", str(_script("04_bootstrap_kit.py")),
           "--db", str(db), "--out", str(out)]
    if args.interview:
        cmd += ["--interview", str(pathlib.Path(args.interview).expanduser())]
    return _run(cmd)


def build(args: argparse.Namespace) -> int:
    """One-command chain: raw chat -> index -> match -> 6-file draft -> L2 proposal -> validate."""
    raw = pathlib.Path(args.raw).expanduser()
    db = pathlib.Path(args.db).expanduser()
    kit_base = pathlib.Path(args.kit).expanduser()
    kit = kit_base
    l2 = pathlib.Path(args.l2).expanduser()
    report = pathlib.Path(args.report).expanduser()
    interview = pathlib.Path(args.interview).expanduser() if args.interview else None
    bootstrap_cmd = [sys.executable, "-X", "utf8", str(_script("04_bootstrap_kit.py")),
                      "--db", str(db), "--out", str(kit)]
    if interview is not None:
        bootstrap_cmd += ["--interview", str(interview)]

    rc, ingest_out = _run_capture([
        sys.executable, "-X", "utf8", str(_script("01_clean_and_index.py")),
        "--raw", str(raw), "--db", str(db), "--query", args.query,
    ])
    if rc != 0:
        return rc
    rc, match_out = _run_capture([
        sys.executable, "-X", "utf8", str(_script("02_four_way_match.py")),
        "--db", str(db), "--out", str(report),
    ])
    if rc != 0:
        return rc
    rc, _boot_out = _run_capture(bootstrap_cmd)
    if rc != 0:
        return rc

    l2_out = ""
    backfill_script = _script("05_deep_backfill.py")
    if backfill_script.is_file():
        rc, l2_out = _run_capture([
            sys.executable, "-X", "utf8", str(backfill_script),
            "--profiles", str(kit), "--first-pass", str(report),
            "--db", str(db), "--out", str(l2), "--broad",
        ])
        if rc != 0:
            return rc
    apply_script = _script("08_l2_apply.py")
    if args.apply_unsigned and apply_script.is_file() and (l2 / "l2_profile_patches").is_dir():
        kit_next = pathlib.Path(args.kit_next).expanduser() if args.kit_next else kit.parent / "kit_next"
        rc, _apply_out = _run_capture([
            sys.executable, "-X", "utf8", str(apply_script),
            "--kit", str(kit), "--l2", str(l2), "--out", str(kit_next),
        ])
        if rc != 0:
            return rc
        kit = kit_next

    graph_out = ""
    if not args.skip_retrieval and all(_script(n).is_file() for n in ("05_temporal_index.py", "06_graph_index.py", "07_recall_time_graph.py")):
        for step in (
            [sys.executable, "-X", "utf8", str(_script("05_temporal_index.py")), "--db", str(db), "--action", "backfill"],
            [sys.executable, "-X", "utf8", str(_script("06_graph_index.py")), "--db", str(db), "--action", "build", "--rebuild"],
            [sys.executable, "-X", "utf8", str(_script("07_recall_time_graph.py")), "--db", str(db), "--since", "2026-01-01", "--limit", "5"],
            [sys.executable, "-X", "utf8", str(_script("07_recall_time_graph.py")), "--db", str(db), "--entity", "Python", "--limit", "5"],
            [sys.executable, "-X", "utf8", str(_script("07_recall_time_graph.py")), "--db", str(db), "--keyword", str(args.query), "--limit", "5"],
        ):
            rc, step_out = _run_capture(step)
            if "06_graph_index.py" in step[3]:
                graph_out = step_out
            if rc != 0:
                return rc
    rc, validate_out = _run_capture(
        [sys.executable, "-X", "utf8", str(_script("03_validate_kit.py")),
         "--target", str(kit), "--strict"]
        + (["--enforce-score"] if getattr(args, "enforce_score", False) else [])
    )
    # Issue #90: a fresh draft is always pending personal review; confirmation
    # is a separate human action (`review --confirm`), never an Agent step.
    _write_review_status(kit, REVIEW_PENDING, note="fresh build; pending personal review")

    # Issue #130: render & persist human-readable stage conversion summary.
    summary_text = _render_build_summary(
        ingest_out=ingest_out,
        match_out=match_out,
        l2_out=l2_out,
        graph_out=graph_out,
        validate_out=validate_out,
        validate_ok=(rc == 0),
        kit_base=kit_base,
        kit_final=kit,
        l2_dir=l2,
        interview=interview,
    )
    summary_path = kit_base.parent / "build_summary.md"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(summary_text, encoding="utf-8")
    print(summary_text)
    print("summary:", summary_path)

    # Keep the legacy state names from the ticket: pending_review / reviewed.
    payload = _receipt("build", rc == 0, raw=str(raw), db=str(db), kit=str(kit), l2=str(l2),
                        report=str(report), interview=str(interview) if interview else None,
                        summary=str(summary_path),
                        review_status=REVIEW_PENDING)
    path = _write_receipt("build", payload)
    print("BUILD_OK" if rc == 0 else "BUILD_FAIL")
    print("receipt:", path)
    return rc


def l2_apply(args: argparse.Namespace) -> int:
    script = _script("08_l2_apply.py")
    if not script.is_file():
        print("L2_APPLY_MISSING: scripts/08_l2_apply.py is not in this checkout")
        return 2
    return _run([sys.executable, "-X", "utf8", str(script),
                 "--kit", str(pathlib.Path(args.kit).expanduser()),
                 "--l2", str(pathlib.Path(args.l2).expanduser()),
                 "--out", str(pathlib.Path(args.out).expanduser())])


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
    if args.role and args.role != "all":
        cmd += ["--role", args.role]
    return _run(cmd)


def validate(args: argparse.Namespace) -> int:
    kit = pathlib.Path(args.kit).expanduser()
    cmd = [sys.executable, "-X", "utf8", str(_script("03_validate_kit.py")), "--target", str(kit)]
    if args.strict:
        cmd.append("--strict")
    if args.enforce_score:
        cmd.append("--enforce-score")
    if args.no_scorecard:
        cmd.append("--no-scorecard")
    if getattr(args, "raw_root", None):
        cmd += ["--raw-root", str(args.raw_root)]
    return _run(cmd)


def review(args: argparse.Namespace) -> int:
    """Issue #90: read or flip the personal-review status of a kit."""
    kit = pathlib.Path(args.kit).expanduser()
    if args.confirm:
        if not kit.is_dir():
            print("REVIEW_FAIL: kit directory missing:", kit)
            return 2
        path = _write_review_status(kit, REVIEW_CONFIRMED,
                                     note=args.note or "confirmed by the user")
        payload = _receipt("review", True, kit=str(kit), review_status=REVIEW_CONFIRMED,
                           sidecar=str(path))
        _write_receipt("review", payload)
        print("REVIEW_CONFIRMED:", kit)
        return 0
    status = _read_review_status(kit)
    print(f"REVIEW_STATUS: {status} ({kit})")
    return 0 if status == REVIEW_CONFIRMED else 1


def verify(args: argparse.Namespace) -> int:
    kit = pathlib.Path(args.kit).expanduser()
    missing = [name for name in KIT_FILES if _kit_actual_name(kit, name) is None]
    if missing:
        print("VERIFY_FAIL")
        print("MISSING:", ", ".join(missing))
        return 1
    # Issue #90: structural validity is not personal sign-off. Block downstream
    # use until a human confirms the kit; the message says exactly what to run.
    blocker = review_block_reason(kit)
    if blocker:
        print("VERIFY_BLOCKED_REVIEW")
        print(blocker)
        return 1
    return validate(argparse.Namespace(
        kit=str(kit), strict=bool(args.strict),
        enforce_score=bool(getattr(args, "enforce_score", False)),
        no_scorecard=bool(getattr(args, "no_scorecard", False))))


def blind(args: argparse.Namespace) -> int:
    """Issue #98: build the S7 three-question blind package (read-only six files)."""
    kit = pathlib.Path(args.kit).expanduser()
    blocker = review_block_reason(kit)
    if blocker:
        print("BLIND_BLOCKED_REVIEW")
        print(blocker)
        return 1
    cmd = [sys.executable, "-X", "utf8", str(_script("blind_test.py")),
           "--kit", str(kit), "--out", str(pathlib.Path(args.out).expanduser())]
    if args.score:
        cmd += ["--score", str(pathlib.Path(args.score).expanduser())]
    return _run(cmd)


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


def coverage(args: argparse.Namespace) -> int:
    cmd = [
        sys.executable, "-X", "utf8", str(_script("09_export_coverage.py")),
        "--raw", str(args.raw), "--expected", str(args.expected),
    ]
    if args.manifest:
        cmd += ["--list", str(args.manifest)]
    return _run(cmd)


def _dir_file_count(folder: pathlib.Path) -> tuple[pathlib.Path | None, int]:
    if not folder.is_dir():
        return None, 0
    return folder, len([p for p in folder.iterdir() if p.is_file()])


def status(args: argparse.Namespace) -> int:
    print("root:", ROOT)
    print("python:", sys.version.split()[0])
    for name in ["raw", "interview", "kit", "reports", "evidence"]:
        folder = WORK / name
        count = len([p for p in folder.iterdir() if p.is_file()]) if folder.is_dir() else 0
        print(f"{name}: {folder} ({count} files)")

    # Issue #99: optional custom dataset views. Without these flags the default
    # work/ layout above is unchanged; each flag points status at a separate
    # raw dir / kit dir / db / report so multiple datasets stay distinguishable.
    raw_dir = getattr(args, "raw", None)
    if raw_dir:
        folder, count = _dir_file_count(pathlib.Path(raw_dir).expanduser())
        if folder is None:
            print(f"raw-custom: {raw_dir} (missing)")
        else:
            print(f"raw-custom: {folder} ({count} files)")

    kit_dir = getattr(args, "kit", None)
    if kit_dir:
        folder, count = _dir_file_count(pathlib.Path(kit_dir).expanduser())
        if folder is None:
            print(f"kit-custom: {kit_dir} (missing)")
        else:
            md_count = len([p for p in folder.iterdir() if p.is_file() and p.suffix.lower() == ".md"])
            print(f"kit-custom: {folder} ({count} files, {md_count} markdown)")

    db_path = getattr(args, "db", None)
    if db_path:
        db = pathlib.Path(db_path).expanduser()
        if not db.is_file():
            print(f"db: {db} (missing)")
        else:
            try:
                con = sqlite3.connect(str(db))
                records = con.execute("SELECT count(*) FROM records").fetchone()[0]
                con.close()
                print(f"db: {db} ({records} records, {db.stat().st_size} bytes)")
            except sqlite3.Error as exc:
                print(f"db: {db} (unreadable: {exc})")

    report_path = getattr(args, "report", None)
    if report_path:
        report = pathlib.Path(report_path).expanduser()
        if not report.is_file():
            print(f"report: {report} (missing)")
        else:
            lines = len(report.read_text(encoding="utf-8", errors="replace").splitlines())
            print(f"report: {report} ({lines} lines, {report.stat().st_size} bytes)")

    print("scripts:", ", ".join(p.name for p in (ROOT / "scripts").glob("*.py")))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="XH-Dossier one-entry CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("doctor", help="check Python/scripts/templates/work")
    p.add_argument("--root", default=None, help="仓库根目录（默认脚本所在仓库根目录，与 00_doctor.py --root 口径一致）")
    p.set_defaults(func=doctor)

    p = sub.add_parser("init", help="create work dirs and copy the 6 templates")
    p.set_defaults(func=init)

    p = sub.add_parser("export-setup", help="open official ScriptCat/AfterChat install pages (consent gate)")
    p.add_argument("--browser", choices=["edge", "chrome", "site"], default="edge")
    p.add_argument("--yes", action="store_true", help="confirm consent non-interactively")
    p.add_argument("--download-release", action="store_true", help="download ScriptCat official release instead of opening store")
    p.add_argument("--no-afterchat", action="store_true", help="only open the engine page")
    p.set_defaults(func=export_setup)

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
    p.add_argument("--enforce-score", action="store_true",
                   help="fail when the issue #96 scorecard misses a threshold")
    p.add_argument("--no-scorecard", action="store_true", help="skip the scorecard")
    p.add_argument("--raw-root", default=None,
                   help="raw export dir for A-level quote cross-check (default: auto-detect beside kit)")
    p.set_defaults(func=validate)

    p = sub.add_parser("verify", help="check 6 files exist, review status, and validate")
    p.add_argument("--kit", default=str(WORK / "kit"))
    p.add_argument("--strict", action="store_true")
    p.set_defaults(func=verify)

    p = sub.add_parser("review", help="read or set the personal-review status of a kit")
    p.add_argument("--kit", default=str(WORK / "kit"))
    p.add_argument("--confirm", action="store_true", help="mark the kit as personally confirmed")
    p.add_argument("--note", default=None, help="optional confirmation note")
    p.set_defaults(func=review)

    p = sub.add_parser("bootstrap", help="build six profile drafts from a real chat index")
    p.add_argument("--db", default=str(WORK / "unified_index.db"))
    p.add_argument("--out", default=str(WORK / "kit"))
    p.add_argument("--interview", "--answers", dest="interview", default=None,
                   help="访谈目录（answers.md + stage-N.md；兼容 round-N.md）或单个 answers.md")
    p.set_defaults(func=bootstrap)

    p = sub.add_parser("build", help="one-command: raw -> index -> 6 drafts -> L2 proposal -> validate")
    p.add_argument("--raw", default=str(WORK / "raw"))
    p.add_argument("--db", default=str(WORK / "unified_index.db"))
    p.add_argument("--kit", default=str(WORK / "kit"))
    p.add_argument("--l2", default=str(WORK / "layer2"))
    p.add_argument("--report", default=str(WORK / "backfill_candidates.md"))
    p.add_argument("--query", default="项目", help="keyword used for the final FTS recall step")
    p.add_argument("--interview", "--answers", dest="interview", default=None,
                   help="访谈目录（answers.md + stage-N.md；兼容 round-N.md）或单个 answers.md；"
                        "访谈答案作为 A 级基准入稿，raw 回填只作补证")
    p.add_argument("--skip-retrieval", action="store_true", help="skip the temporal/graph/FTS index step")
    p.add_argument("--apply-unsigned", dest="apply_unsigned", action="store_true", default=True,
                   help="apply L2 candidates as a pending zone in kit_next (default)")
    p.add_argument("--no-l2-apply", dest="apply_unsigned", action="store_false",
                   help="keep the first-pass kit unchanged")
    p.add_argument("--kit-next", default=None,
                   help="output of the unsigned layer-2 pending zone (default: <kit parent>/kit_next)")
    p.add_argument("--enforce-score", action="store_true",
                   help="fail when the issue #96 scorecard misses a threshold (default: advisory)")
    p.set_defaults(func=build)

    p = sub.add_parser("l2-apply", help="apply L2 candidates as an unsigned pending zone")
    p.add_argument("--kit", default=str(WORK / "kit"))
    p.add_argument("--l2", default=str(WORK / "layer2"))
    p.add_argument("--out", default=str(WORK / "kit_next"))
    p.set_defaults(func=l2_apply)

    p = sub.add_parser("retrieval", help="build temporal/graph indexes and run recall")
    p.add_argument("--db", default=str(WORK / "unified_index.db"))
    p.add_argument("--as-of", default=None)
    p.add_argument("--keyword", default=None)
    p.add_argument("--entity", default=None)
    p.add_argument("--hops", type=int, default=None, choices=[1, 2])
    p.add_argument("--limit", type=int, default=50)
    p.add_argument("--role", choices=["user", "assistant", "all"], default="all",
                   help="Filter keyword recall by role; default lists user first (#95).")
    p.set_defaults(func=retrieval)

    p = sub.add_parser("blind", help="S7 three-question blind-test package (issue #98)")
    p.add_argument("--kit", default=str(WORK / "kit"))
    p.add_argument("--out", default=str(WORK / "blind"))
    p.add_argument("--score", default=None, help="filled answer sheet to score")
    p.set_defaults(func=blind)

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

    p = sub.add_parser("coverage", help="reconcile raw export count against session list count (#93)")
    p.add_argument("--raw", default=str(WORK / "raw"))
    p.add_argument("--expected", type=int, required=True)
    p.add_argument("--list", dest="manifest", default=None, help="optional session title manifest")
    p.set_defaults(func=coverage)

    p = sub.add_parser("status", help="show work dirs and scripts; optional custom dataset views (#99)")
    p.add_argument("--raw", default=None, type=pathlib.Path, help="custom raw export dir to count")
    p.add_argument("--kit", default=None, type=pathlib.Path, help="custom kit dir to count")
    p.add_argument("--db", default=None, type=pathlib.Path, help="custom SQLite index to count records")
    p.add_argument("--report", default=None, type=pathlib.Path, help="custom report file to count lines")
    p.set_defaults(func=status)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())

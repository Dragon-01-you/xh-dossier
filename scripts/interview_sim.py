#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Stage 1 访谈脚本层模拟器（Issue #1/#3 修复验收用）。

真实访谈由本地 Agent / 网页 AI 按 ``skills/onboarding-interviewer/SKILL.md``
题库主持；本脚本**不替代真人对话**，只在脚本层把一份脚本化 transcript（JSON）
喂给直接解析自 SKILL.md 的题库，校验三件事：

1. 每道封闭选择题都带一个显式自定义 / 可补充位（题末项）；
2. 用户选自定义位时必须带原话，原话被逐字采纳并进本轮对应的产出文件；
3. 从第 2 轮起滚动采集的正例 / 反例，最终汇总进 ``04-正反例避坑账.md``。

成功输出 ``SIM_OK``（exit 0）；可预期错误给人话提示 + ``SIM_FAIL``（exit 2），
不把 traceback 丢给用户。纯标准库，无第三方依赖。
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
from dataclasses import dataclass, field

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
SKILL_PATH = REPO_ROOT / "skills" / "onboarding-interviewer" / "SKILL.md"

ROUND_RE = re.compile(r"^###\s*第\s*(\d+)\s*轮题库\s*→\s*`([^`]+)`")
QUESTION_RE = re.compile(r"^(\d+)\.\s*\*\*(.+?)\*\*")
OPTION_RE = re.compile(r"^\s+-\s*`([A-Z])`\s+(.+?)\s*$")
CUSTOM_KEYWORDS = ("自定义", "可补充", "手填", "可手写")

KIT_FILES = [
    "AGENTS.md",
    "00-总入口索引.md",
    "01-身份与当前主线.md",
    "02-核心判断准则.md",
    "03-硬规则与表达黑话.md",
    "04-正反例避坑账.md",
]

# Issue #85: identity branches the interview may follow. A transcript may
# carry ``identity`` on any round; unknown values are rejected instead of being
# silently treated as the default "唯一核心项目" path.
IDENTITY_BRANCHES = {"学生", "在职", "多项目并行", "暂无核心项目"}

# Issue #84: per-round product gate outcome. ``reask`` means the round's target
# product was missing and the hoster re-asked once anchored to this round's answer.
PRODUCT_GATES = {"ok", "reask"}


class SimError(Exception):
    """可预期的人话错误，直接转成 exit 2。"""


@dataclass
class Option:
    letter: str
    text: str
    is_custom: bool


@dataclass
class Question:
    index: int
    text: str
    options: list[Option] = field(default_factory=list)

    @property
    def open_question(self) -> bool:
        return not self.options

    @property
    def custom_option(self) -> Option | None:
        return self.options[-1] if self.options and self.options[-1].is_custom else None


@dataclass
class Round:
    index: int
    target_file: str
    questions: list[Question] = field(default_factory=list)


def _is_custom_option(text: str) -> bool:
    return any(keyword in text for keyword in CUSTOM_KEYWORDS)


def parse_question_bank(skill_text: str) -> list[Round]:
    """Parse the 6-round question bank out of SKILL.md.

    Closed questions have ``- `X` ...`` option lines; questions whose body is
    only an italic open prompt are treated as open questions.
    """
    rounds: list[Round] = []
    current_round: Round | None = None
    current_question: Question | None = None

    for raw_line in skill_text.splitlines():
        round_match = ROUND_RE.match(raw_line)
        if round_match:
            current_round = Round(
                index=int(round_match.group(1)),
                target_file=round_match.group(2).strip(),
            )
            rounds.append(current_round)
            current_question = None
            continue

        if current_round is None:
            continue

        question_match = QUESTION_RE.match(raw_line)
        if question_match:
            current_question = Question(
                index=int(question_match.group(1)),
                text=question_match.group(2).strip(),
            )
            current_round.questions.append(current_question)
            continue

        option_match = OPTION_RE.match(raw_line)
        if option_match and current_question is not None:
            letter, text = option_match.group(1), option_match.group(2).strip().rstrip("。；")
            current_question.options.append(
                Option(letter=letter, text=text, is_custom=_is_custom_option(text))
            )
            continue

    if len(rounds) != 6:
        raise SimError(f"题库解析异常：应解析出 6 轮，实际 {len(rounds)} 轮。")
    return rounds


def _validate_bank_contract(rounds: list[Round]) -> None:
    """Static contract: every closed question ends with an explicit custom slot."""
    for rnd in rounds:
        for q in rnd.questions:
            if q.open_question:
                continue
            if q.custom_option is None:
                letters = "/".join(o.letter for o in q.options)
                raise SimError(
                    f"第 {rnd.index} 轮题 {q.index} 缺少自定义 / 可补充位"
                    f"（现有选项：{letters}）。"
                )


def run_interview(skill_text: str, transcript: dict) -> dict:
    """Drive the 6-round interview against a scripted transcript.

    Returns a result dict with per-round records, rendered kit files, and the
    collected cases. Raises :class:`SimError` on any contract violation.
    """
    rounds = parse_question_bank(skill_text)
    _validate_bank_contract(rounds)

    t_rounds = transcript.get("rounds")
    if not isinstance(t_rounds, list) or len(t_rounds) != 6:
        raise SimError(f"transcript 必须包含 6 轮回答，实际 {len(t_rounds) if isinstance(t_rounds, list) else '非列表'}。")

    records: list[dict] = []
    collected_cases: list[dict] = []
    kit_lines: dict[str, list[str]] = {fname: [] for fname in KIT_FILES}

    for bank_round, t_round in zip(rounds, t_rounds):
        answers = {
            int(a["question"]): a
            for a in t_round.get("answers", [])
            if isinstance(a, dict) and "question" in a
        }

        identity = str(t_round.get("identity", "")).strip()
        if identity and identity not in IDENTITY_BRANCHES:
            raise SimError(
                f"第 {bank_round.index} 轮身份分支「{identity}」不在已知分支 "
                f"{sorted(IDENTITY_BRANCHES)} 中。"
            )

        product_gate = str(t_round.get("product_gate", "ok")).strip() or "ok"
        if product_gate not in PRODUCT_GATES:
            raise SimError(
                f"第 {bank_round.index} 轮产物门禁「{product_gate}」须为 "
                f"{sorted(PRODUCT_GATES)}。"
            )

        carryover = str(t_round.get("carryover", "")).strip()
        round_lines: list[str] = []
        adopted_customs: list[str] = []
        closed_summary: list[str] = []

        if identity:
            round_lines.append(f"- 身份分支：{identity}")
        if carryover:
            round_lines.append(f"- 带入上一轮要点：{carryover}")
        if product_gate == "reask":
            round_lines.append("- 产物门禁：本轮目标产物未拿全，已基于本轮回答重问一次")

        for question in bank_round.questions:
            ans = answers.get(question.index)

            if question.open_question:
                free_text = str((ans or {}).get("text", "")).strip()
                round_lines.append(f"- 题{question.index}（开放题）：{free_text or '（未填写）'}")
                continue

            if ans is None:
                round_lines.append(f"- 题{question.index}：未作答")
                closed_summary.append(f"题{question.index} 无回答")
                continue

            choice = str(ans.get("choice", "")).strip().upper()
            option = next((o for o in question.options if o.letter == choice), None)
            if option is None:
                raise SimError(
                    f"第 {bank_round.index} 轮题 {question.index}：选项 {choice or '（空）'} "
                    f"不在题库 {[o.letter for o in question.options]} 中。"
                )

            line = f"- 题{question.index}：选 {choice} {option.text}"
            if option.is_custom:
                custom = str(ans.get("custom", "")).strip()
                if not custom:
                    raise SimError(
                        f"第 {bank_round.index} 轮题 {question.index}：选了自定义位 {choice}，"
                        "但没有填写自填原话（custom 为空）。"
                    )
                adopted_customs.append(custom)
                line += f"\n  - 自定义原话（逐字采纳进本轮档案）：{custom}"
            round_lines.append(line)
            closed_summary.append(
                f"题{question.index} 选 {choice}"
                + (f"（自定义位 {option.letter}，原话已采纳）" if option.is_custom else "")
            )

        cases = t_round.get("cases", [])
        if not isinstance(cases, list):
            raise SimError(f"第 {bank_round.index} 轮 cases 必须是列表。")
        positive = negative = 0
        for case in cases:
            kind = case.get("kind")
            text = str(case.get("text", "")).strip()
            if kind not in ("positive", "negative") or not text:
                raise SimError(
                    f"第 {bank_round.index} 轮案例格式错误：kind 须为 positive/negative 且 text 非空。"
                )
            collected_cases.append({"round": bank_round.index, "kind": kind, "text": text})
            if kind == "positive":
                positive += 1
            else:
                negative += 1

        notes = str(t_round.get("notes", "")).strip()
        if notes:
            round_lines.append(f"- 本轮补充说明：{notes}")

        kit_lines[bank_round.target_file].extend(round_lines)
        records.append(
            {
                "round": bank_round.index,
                "target_file": bank_round.target_file,
                "closed_summary": closed_summary,
                "adopted_customs": adopted_customs,
                "positive": positive,
                "negative": negative,
                "identity": identity,
                "product_gate": product_gate,
                "carryover": carryover,
            }
        )

    positives = [c for c in collected_cases if c["kind"] == "positive"]
    negatives = [c for c in collected_cases if c["kind"] == "negative"]

    kit: dict[str, str] = {}
    for fname, lines in kit_lines.items():
        header = f"# {fname}（脚本层模拟访谈产出）\n"
        if fname == "04-正反例避坑账.md":
            body = ["## 一、正例 · 确实管用必须保留的做法"]
            body += [f"- [第 {c['round']} 轮] {c['text']}" for c in positives] or ["- （本轮模拟未采集到正例）"]
            body.append("\n## 二、反例 · 一犯再犯必须当场喊停的坑")
            body += [f"- [第 {c['round']} 轮] {c['text']}" for c in negatives] or ["- （本轮模拟未采集到反例）"]
            kit[fname] = header + "\n".join(body) + "\n"
        else:
            kit[fname] = header + "\n".join(lines) + "\n"

    return {"records": records, "kit": kit, "cases": collected_cases}


def _print_report(result: dict) -> None:
    for rec in result["records"]:
        print(
            f"第 {rec['round']} 轮 -> {rec['target_file']} | "
            f"自定义采纳 {len(rec['adopted_customs'])} 条 | "
            f"正例 {rec['positive']} / 反例 {rec['negative']}"
        )
        for item in rec["closed_summary"]:
            print(f"    - {item}")
        for custom in rec["adopted_customs"]:
            print(f"    - 原话采纳：{custom}")
    positives = [c for c in result["cases"] if c["kind"] == "positive"]
    negatives = [c for c in result["cases"] if c["kind"] == "negative"]
    print(f"汇总进 04 避坑账：正例 {len(positives)} 条，反例 {len(negatives)} 条")


def main() -> int:
    parser = argparse.ArgumentParser(description="脚本层 6 轮访谈模拟器（验收 Issue #1/#3 修复）。")
    parser.add_argument("--transcript", required=True, type=pathlib.Path, help="脚本化访谈 JSON")
    parser.add_argument("--out", required=True, type=pathlib.Path, help="模拟产出 6 份档案的目录")
    parser.add_argument("--root", type=pathlib.Path, default=REPO_ROOT, help="仓库根目录")
    args = parser.parse_args()

    try:
        skill_path = args.root / "skills" / "onboarding-interviewer" / "SKILL.md"
        skill_text = skill_path.read_text(encoding="utf-8")
        transcript = json.loads(args.transcript.read_text(encoding="utf-8"))
        result = run_interview(skill_text, transcript)

        args.out.mkdir(parents=True, exist_ok=True)
        for fname, content in result["kit"].items():
            (args.out / fname).write_text(content, encoding="utf-8")

        _print_report(result)
        print("SIM_OK")
        return 0
    except SimError as exc:
        print(f"SIM_FAIL: {exc}")
        return 2
    except FileNotFoundError as exc:
        print(f"SIM_FAIL: 缺少文件：{exc.filename}")
        return 2
    except json.JSONDecodeError as exc:
        print(f"SIM_FAIL: transcript JSON 解析失败：{exc.msg}（行 {exc.lineno}）")
        return 2
    except Exception as exc:  # noqa: BLE001 - 兜底，不把 traceback 丢给用户
        print(f"SIM_FAIL: 未预期错误：{type(exc).__name__}: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

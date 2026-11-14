#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Typst 前端回归测试（只到 S0.5，不需要 Word / MathType，秒级）。

    python tests/run_typ_tests.py
    python tests/run_typ_tests.py -k symbols

断言不看肉眼：每个 .typ 用例对应一类**历史上真实踩过**的坑，检查转出来的
LaTeX 里有没有那几种"MathType 会静默画错"的写法。

    01-basic      行内/行间/多行对齐/分式          别把 aligned 弄丢
    02-symbols    ° ± ≤ 10^-2 mat cases op         别产出 {^} / ^{-}N
    03-structure  标题/列表/表格/代码/链接/注释     别把结构或注释里的 $ 当公式
    04-cjk        中文 + 手写标题块 + 长公式       标题取可见的、行结构别塌
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SCRIPTS = ROOT / "scripts"
CASES = HERE / "cases"

B = "\\"
FORBIDDEN = ["{^", "{_", B + "backslash", B + "text{T }"]

EXPECT = {
    "typ-01-basic": dict(math_total=6, min_block=2,
                         must=["\\begin{aligned}", "\\section{", "\\subsection{"],
                         title="基础公式"),
    "typ-02-symbols": dict(math_total=12, min_block=0,
                           must=["\\circ", "\\pm", "\\leq", "\\begin{bmatrix}",
                                 "\\operatorname{Re}", "\\mathbf{A}", "\\mathcal{F}"],
                           title="符号与矩阵"),
    "typ-03-structure": dict(math_total=3, min_block=0,
                             must=["\\section{", "\\subsection{", "\\subsubsection{",
                                   "\\begin{longtable}", "\\texttt{", "\\href{"],
                             title=None),
    "typ-04-cjk": dict(math_total=5, min_block=1,
                       must=["\\begin{aligned}", "\\section{", "\\textbf{族}"],
                       title="当前进展说明"),
}


def run_case(name: str) -> tuple[bool, list[str]]:
    src = CASES / f"{name}.typ"
    if not src.exists():
        return False, [f"用例不存在: {src}"]
    with tempfile.TemporaryDirectory(prefix="typtest_") as td:
        out = Path(td) / "paper.tex"
        rep = Path(td) / "report.json"
        r = subprocess.run(
            [sys.executable, str(SCRIPTS / "typ2tex.py"), str(src),
             "-o", str(out), "--report", str(rep)],
            capture_output=True, text=True, encoding="utf-8", errors="replace")
        if r.returncode != 0:
            return False, [f"typ2tex 失败（{r.returncode}）：{(r.stderr or r.stdout)[-400:]}"]
        tex = out.read_text(encoding="utf-8")
        info = json.loads(rep.read_text(encoding="utf-8"))

    exp = EXPECT.get(name, {})
    errs: list[str] = []

    if "math_total" in exp and info["math_total"] != exp["math_total"]:
        errs.append(f"公式条数 {info['math_total']} != {exp['math_total']}")
    if info.get("problems"):
        errs.append(f"有公式没过校验: {info['problems'][:3]}")
    if exp.get("min_block") and info["math_block"] < exp["min_block"]:
        errs.append(f"行间公式 {info['math_block']} < {exp['min_block']}")

    for bad in FORBIDDEN:
        if bad in tex:
            errs.append(f"出现禁用写法 {bad!r}（MathType 会假成功）")
    if tex.count("{") != tex.count("}"):
        errs.append(f"花括号不平衡 {tex.count('{')} / {tex.count('}')}")

    for must in exp.get("must", []):
        if must not in tex:
            errs.append(f"缺少 {must!r}")

    if exp.get("title") and info.get("title") != exp["title"]:
        errs.append(f"标题取了 {info.get('title')!r}，应为 {exp['title']!r}")

    # 注释里的 $ 不能被当公式：只有注释的那一行不该贡献公式
    if name == "typ-03-structure" and "not math" in tex and "$not math$" in tex:
        errs.append("注释里的 $ 被当成公式了")

    return not errs, errs


def main() -> int:
    ap = argparse.ArgumentParser(description="Typst 前端回归测试")
    ap.add_argument("-k", help="只跑名字里含该子串的用例")
    a = ap.parse_args()

    names = sorted(EXPECT)
    if a.k:
        names = [n for n in names if a.k in n]
    failed = 0
    for n in names:
        ok, errs = run_case(n)
        print(f"  {'PASS' if ok else 'FAIL'}  {n}")
        for e in errs:
            print(f"        - {e}")
        failed += 0 if ok else 1
    print(f"\n{len(names) - failed}/{len(names)} 通过")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

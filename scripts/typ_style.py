#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""从 Typst 源里读版式，生成 pandoc 参考模板 reference.docx。

    python typ_style.py paper.typ -o build/reference.docx [--pdf 编译好的.pdf]

Typst 的版式是**写在源文件里**的，不需要编译再去 PDF 里量：

    #set page(paper: "a4", margin: (x: 2.2cm, top: 2.5cm, bottom: 2.3cm))
    #set text(font: ("Times New Roman", "SimSun"), size: 10.5pt)
    #set par(leading: 0.78em, first-line-indent: (amount: 2em, all: true))
    #show heading.where(level: 1): set text(size: 17pt)

所以纸张、边距、字号、缩进、标题层级都能直接读到。只有两件事 Typst 和 Word
的语义对不上，要另想办法：

* **行距**：Typst 的 `leading` 是"行间额外空隙"，不等于 Word 的行距磅值。
  这里用一个经验换算 `line = size * (1 + 0.30 * leading)`（10.5pt/0.78em
  → 13.0pt，与实测一致），并把换算结果写进 style.json 便于复核；
* **标题字号**：多数稿子用 `#show heading…` 显式指定，读不到就按比例推。

给了 `--pdf`（自己编好的那份）就用实测值覆盖行距与标题字号——量出来的永远
比推出来的准，但**边距仍以源文件为准**，因为 PDF 的文字外接框会比版心略宽。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from make_reference_docx import DEFAULTS, build_reference  # noqa: E402

LEN = re.compile(r"(-?\d+(?:\.\d+)?)\s*(cm|mm|pt|em|in)")
PAPERS = {
    "a4": (21.0, 29.7),
    "us-letter": (21.59, 27.94),
    "letter": (21.59, 27.94),
    "a5": (14.8, 21.0),
    "a3": (29.7, 42.0),
}


# --------------------------------------------------------------------------
# 小工具：从 `#set xxx( ... )` 里取参数表
# --------------------------------------------------------------------------
def grab_call(src: str, name: str) -> str | None:
    """取 `#set <name>(...)` 括号里的内容（支持嵌套括号与字符串）。"""
    m = re.search(r"#set\s+" + re.escape(name) + r"\s*\(", src)
    if not m:
        m = re.search(r"#show\s+[^\n]*" + re.escape(name) + r"\s*:\s*set\s+" + re.escape(name) + r"\s*\(", src)
    if not m:
        return None
    open_i = src.index("(", m.start())
    i = open_i
    depth = 0
    while i < len(src):
        ch = src[i]
        if ch == '"':
            i += 1
            while i < len(src) and src[i] != '"':
                i += 2 if src[i] == "\\" else 1
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return src[open_i + 1:i]
        i += 1
    return None


def to_cm(tok: str) -> float | None:
    m = LEN.search(tok)
    if not m:
        return None
    v, unit = float(m.group(1)), m.group(2)
    return {"cm": v, "mm": v / 10, "pt": v / 28.3465, "in": v * 2.54, "em": None}[unit]


def to_pt(tok: str, size: float) -> float | None:
    m = LEN.search(tok)
    if not m:
        return None
    v, unit = float(m.group(1)), m.group(2)
    if unit == "pt":
        return v
    if unit == "em":
        return v * size
    if unit == "cm":
        return v * 28.3465
    if unit == "mm":
        return v * 2.83465
    if unit == "in":
        return v * 72.0
    return None


def paren_body(args: str, key: str) -> str | None:
    """从参数表里取 `key: (...)` 的括号内容。"""
    m = re.search(r"\b" + key + r"\s*:\s*\(", args)
    if not m:
        return None
    i = m.end() - 1
    depth = 0
    while i < len(args):
        if args[i] == "(":
            depth += 1
        elif args[i] == ")":
            depth -= 1
            if depth == 0:
                return args[m.end():i]
        i += 1
    return None


def key_value(args: str, key: str) -> str | None:
    m = re.search(r"\b" + key + r"\s*:\s*([^,()]+)", args)
    return m.group(1).strip() if m else None


# --------------------------------------------------------------------------
# 解析
# --------------------------------------------------------------------------
def parse_typst(src: str) -> dict:
    spec = dict(DEFAULTS)

    # --- 字号 / 字体
    text_args = grab_call(src, "text") or ""
    size = to_pt(key_value(text_args, "size") or "", 10.0) or DEFAULTS["size"]
    spec["size"] = round(size, 2)
    fonts = re.findall(r'"([^"]+)"', key_value(text_args, "font") or "")
    if fonts:
        latin = [f for f in fonts if not re.search(r"[\u4e00-\u9fff]|Sim|Song|Hei|Kai|Ming|YaHei", f)]
        cjk = [f for f in fonts if f not in latin]
        if latin:
            spec["font"] = latin[0]
        if cjk:
            spec["east"] = cjk[0]

    # --- 纸张 / 边距
    page_args = grab_call(src, "page") or ""
    paper = key_value(page_args, "paper")
    if paper:
        paper = paper.strip('"')
        spec["paper"] = "a4" if paper == "a4" else ("letter" if "letter" in paper else "a4")
    margin = paren_body(page_args, "margin")
    if margin is None:
        margin = key_value(page_args, "margin")
    if margin:
        vals: dict[str, float] = {}
        if ":" in margin:                       # (x: 2.2cm, top: 2.5cm, …)
            for part in re.split(r",(?![^()]*\))", margin):
                if ":" in part:
                    k, v = part.split(":", 1)
                    cm = to_cm(v)
                    if cm is not None:
                        vals[k.strip()] = cm
        else:
            cm = to_cm(margin)
            if cm is not None:
                vals = {k: cm for k in ("top", "bottom", "left", "right")}
        if vals:
            x = vals.get("x", vals.get("left", DEFAULTS["margins"][2]))
            top = vals.get("top", x)
            bottom = vals.get("bottom", x)
            left = vals.get("left", x)
            right = vals.get("right", x)
            spec["margins"] = (round(top, 2), round(bottom, 2), round(left, 2), round(right, 2))

    # --- 行距 / 首行缩进
    par_args = grab_call(src, "par") or ""
    leading = key_value(par_args, "leading") or ""
    lead_em = LEN.search(leading)
    lead_em = float(lead_em.group(1)) if lead_em and lead_em.group(2) == "em" else 0.65
    spec["line"] = round(spec["size"] * (1 + 0.30 * lead_em), 1)

    indent = paren_body(par_args, "first-line-indent")
    if indent is None:
        indent = key_value(par_args, "first-line-indent")
    if indent:
        amount = key_value(indent, "amount") or indent
        pt = to_pt(amount, spec["size"])
        if pt:
            spec["indent"] = round(pt, 1)

    # --- 标题字号（#show heading.where(level: N): set text(size: Xpt)）
    sizes = list(DEFAULTS["heading_sizes"])
    for m in re.finditer(
            r"#show\s+heading\.where\(\s*level:\s*(\d)\s*\)\s*:\s*set\s+text\(([^)]*)\)", src):
        lvl = int(m.group(1))
        pt = to_pt(key_value(m.group(2), "size") or "", spec["size"])
        if pt and 1 <= lvl <= 4:
            sizes[lvl - 1] = round(pt, 1)
    spec["heading_sizes"] = tuple(sizes)

    spec["cjk"] = bool(re.search(r"[\u4e00-\u9fff]", src))
    return spec


def calibrate(spec: dict, pdf: Path) -> dict:
    """用编译好的 PDF 覆盖行距与标题字号（边距仍以源为准）。"""
    try:
        from learn_style import measure_pdf
    except Exception as exc:                    # noqa: BLE001
        print(f"！读不了 PDF（{exc}），只用源文件推断")
        return spec
    try:
        m = measure_pdf(pdf)
    except Exception as exc:                    # noqa: BLE001
        print(f"！量 PDF 失败（{exc}），只用源文件推断")
        return spec
    for key in ("line", "heading_sizes", "caption_size"):
        if m.get(key):
            spec[key] = m[key]
    print(f"  用 PDF 校准：行距 {spec['line']}pt / 标题 {spec['heading_sizes']}")
    return spec


def main() -> int:
    ap = argparse.ArgumentParser(description="从 .typ 推断版式并生成 reference.docx")
    ap.add_argument("typ")
    ap.add_argument("-o", "--out", default="reference.docx")
    ap.add_argument("--pdf", help="自己的编译产物，用来校准行距与标题字号")
    ap.add_argument("--json", dest="json_out", help="把推断结果写成 json 便于复核")
    a = ap.parse_args()

    src = Path(a.typ).read_text(encoding="utf-8", errors="replace")
    spec = parse_typst(src)
    if a.pdf:
        spec = calibrate(spec, Path(a.pdf))
    if a.json_out:
        Path(a.json_out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.json_out).write_text(json.dumps(spec, ensure_ascii=False, indent=1),
                                    encoding="utf-8")
    out = build_reference(Path(a.out), spec)
    print(f"纸张 {spec['paper']} / 边距 {spec['margins']} cm / "
          f"正文 {spec['size']}pt / 行距 {spec['line']}pt / 缩进 {spec['indent']}pt")
    print(f"标题字号 {spec['heading_sizes']} / 字体 {spec['font']} + {spec['east']}")
    print(f"→ {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

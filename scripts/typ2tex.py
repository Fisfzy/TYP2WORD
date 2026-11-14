#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Typst → LaTeX（给 L2Word / MathType 流水线用的那一档）。

    python typ2tex.py paper.typ -o build/paper.tex

它只做一件事：**把 .typ 变成一份"公式已经是对的形式"的 .tex**，后续
prep_tex / build_docx / to_mathtype / verify 原样复用。

关键顺序（别改）
----------------
1. 先把 `$…$` 全部抽出来换成纯 token 占位符；
2. 再把占位符版 .typ 丢给 pandoc —— 此时 pandoc **看不见任何数学**，
   它只负责骨架（标题层级、段落、列表、图片、表格）；
3. 把占位符换回 `$…$` / `\\[…\\]`，公式内容来自 typ_math.py 的逐格转译。

这样做的好处是实测过的：同一份 335 公式的稿子，把数学抽走后 pandoc 输出里
`\\frac`/`\\sum`/`\\begin{array}`/`{^` 的出现次数全部为 0，而标题、图片、
longtable 一个不少。
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import typ_math  # noqa: E402

TOKEN = "MTXZ%04d"

DOC_TITLE = re.compile(r"#set\s+document\s*\(([^)]*)\)", re.S)
TITLE_KV = re.compile(r'title\s*:\s*"([^"]*)"')
IMG_HEIGHT = re.compile(r",\s*height\s*=\s*\\textheight\s*,\s*keepaspectratio")


def find_balanced(s: str, i: int, op: str = "(", cl: str = ")") -> int:
    """s[i] == op，返回配对 cl 之后的下标。"""
    depth = 0
    n = len(s)
    while i < n:
        if s[i] == "\\":
            i += 2
            continue
        if s[i] == op:
            depth += 1
        elif s[i] == cl:
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return n


TITLE_TEXT = re.compile(r"#text\(\s*size:\s*(\d+(?:\.\d+)?)pt")


def detect_title(src: str) -> tuple[str | None, str]:
    """标题优先取**可见**的那个（居中大字号），不行再退到 document(title:)。

    Typst 的 `#set document(title:)` 是 PDF 元数据，可以跟正文里印的标题
    完全不同（本机实测那份稿子：元数据是"程序说明"，正文印的是"当前进展说明"）。
    """
    for m in TITLE_TEXT.finditer(src):
        if float(m.group(1)) < 16:
            continue
        open_paren = src.index("(", m.start())
        close = find_balanced(src, open_paren)
        j = close
        while j < len(src) and src[j] in " \t\r\n":
            j += 1
        if j >= len(src) or src[j] != "[":
            continue
        end = find_balanced(src, j, "[", "]")
        text = src[j + 1:end - 1].strip().strip("[]")
        if text and "\n" not in text and len(text) <= 80:
            return text, "visible-block"
    meta = extract_title(src)
    return meta, ("document-meta" if meta else "")


def pandoc_convert(typ: Path, out: Path, pandoc: str = "pandoc") -> None:
    r = subprocess.run(
        [pandoc, "-f", "typst", "-t", "latex", str(typ), "-o", str(out)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if r.returncode != 0:
        raise SystemExit(f"pandoc 失败（{r.returncode}）：{(r.stderr or '').strip()[:500]}")


def extract_title(src: str) -> str | None:
    """`#set document(title: "…")` 是 Typst 自己声明的标题，比猜居中大字可靠。"""
    m = DOC_TITLE.search(src)
    if not m:
        return None
    t = TITLE_KV.search(m.group(1))
    return t.group(1).strip() if t else None


def strip_braced(s: str, i: int) -> int:
    """s[i] 应为 '{'，返回匹配 '}' 之后的下标。"""
    depth = 0
    while i < len(s):
        if s[i] == "\\":
            i += 2
            continue
        if s[i] == "{":
            depth += 1
        elif s[i] == "}":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return len(s)


def unwrap_texorpdfstring(tex: str) -> str:
    """pandoc 给标题里的小代码块生成 \\texorpdfstring{A}{B}，docx 只认 A。"""
    out = []
    i = 0
    key = "\\texorpdfstring{"
    while True:
        j = tex.find(key, i)
        if j < 0:
            out.append(tex[i:])
            break
        out.append(tex[i:j])
        a_end = strip_braced(tex, j + len(key) - 1)
        first = tex[j + len(key):a_end - 1]
        b_start = a_end
        while b_start < len(tex) and tex[b_start] in " \t\r\n":
            b_start += 1
        b_end = strip_braced(tex, b_start)
        out.append(first)
        i = b_end
    return "".join(out)


def strip_manual_title_block(tex: str, title: str | None) -> str:
    """Typst 里常见的"居中大字号 + 横线"手写标题块，正文里不该再出现一次。"""
    if title:
        esc = re.escape(title)
        for pat in (
            r"\A\s*\{\\textbf\{" + esc + r"\}\}\s*\n",
            r"\A\s*\\textbf\{" + esc + r"\}\s*\n",
            r"\A\s*" + esc + r"\s*\n\n",
        ):
            tex = re.sub(pat, "", tex, count=1)
    # 横线：\begin{center}\rule{..}{..}\end{center}
    while True:
        new = re.sub(r"\A\s*\\begin\{center\}\s*\\rule\{[^}]*\}\{[^}]*\}\s*\\end\{center\}\s*\n",
                     "", tex, count=1)
        if new == tex:
            break
        tex = new
    return tex


def convert(src: Path, out: Path, *, pandoc: str = "pandoc",
            report: Path | None = None, strict: bool = False,
            no_title: bool = False) -> dict:
    text = src.read_text(encoding="utf-8", errors="replace")
    spans = typ_math.scan_math(text)
    conv = typ_math.translate_many([s.body for s in spans], pandoc=pandoc)

    problems = [(k + 1, c.problems) for k, c in enumerate(conv) if c.problems]

    # 1) 遮住数学
    pieces: list[str] = []
    last = 0
    for k, s in enumerate(spans):
        pieces.append(text[last:s.start])
        pieces.append(TOKEN % k)
        last = s.end
    pieces.append(text[last:])
    masked = "".join(pieces)

    title, title_src = (None, "") if no_title else detect_title(text)
    with tempfile.TemporaryDirectory(prefix="typ2tex_") as td:
        tmp_typ = Path(td) / "masked.typ"
        tmp_tex = Path(td) / "masked.tex"
        tmp_typ.write_text(masked, encoding="utf-8")
        pandoc_convert(tmp_typ, tmp_tex, pandoc)
        tex = tmp_tex.read_text(encoding="utf-8", errors="replace")

    # 2) 换回真公式
    for k, c in enumerate(conv):
        token = TOKEN % k
        if token not in tex:
            problems.append((k + 1, ["占位符在 pandoc 输出里丢失"]))
            continue
        body = ("\\[" + c.latex + "\\]") if c.is_block else ("$" + c.latex + "$")
        tex = tex.replace(token, body)

    left = sum(tex.count(TOKEN % k) for k in range(len(conv)))
    if left:
        problems.append((0, [f"仍有 {left} 个占位符没换回来"]))

    # 3) 收尾：pandoc 给图片加的高度参数在 Word 里会把图顶出一页
    tex = IMG_HEIGHT.sub("", tex)
    tex = unwrap_texorpdfstring(tex)

    # 4) 标题：用 Typst 自己声明的 document(title:)
    if title:
        tex = strip_manual_title_block(tex, title)
        if "\\title{" not in tex:
            tex = "\\title{" + title + "}\n\\maketitle\n\n" + tex.lstrip("\n")

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(tex, encoding="utf-8", newline="\n")

    info = {
        "src": str(src),
        "out": str(out),
        "math_total": len(spans),
        "math_block": sum(1 for s in spans if s.is_block),
        "title": title,
        "title_source": title_src,
        "problems": [{"index": i, "issues": p} for i, p in problems],
    }
    if report:
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(json.dumps(info, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"公式 {info['math_total']} 条（行间 {info['math_block']}）→ {out.name}")
    if title:
        print(f"标题（{title_src}）：{title}")
    if problems:
        print(f"！{len(problems)} 条公式需要人工看一眼：")
        for i, p in problems[:10]:
            print(f"    #{i}: {'; '.join(p)}")
        if strict:
            raise SystemExit("--strict：存在未通过的公式，停止")
    return info


def main() -> int:
    ap = argparse.ArgumentParser(description="Typst → LaTeX（公式逐格转译）")
    ap.add_argument("typ")
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--report", help="把统计与问题清单写成 json")
    ap.add_argument("--pandoc", default="pandoc")
    ap.add_argument("--strict", action="store_true", help="有公式没过校验就停止")
    ap.add_argument("--no-title", action="store_true", help="不要自动生成 \\title")
    a = ap.parse_args()
    src = Path(a.typ).resolve()
    if not src.exists():
        print(f"文件不存在: {src}")
        return 1
    convert(src, Path(a.out), pandoc=a.pandoc, report=Path(a.report) if a.report else None,
            strict=a.strict, no_title=a.no_title)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

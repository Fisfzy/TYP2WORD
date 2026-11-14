#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Typst 数学 → LaTeX（可直接喂给 MathType 的那一档）。

为什么不能把整篇 `.typ` 一把丢给 pandoc
--------------------------------------
`pandoc -f typst -t latex` 在正文层面够用，但在数学层面有三类硬伤，而且
**都不报错**——要么产出结构错乱的 LaTeX，要么产出 MathType 会"假成功"的
写法。本机逐条实测（pandoc 3.6.4）：

    Typst 源                         pandoc 输出
    ------------------------------------------------------------------
    a &= b \\ c &= d                 \\begin{array}{rlr} a & = b\\backslash c ...
    $0°$                             0{^\\circ}        ← 无基底的上标组
    $10^-2$                          10^{-}2           ← 上标是空的，"2" 掉回基线
    mat(delim:"[",1,2;3,4)           \\begin{bmatrix}…   ✅
    phi_x(x,y)                       \\varphi_{x(x,y)}  ✅（与 Typst 自己渲染一致）
    upright(T) / dot.c / plus.minus  \\mathrm{T} / \\cdot / \\pm  ✅

前两类是"顶层语法被误读"：`&`/`\\\\` 只在数学的**最外层**有意义，pandoc 把
整块塞进一个 array 里再逐个猜，结果既丢了行结构、又把 `\\\\` 变成
`\\backslash{}` 字面量。

所以这里自己切顶层，逐格交给 pandoc
----------------------------------
`&` 与 `\\\\` 在深度 0 处无歧义（`mat(...)`/`cases(...)` 内部用的是 `;` 和
`,`，不会被误伤），于是：

    1. 按 `$…$` 把公式整段抽出来（跳过 // 注释与转义）；
    2. 深度 0 处按 `\\\\` 切行、按 `&` 切列；
    3. **每个格子单独**变成 `$cell$`，一次性批量喂给 pandoc（只起一次进程）；
    4. 自己组装成 \\begin{aligned}（交给 tex_macros 再降级成 array）；
    5. normalize + 结构校验，修不了的直接报出来，不静默通过。

pandoc 仍然负责"单个表达式"的翻译——它的绑定规则是对的（`phi_x(x,y)` 就
该是 `\\varphi_{x(x,y)}`，这是 Typst 自己的读法），别自己重写一遍。
"""
from __future__ import annotations

import re
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

SEP = "TYPGRIDSEP"  # Typst 里 @ 是引用标记，分隔符只能是纯字母


# --------------------------------------------------------------------------
# 1. 抽取与切分
# --------------------------------------------------------------------------
@dataclass
class MathSpan:
    start: int          # `$` 的位置
    end: int            # 收尾 `$` 之后的位置
    body: str

    @property
    def is_block(self) -> bool:
        """Typst 用首尾空白标记行间公式：`$ x $` 是 block，`$x$` 是 inline。"""
        return bool(self.body[:1].isspace() or self.body[-1:].isspace())


def scan_math(src: str) -> list[MathSpan]:
    """扫出所有 `$…$`，跳过 // 注释与 \\$ 转义。

    只做配对，不理解数学语义——理解数学是 pandoc 的活。
    """
    spans: list[MathSpan] = []
    i, n = 0, len(src)
    while i < n:
        if src.startswith("//", i):
            j = src.find("\n", i)
            i = n if j < 0 else j + 1
            continue
        ch = src[i]
        if ch == "\\" and i + 1 < n:      # 转义字符，整体跳过
            i += 2
            continue
        if ch == "$":
            j = i + 1
            while j < n:
                if src[j] == "\\" and j + 1 < n:
                    j += 2
                    continue
                if src[j] == "$":
                    break
                j += 1
            if j >= n:                     # 落单的 $
                break
            spans.append(MathSpan(i, j + 1, src[i + 1:j]))
            i = j + 1
            continue
        i += 1
    return spans


def split_grid(body: str) -> list[list[str]]:
    """深度 0 处按 `\\\\`（行）与 `&`（列）切开。

    注意 Typst 的行分隔是**单个反斜杠**（`\\` 后面跟空白/换行），不是 LaTeX
    的 `\\\\`——`\\\\` 在 Typst 里是字面反斜杠。本机实测：一行里带 `&` 的
    多行公式，pandoc 有时能自己转对，但只要后一行以分式开头就会把行结构塞进
    `\\frac{...}` 里（真实稿 1.1 节即如此），所以这里先自己切干净。
    """
    rows: list[list[str]] = []
    cur_row: list[str] = []
    buf: list[str] = []
    depth = 0
    i, n = 0, len(body)
    while i < n:
        ch = body[i]
        if ch == "\\":
            nxt = body[i + 1] if i + 1 < n else ""
            if nxt == "\\":                      # 字面反斜杠
                buf.append("\\\\")
                i += 2
                continue
            if nxt == "" or nxt in " \t\r\n":    # 行分隔（吞掉紧随的空白）
                while i < n and body[i] in "\\ \t\r\n":
                    i += 1
                cur_row.append("".join(buf).strip())
                buf = []
                rows.append(cur_row)
                cur_row = []
                continue
            buf.append("\\" + nxt)               # 转义字符，原样保留
            i += 2
            continue
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth = max(0, depth - 1)
        elif ch == "&" and depth == 0:           # 列分隔
            cur_row.append("".join(buf).strip())
            buf = []
            i += 1
            continue
        buf.append(ch)
        i += 1
    cur_row.append("".join(buf).strip())
    rows.append(cur_row)
    # 去掉纯空行（例如公式末尾多一个换行）
    rows = [r for r in rows if any(c.strip() for c in r)] or [[""]]
    return rows


# --------------------------------------------------------------------------
# 2. 逐格转译（一次 pandoc 调用处理全部）
# --------------------------------------------------------------------------
def translit(cells: list[str], pandoc: str = "pandoc", timeout: int = 180) -> list[str]:
    """把若干 Typst 表达式批量转成 LaTeX。空串原样返回空串。"""
    if not cells:
        return []
    todo = [(k, c.strip()) for k, c in enumerate(cells) if c.strip()]
    if not todo:
        return ["" for _ in cells]

    parts: list[str] = []
    for k, (_, body) in enumerate(todo):
        if k:
            parts.append("")
            parts.append(SEP)
            parts.append("")
        parts.append("$" + body + "$")
    tmp = Path(tempfile.mkdtemp(prefix="typmath_")) / "cells.typ"
    tmp.write_text("\n".join(parts) + "\n", encoding="utf-8")
    try:
        r = subprocess.run(
            [pandoc, "-f", "typst", "-t", "latex", str(tmp)],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=timeout,
        )
        if r.returncode != 0:
            raise RuntimeError(f"pandoc 失败（{r.returncode}）：{(r.stderr or '').strip()[:300]}")
        out = r.stdout
    finally:
        tmp.unlink(missing_ok=True)

    chunks = out.split(SEP)
    if len(chunks) != len(todo):
        # 标记被吃掉说明 pandoc 改写了结构，宁可报错也不要错位
        raise RuntimeError(
            f"逐格转译错位：期望 {len(todo)} 段，实得 {len(chunks)} 段")
    result = ["" for _ in cells]
    for (k, _body), chunk in zip(todo, chunks):
        latex = _unwrap(chunk)
        result[k] = normalize(latex)
    return result


def _unwrap(s: str) -> str:
    """pandoc 给单条表达式套的是 `\\(…\\)`，剥掉外层。"""
    s = s.strip()
    if s.startswith("\\(") and s.endswith("\\)"):
        s = s[2:-2]
    elif s.startswith("\\[") and s.endswith("\\]"):
        s = s[2:-2]
    return s.strip()


# --------------------------------------------------------------------------
# 3. 归一化：修掉"MathType 会静默画错"的写法
# --------------------------------------------------------------------------
NOBASE_GROUP = re.compile(r"(?<!\\)\{(\^|_)([^{}]*)\}")
EMPTY_SCRIPT = re.compile(r"\^\{([-+])\}(\d+)")
TEXT_TAIL_SPACE = re.compile(r"\\text\{([^{}]*?)\s+\}")


def normalize(tex: str) -> str:
    """把 Typst 源带出来的、MathType 会"假成功"的写法改掉。

    三条都来自实测：
      `0{^\\circ}`  MathType 把 { } 当字面字符印出来（`0{°}`）；
      `10^{-}2`    上标是空的，2 掉回基线；
      `\\text{T }`  Typst 的 "T" 带了尾随空格，公式里多一个空隙。
    """
    tex = NOBASE_GROUP.sub(lambda m: m.group(1) + "{" + m.group(2) + "}", tex)
    tex = EMPTY_SCRIPT.sub(lambda m: "^{" + m.group(1) + m.group(2) + "}", tex)
    tex = TEXT_TAIL_SPACE.sub(lambda m: r"\text{" + m.group(1) + "}", tex)
    return tex


# --------------------------------------------------------------------------
# 4. 结构校验：能修的自己修，修不了的要报出来
# --------------------------------------------------------------------------
ENV_OK = {"array", "matrix", "pmatrix", "bmatrix", "Bmatrix", "cases", "align",
          "aligned", "gathered", "split", "eqnarray"}


def validate(tex: str) -> list[str]:
    """返回问题清单。空列表 = 这条公式可以安全交给 MathType。"""
    bad: list[str] = []
    if tex.count("{") != tex.count("}"):
        bad.append("花括号不平衡")
    if "\\backslash" in tex:
        bad.append("残留 \\backslash（顶层 \\\\ 没切开）")
    if re.search(r"\{[\^_]", tex):
        bad.append("仍有不带基底的上标/下标组")
    if re.search(r"\^\{[-+]\}\d", tex):
        bad.append("空上标 `^{-}N`")
    for m in re.finditer(r"\\begin\{(\w+\*?)\}", tex):
        if m.group(1) not in ENV_OK:
            bad.append(f"环境 \\begin{{{m.group(1)}}} 不在白名单")
    if re.search(r"\\frac\s*\{[^{}]*\\begin\{array\}", tex):
        bad.append("\\frac 参数里套了 array（行结构已坏）")
    return bad


# --------------------------------------------------------------------------
# 5. 对外主入口
# --------------------------------------------------------------------------
@dataclass
class Converted:
    latex: str
    is_block: bool
    problems: list[str] = field(default_factory=list)


def to_latex(body: str, pandoc: str = "pandoc") -> Converted:
    """单条 Typst 公式 → LaTeX。多条请用 translate_many（省进程）。"""
    return translate_many([body], pandoc=pandoc)[0]


def translate_many(bodies: list[str], pandoc: str = "pandoc") -> list[Converted]:
    """批量转换。先把所有公式拆成格子、一次 pandoc、再组装回去。"""
    grid_of: list[tuple[bool, list[list[int]]]] = []   # (是否网格, 行列→cell 下标)
    flat: list[str] = []

    for body in bodies:
        rows = split_grid(body)
        is_grid = len(rows) > 1 or any(len(r) > 1 for r in rows)
        idx: list[list[int]] = []
        for r in rows:
            line = []
            for cell in r:
                line.append(len(flat))
                flat.append(cell)
            idx.append(line)
        grid_of.append((is_grid, idx))

    lats = translit(flat, pandoc=pandoc)

    out: list[Converted] = []
    for body, (is_grid, idx) in zip(bodies, grid_of):
        if not is_grid:
            tex = lats[idx[0][0]]
            out.append(Converted(tex, _is_block_body(body), validate(tex)))
            continue
        ncol = max(len(r) for r in idx)
        lines = []
        for r in idx:
            cells = [lats[k] for k in r]
            cells += [""] * (ncol - len(cells))
            lines.append(" & ".join(cells))
        tex = "\\begin{aligned}\n" + " \\\\\n".join(lines) + "\n\\end{aligned}"
        out.append(Converted(tex, True, validate(tex)))
    return out


def _is_block_body(body: str) -> bool:
    return bool(body[:1].isspace() or body[-1:].isspace())

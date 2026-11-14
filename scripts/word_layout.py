#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Word 侧的排版修整（python-docx 层）。

这些坑跟输入是 Typst 还是 LaTeX 无关，是 pandoc 出稿 + MathType 落地这条链
上必然要补的：

1. **表格列宽**：pandoc 出的表没有 `tblLayout`，Word 按"自动调整"重算列宽，
   而自动调整**不把 OLE 对象算进内容宽度**——装着公式的那一列被压到极窄，
   对象直接溢出到表格外面（真实稿三张 SIF 表全中）。改成固定列宽，用 pandoc
   自己算好的 `tblGrid`，不另造一套宽度。
2. **单元格段距**：行间公式的 10pt 段前/段后进到单元格里，一个只有一行数据的
   单元格被撑成三行高。而且 `Toggle TeX` 在 S4 会**再写一遍**，所以这一步
   既要在 S3 做，也要在 S4 之后重做。
3. **图片高度**：Word 不会替你缩放，高分辨率图按原始尺寸铺上去比版心还高，
   于是"图注在上一页、图在下一页"。超过版心 92% 的图等比缩下来。
4. **图注分页**：图注段落打开 `keep_with_next`，图注就不会和图分家。
"""
from __future__ import annotations

import re

from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt
from docx.text.paragraph import Paragraph

FIG_TEXT_RE = re.compile(r"^\s*(图|表)\s*\d+")
A_EXT = "{http://schemas.openxmlformats.org/drawingml/2006/main}ext"


def max_image_height(doc, ratio: float = 0.92) -> int:
    """版心高度 × ratio（EMU）。拿不到页面信息时按 A4 + 2.5cm 上下边距估。"""
    try:
        sec = doc.sections[-1]
        page_h = int(sec.page_height) - int(sec.top_margin) - int(sec.bottom_margin)
    except Exception:                                   # noqa: BLE001
        page_h = int(24.0 / 2.54 * 914400)
    return int(page_h * ratio)


def layout_tables(doc) -> int:
    fixed = 0
    for tbl in doc.tables:
        t = tbl._tbl
        tblPr = t.tblPr
        if tblPr is None:
            continue
        for old in tblPr.findall(qn("w:tblLayout")):
            tblPr.remove(old)
        layout = OxmlElement("w:tblLayout")
        layout.set(qn("w:type"), "fixed")
        tblPr.append(layout)

        grid = [int(g.get(qn("w:w"))) for g in t.iter(qn("w:gridCol")) if g.get(qn("w:w"))]
        if grid:
            tw = tblPr.find(qn("w:tblW"))
            if tw is None:
                tw = OxmlElement("w:tblW")
                tblPr.append(tw)
            tw.set(qn("w:type"), "dxa")
            tw.set(qn("w:w"), str(sum(grid)))

        for tr in t.findall(qn("w:tr")):
            trPr = tr.find(qn("w:trPr"))
            if trPr is None:
                continue
            for h in trPr.findall(qn("w:trHeight")):
                trPr.remove(h)

        nrows = len(t.findall(qn("w:tr")))
        for ri, tr in enumerate(t.findall(qn("w:tr"))):
            for tc in tr.findall(qn("w:tc")):
                # 注意：pPr 是 w:p 的子元素，不是 w:tc 的。直接往 tc 里塞 pPr
                # 是无效 XML，Word 会静默忽略（这个 bug 实测让整表高出 10pt/行）。
                for p_el in tc.findall(qn("w:p")):
                    para = Paragraph(p_el, None)
                    fmt = para.paragraph_format
                    fmt.space_before = Pt(0)
                    # 末行留 3pt，别让三线表底线贴着字
                    fmt.space_after = Pt(3) if ri == nrows - 1 else Pt(0)
        fixed += 1
    return fixed


def layout_figures(doc, max_h_emu: int | None = None) -> dict:
    if max_h_emu is None:
        max_h_emu = max_image_height(doc)
    scaled = 0
    for p in doc.paragraphs:
        for ext in p._p.iter(qn("wp:extent")):
            cy = int(ext.get("cy") or 0)
            cx = int(ext.get("cx") or 0)
            if not cy or cy <= max_h_emu:
                continue
            k = max_h_emu / cy
            ext.set("cy", str(int(cy * k)))
            ext.set("cx", str(int(cx * k)))
            for sub in p._p.iter(A_EXT):            # a:ext 不同步改，Word 仍按旧尺寸排
                if sub.get("cy"):
                    sub.set("cy", str(int(int(sub.get("cy")) * k)))
                    sub.set("cx", str(int(int(sub.get("cx")) * k)))
            scaled += 1

    kept = 0
    paras = doc.paragraphs
    for i, p in enumerate(paras):
        if not FIG_TEXT_RE.match(p.text or ""):
            continue
        nxt = paras[i + 1] if i + 1 < len(paras) else None
        if nxt is None:
            continue
        if (nxt._p.find(".//" + qn("w:drawing")) is not None
                or nxt._p.find(".//" + qn("w:pict")) is not None):
            p.paragraph_format.keep_with_next = True
            kept += 1
    return {"scaled": scaled, "captions_kept": kept}


def fix_docx(path, max_h_emu: int | None = None) -> dict:
    """对一个已经存在的 docx 原地做上面四件事（S4 之后重做用）。"""
    from docx import Document

    doc = Document(str(path))
    tables = layout_tables(doc)
    figs = layout_figures(doc, max_h_emu)
    doc.save(str(path))
    return {"tables": tables, **figs}

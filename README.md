# TYP2WORD

**Typst → Word，公式落地为可双击编辑的原生 MathType 对象，全程零 OMML。**

Typst 论文（十几到几百个公式）转成**可继续编辑的 Word 工作稿**：公式是独立的
`Equation.DSMT4` 对象，双击就能改；章节层级、表格、图片都在原位。

> English: convert Typst papers to Word where every equation becomes an editable
> native MathType OLE object instead of OMML. Typst math is translated cell-by-cell,
> pandoc never sees it. Windows + Word + MathType 7 required.

---

## 为什么不是 `pandoc -f typst -t docx`

pandoc 能把 Typst 的正文结构转出来，但它的公式会变成 OMML——之后想改一个字要
整条重排，而且 LaTeX 语义在那一步就丢了。更要紧的是，`pandoc -f typst -t latex`
在数学上有几类**不报错**的硬伤：

| Typst 源 | pandoc 输出 | 后果 |
|---|---|---|
| 多行对齐公式（后行以分式开头） | `\begin{array}{rlr}`，行结构塞进 `\frac{…}` | 公式结构塌掉 |
| `$0°$` | `0{^\circ}` | MathType 把 `{ }` 当字面字符印出来 |
| `$10^-2$` | `10^{-}2` | 上标是空的，"2" 掉回基线 |

本仓的做法是**公式不进 pandoc 的正文通道**：`$…$` 先抽成占位符，公式按
「顶层切行/切列 → 逐格转译 → 自己组装」处理，最后一刻由 MathType 官方宏
`Toggle TeX` 原地换成 OLE 对象。

实测（同一份 335 公式的中文稿）：抽走数学后 pandoc 输出里
`\frac` / `\sum` / `\begin{array}` / `{^` 的出现次数全部为 **0**，标题、图片、
`longtable` 一个不少；最终 338 个公式对象、OMML 0、正文段落缺失 0。

## 环境要求

| 依赖 | 要求 | 为什么 |
|---|---|---|
| 操作系统 | Windows | OLE 复合对象只能由桌面版 Word 写入 |
| Word | 桌面版 Microsoft Word | WPS / LibreOffice 不能写 MathType 对象 |
| MathType | 7 完整版，且 `MathType Commands 2016.dotm` 在 Word STARTUP 里 | 转换靠它提供的 `Toggle TeX` 宏 |
| pandoc | 3.0+ | 正文骨架 |
| Python | 3.9+，`pip install python-docx lxml pywin32` | 编排各阶段 |

```bash
python scripts/doctor.py     # 体检：MathType / Word / 加载项 / pandoc / 依赖 / Word 冒烟
```

## 用法

```bash
PY="C:/Users/<you>/AppData/Local/Programs/Python/Python313/python.exe"

$PY scripts/run.py paper.typ -o paper.docx

# 有自己编译好的 PDF：校准行距/标题字号，并做版面与正文覆盖对比
$PY scripts/run.py paper.typ -o paper.docx --style-pdf paper.pdf --compare paper.pdf
```

`run.py` 串完 S0→S5（可选 S6）。也可以分步跑，见 [`SKILL.md`](SKILL.md)。

## 与上游 L2Word-mathtype 的关系

后端五个阶段（抽公式 / 建 docx / MathType 落地 / 校验 / 版面对比）与
[L2Word-mathtype](https://github.com/Fisfzy/L2Word-mathtype) 同源，硬约束一致；
本仓替换的是"语际转换"那一段，并修掉了四个 Word 侧的排版坑（表格列宽、单元格
段距、图片限高、图注分页），这些对 LaTeX 稿同样有效。

新增模块：

- `scripts/typ_math.py` —— Typst 数学 → LaTeX（顶层切分、归一化、结构校验）
- `scripts/typ2tex.py` —— `.typ` → `.tex`（占位符隔离、标题与图注清理）
- `scripts/typ_style.py` —— `#set page/text/par` → `reference.docx`
- `scripts/doctor.py` 增加 Word 自动化冒烟测试（能建文档、能存盘）
- `scripts/build_docx.py` 增加 `layout_tables` / `layout_figures`

## 测试

```bash
python tests/run_typ_tests.py           # 4 个 .typ 用例，只到 S0.5，秒级，不需要 Word
```

## 已知边界

`#figure(...)` 的编号、`@ref` 交叉引用、`#bibliography` 与 `#outline` 尚未做
语义化处理（按字面文本保留）。详见 [`SKILL.md`](SKILL.md) 的"已知不做"。

## 授权

MIT。

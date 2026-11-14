---
name: typ2word-mathtype
description: 把 Typst 论文转换成 Word（.docx），公式落地为可双击编辑的原生 MathType 对象，全程零 OMML。当用户要求"Typst 导出 Word"、"typ 转 docx"、"论文转 Word 且公式要 MathType 格式"、"可编辑的 Word 工作稿"时使用。先 pandoc 出骨架，公式逐格转译，最后用 MathType 官方宏原地换对象。
---

# Typst → Word（MathType 公式，无 OMML）

`.typ` 里的公式**全程以 Typst 源码形态流转**：`$…$` 一进来就被抽成占位符，
pandoc 只看到正文骨架；公式按「顶层切行 / 切列 → 逐格交给 pandoc → 自己组装」
处理；最后一刻才由 MathType 的 `Toggle TeX` 宏换成 `Equation.DSMT4` 对象。
**文档里永远不会出现 OMML。**

> 本仓是 [L2Word-mathtype](https://github.com/Fisfzy/L2Word-mathtype) 的 Typst 前端，
> 沿用它的五阶段后端（prep / build / to_mathtype / verify），只替换"语际转换"那一段。
> 公式与后端那套硬约束与上游同等效力。

## 一句话安装

```bash
pip install python-docx lxml pywin32
python scripts/doctor.py          # 有 [STOP] 先修，别往下跑
```

硬性环境：Windows + 桌面版 Word + MathType 7 完整版（`MathType Commands 2016.dotm`
在 Word 的 STARTUP 目录里）+ pandoc ≥ 3 + Python 3.9+。

## 快速开始

```bash
PY="C:/Users/<you>/AppData/Local/Programs/Python/Python313/python.exe"

# 一条命令跑完 S0→S5（Typst 稿直接给 .typ）
$PY scripts/run.py paper.typ -o paper.docx

# 有自己编译好的 PDF：用它校准行距与标题字号，并做一次版面/正文覆盖对比
$PY scripts/run.py paper.typ -o paper.docx --style-pdf paper.pdf --compare paper.pdf
```

分步：

```bash
$PY scripts/doctor.py                                   # S0  环境体检（含 Word 冒烟）
$PY scripts/typ2tex.py   paper.typ -o build/paper.tex   # S0.5 Typst → LaTeX
$PY scripts/scan_tex.py  build/paper.tex --out build/audit.md   # S1 复杂度审计
$PY scripts/prep_tex.py  build/paper.tex -o build --keep-subheadings   # S2 抽公式
$PY scripts/typ_style.py paper.typ -o build/reference.docx      # S2.5 版式
$PY scripts/build_docx.py build/prepared.tex -o build/base.docx \
        --equations build/equations.json --reference-doc build/reference.docx \
        --no-number-sections                            # S3 骨架 + 回填
$PY scripts/to_mathtype.py build/base.docx -o build/out.docx    # S4 MathType 落地
$PY scripts/verify.py build/out.docx --manifest build/filled.json \
        --source build/equations.json                   # S5 校验
```

## 为什么公式不能整篇丢给 pandoc

`pandoc -f typst -t latex` 在正文层面够用，在数学层面有三类**不报错**的硬伤
（本机 pandoc 3.6.4 逐条实测）：

| Typst 源 | pandoc 输出 | 后果 |
|---|---|---|
| `a &= b \` + 换行 + `c &= d`（后行以分式开头） | `\begin{array}{rlr}`，行结构被塞进 `\frac{…}{…}` | 公式结构塌掉 |
| `$0°$` | `0{^\circ}` | **MathType 把 `{ }` 当字面字符印出来** |
| `$10^-2$` | `10^{-}2` | 上标是空的，"2" 掉回基线 |
| `mat(delim:"[",1,2;3,4)` | `\begin{bmatrix}…` | ✅ 正常 |
| `phi_x(x,y)` | `\varphi_{x(x,y)}` | ✅ 与 Typst 自己渲染一致 |
| `upright(T)` / `dot.c` / `plus.minus` | `\mathrm{T}` / `\cdot` / `\pm` | ✅ 正常 |

前两类是「顶层语法被误读」。所以本仓的做法是：

1. 按 `$…$` 抽出公式（跳过 `//` 注释和 `\` 转义）；
2. **深度 0** 处按 `&` 切列、按**单个 `\`** 切行（Typst 用 `\` 换行，`\\` 是字面反斜杠）；
3. 每个格子单独变成 `$cell$`，**一次** pandoc 调用批量转完；
4. 自己组装 `\begin{aligned}`（后端会按 MathType 的脾气再降级成 `array`）；
5. `normalize` 修掉 `{^X}` / `10^{-}N` / `\text{X }`，`validate` 把修不了的报出来。

实测同一份 335 公式的稿子：抽走数学后 pandoc 输出里
`\frac` / `\sum` / `\begin{array}` / `{^` 的出现次数**全部为 0**，而
`\section`/`\subsection`/`longtable`/`includegraphics` 一个不少。

## Typst 与 LaTeX 的语义差异（改代码前必读）

| Typst | 对应 LaTeX | 本仓处理 |
|---|---|---|
| `\`（反斜杠）换行 | `\\` | `typ_math.split_grid` 顶层切分 |
| `\\` | 字面反斜杠 | 原样保留 |
| `°` `±` `≤` | `^\circ` `\pm` `\leq` | 交给 pandoc，**再修掉它加的花括号** |
| `*强*` / `_强调_` | `\textbf` / `\emph` | pandoc 直接认（注意不是 markdown 的 `**`） |
| `#set page/text/par` | 页面/样式 | `typ_style.py` 读源文件生成 reference.docx |
| `#set par(leading: 0.78em)` | Word 行距（磅） | 经验换算 `size*(1+0.30*leading)`，10.5pt→13.0pt 与实测一致 |
| `#set document(title:)` | — | 只是 PDF 元数据，**正文可能印的是另一个标题** |
| `#align(center)[#text(size:21pt…)]` | 标题 | 取这个"可见标题"优先，再回退元数据 |
| `#table(columns: …)` | 无列宽 | pandoc 出 longtable，S3 再固定列宽 |
| `#figure(caption: …)` / `@ref` | `\caption` / `\ref` | **未实现**，见下 |

## 结构能力

认得：`= / == / ===` 标题层级、有序/无序列表、`#table`、行内代码、`#link`、
`#strong`/`#emph`、`#set page/text/par`、`document(title:)`、手写居中标题块。

**已知不做**（不是能力不足，是这一步没有语义可依）：

| 写法 | 结果 | 绕法 |
|---|---|---|
| `#figure(...caption:...)` + `@fig:x` | 不生成 SEQ/REF 域，图号按字面文本 | 改成"加粗 `图 N：`"段落（本仓按此处理，与 Typst 输出一致） |
| `#let` 自定义函数 | pandoc 不求值；函数体里的 `image()` 会被转成图片 | 尽量用内置元素 |
| `#bibliography("x.bib")` + `@key` | 不展开 | 先 `#bibliography` 导出为 LaTeX 侧文献表 |
| `#outline()` | 不生成目录 | Word 里「引用 → 目录」 |
| `#show` 花式样式 | 丢弃 | 版式以 `#set` 为准 |

## Word 侧的四个坑（与 Typst 无关，但一样会让稿子不能看）

这些坑 LaTeX 稿同样会踩，所以修在后端而不是前端（`scripts/word_layout.py`）：

1. **表格自动调整不把 OLE 对象算进列宽** → 装公式的那一列被压扁、对象溢出表格。
   `layout_tables()` 改成固定列宽（用 pandoc 算好的 `tblGrid`）。
2. **行间公式的 10pt 段前/段后进到单元格里** → 一行数据被撑成三行高（实测
   35.9pt → 15.8pt）。而且 `Toggle TeX` 在 S4 会**再写一遍**，所以这一步必须
   在 S3 和 S4 之后各做一次。
   > 写这段时踩过一个隐蔽的坑：`w:pPr` 是 `w:p` 的子元素，不是 `w:tc` 的。
   > 往 `w:tc` 里插 `w:pPr` 生成的是无效 XML，Word **静默忽略**，看起来"改过了"
   > 却一点效果都没有。用 python-docx 的 `Paragraph.paragraph_format` 才安全。
3. **图片按原始尺寸铺** → 比版心还高，于是"图注在上一页、图在下一页"。
   `layout_figures()` 把超过版心 92% 的图等比缩下来，并给图注打开 `keep_with_next`。
4. **文件沙箱让 Word 建不了工作文件** → 弹一个隐藏的模态框，COM 调用**永久挂住**
   （不是报错，是卡死）。`doctor.py` 的 Word 冒烟测试用线程 + 超时把这件事在 5 秒内
   说出来，必要时点掉模态框。

## 交付前只认这几条

1. `verify.py` 结论「通过」：对象数、OMML=0、残留分隔符、OLE 里的未知宏、内容对账；
2. `compare_pdf.py` 的**正文段落缺失必须是 0**（整体词相似度会被公式对象拉低，不能当验收线）；
3. 导出的 PDF 文字层里扫不到 `{` `}` `\`（这是"假成功"的最后一道闸）；
4. 页数差 ≤ 1 页。

## 目录

```
scripts/
  typ_math.py      Typst 数学 → LaTeX（顶层切分、归一化、校验）
  typ2tex.py       .typ → .tex（占位符隔离 + 标题/图注清理）
  typ_style.py     #set page/text/par → reference.docx
  run.py           一键 S0→S5（.typ / .tex 都行）
  doctor.py        环境体检（含 Word 自动化冒烟）
  scan_tex.py  prep_tex.py  build_docx.py  to_mathtype.py  verify.py
  tex_macros.py  tex_struct.py  bibtex.py  learn_style.py  make_reference_docx.py
  compare_pdf.py
tests/
  run_typ_tests.py  4 个 .typ 回归用例，只到 S0.5，秒级
  cases/*.typ
references/degrade-rules.md
```

## 测试

```bash
python tests/run_typ_tests.py            # 不需要 Word/MathType，秒级
python tests/run_typ_tests.py -k cjk
```

用例覆盖：多行对齐、`° ± ≤ 10^-2`、`mat/cases/op`、标题与表格与注释里的 `$`、
中文手写标题块、长公式行结构。

## 授权

MIT。后端流水线来自 [L2Word-mathtype](https://github.com/Fisfzy/L2Word-mathtype)。

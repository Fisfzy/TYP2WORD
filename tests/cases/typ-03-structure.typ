// typ-03-structure：标题层级、列表、表格、行内代码、链接、注释里的 $ 不算公式
#set page(paper: "a4", margin: (x: 2.2cm, top: 2.5cm, bottom: 2.3cm))
#set text(size: 10.5pt, font: ("Times New Roman", "SimSun"))

// 这一行是注释，里面的 $not math$ 不应该被当成公式

= 第一部分：结构

== 1.1 小节

- 列表项一 $a_1$
- 列表项二 $b_2$

=== 三级标题

层合板 `[0/90/90/0]` 的写法保留原文。

#table(
  columns: (auto, auto, auto),
  align: (left, right, right),
  [*构型*], [*误差*], [*备注*],
  [薄板], [0.073%], [Reddy],
  [厚板], [0.498%], [Pagano],
)

见 #link("https://example.com")[外部链接]。

= 附录

结尾一段 $c = 2 pi r$。

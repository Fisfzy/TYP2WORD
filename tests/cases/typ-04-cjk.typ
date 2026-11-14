// typ-04-cjk：中文标题、中文题注式段落、中文正文夹公式
#set document(title: "元数据标题（不该被用）")

#v(0.5em)

#align(center)[#text(size: 21pt, weight: "bold", font: ("Microsoft YaHei", "SimHei"))[当前进展说明]]

#v(0.3em)
#align(center)[#line(length: 30%, stroke: 0.9pt + luma(120))]
#v(0.9em)

= 第一部分：理论基础

设节点 $i$ 的坐标为 $bold(x)_i$，在给定_邻域半径_内参与计算的节点集合称为该节点的*族*。

$
g_(i j)^((r,s)) &= omega_(i j) bold(p)_(i j)^"T" bold(a)_i^((r,s)), \
(partial^(r+s) f)/(partial x^r partial y^s) |_i & approx
  1/(ell_(x,i)^r ell_(y,i)^s) sum_(j in cal(F)_i) g_(i j)^((r,s)) (f_j - f_i) Delta A_j.
$

温度取 $25 °$，误差在 $±0.5%$ 以内。

# 方向标签（direction tags）

给用户一个**风格化的操纵面**：一次策展结束后，用大约 5 个标签说明这次「往哪个方向走」，
让用户能说「多一点 funk / 少一点 disco」，而不必重写整段需求。

对应的 MCP 工具是 `am_tag_directions`，实现是 `playlist_tags.py`。

## 边界：标签不是 brief

这一点必须先说，因为它决定了这个功能能做什么、不能做什么。

`docs/evaluation-signals.md` 记录了为什么把需求压成标签或权重表是有害的：
它会丢掉否定的作用范围、参照与必选的区分、以及叙事节点。**方向标签不改变这个结论。**

标签是**反向使用的**：

| | brief 与策展契约 | 方向标签 |
|---|---|---|
| 权威性 | **唯一权威** | 操纵面，冲突时以 brief 为准 |
| 内容 | 必须、排除、参照、软语境、叙事节点、未决 | 约 5 个词，概括「这次的方向」 |
| 谁写的 | 用户 + 宿主模型 | 宿主模型 |
| 用途 | 决定选哪些歌 | 让用户能抽象地调方向 |

因此 `direction_note()` 的输出里**自带**这句边界，宿主模型读到的就是带约束的指令，
不依赖外部文档提醒：

> 这些标签是给用户的操纵面，**不是 brief**：原始需求与策展契约仍然优先，冲突时以 brief 为准。

## 两个轴

标签分两个轴，因为它们的**可信度不同**：

- **`sonic`** —— 音乐自身的属性：流派、年代、织体、氛围、编制、语言。
- **`context`** —— 这些歌**为什么在这里**：最近在听、高播放、集中循环、本就在库里、
  来自某个参照曲、新加入但还没听。

`context` 轴上的标签**必须有真实证据**（`am_recently_played` / `am_top_played` / 音乐库），
不能凭印象写。这是仓库里「catalog 事实 / 收听证据 / 模型推断」三分法的延伸：
把「我觉得他最近在听」写成 `context:recent` 是在伪造证据。

轴必须**显式写**。本模块不猜轴——猜轴需要一份流派与行为词库，那等于把
「这个模块不认识音乐」这句话作废。没写轴的标签会被接受但**报出来**，请补上。

## 写法

```text
字符串：   night
            sonic:night                     # 显式轴
            context:recent-heavy-rotation
           （也接受对象：{"label": "night", "axis": "sonic", "weight": 1.5}）
```

约 5 个，上限 8 个——超过 8 个就不是操纵面，而是一份清单了。

权重默认 `1.0`，范围 `0.0 – 2.0`：

- `> 1.0` 表示「往这个方向再走一点」
- `< 1.0` 表示「这个方向收着点」

## 用户怎么调

| 用户说 | 效果 |
|---|---|
| `more funk` / `多一点 funk` / `+funk` | 权重 +0.5 |
| `less disco` / `少一点 disco` / `-disco` | 权重 −0.5；降到 0 就移除 |
| `drop dark` / `去掉 dark` | 直接移除 |
| `add ambient` / `加上 ambient` | 补一个（权重 1.0，轴未指定） |
| `more funk 0.25` | 指定步长 |

三条性质是刻意保证的：

1. **确定性**：同样的输入永远得到同样的输出，权重是显式记账，不是模型即兴。
2. **可解释**：每条调整都回一句 `before → after`。
3. **不静默**：找不到的标签回 `unknown` 并**列出实际有哪些**。用户说 `more techno`
   而方向里没有 techno 时，最坏的结果是「说了但没反应」——所以必须说出来。
   同理，读不懂的调整回 `unparsed`，而不是当没说过。

## 交互流程

```text
1. 宿主模型读完 brief，完成策展（选择与排序仍按原有流程）。
2. 模型写约 5 个方向标签，混两个轴，调用 am_tag_directions(tags=[...])。
3. 把返回的「展示」行给用户看：
     sonic — synthwave · night · dark   ‖   context — recent-heavy-rotation · in-library
4. 用户回：more night / less dark。
5. 同一工具带 adjustments 再调一次，得到新的展示行与 direction_note。
6. 把 direction_note 作为**补充**并入下一轮 brief（原始需求保持不动）。
```

这个工具**只读且离线**：不碰 Apple Music，不需要登录，所以方向可以在一开始就谈清楚，
不必等到写完歌单。

## 一个完整的例子

（用中立的描述，不指涉任何具体作品。）

用户：「深夜开车听的那种，霓虹感，偏冷。」

模型给出并展示：

```text
sonic — synthwave · night · cold · driving   ‖   context — in-library
```

用户回 `more cold` / `less driving`：

```text
[applied] 「cold」1.0 → 1.5
[applied] 「driving」1.0 → 0.5

展示：sonic — synthwave · night · cold ↑1.5 · driving ↓0.5   ‖   context — in-library
```

若用户接着回 `more funk`，而方向里没有 funk：

```text
[unknown] 方向里没有「funk」，所以 more 没有作用；
          现有标签：synthwave、night、cold、driving、in-library
```

—— 这是**期望行为**：宁可告诉用户「这个方向我这边没有」，也不要让它看起来生效了。

## 与其他工具的分工

| 关心的事 | 用哪个 |
|---|---|
| 选哪些歌、主题是否契合 | 宿主模型的判断（`am_resolve_candidates` 只提供 catalog 事实） |
| 这次的**方向**是什么、用户想怎么调 | `am_tag_directions` |
| 段内衔接是否顺 | `am_optimize_order`（可选，不负责选曲） |
| 需求本身（必须/排除/参照/叙事） | brief 与策展契约，**始终优先** |

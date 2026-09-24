# LLM 原生的选曲流程

这份文档回答一个问题：**当用户只给一段自然语言描述时，哪些判断应该交给 LLM，哪些事情
必须由确定性代码完成？**

结论：主题、气质、歌词语义、文化语境和曲目之间的呼应属于语言理解；可用性、版本、重复、
数量和账号写入属于工具执行。不要把前一类审美判断伪装成精确的 `0–1` 分数，也不要让后一类
事实依赖模型猜测。

2026-09-24 的文献补充见 [`natural-language-curation-evidence.md`](natural-language-curation-evidence.md)：
真实音乐请求中的艺人/作品经常只是参照而非必选项，复杂否定也容易被模型误读。因此“理解 brief”
不能只抽取几个标签，还要保留各个描述在请求里的作用。

---

## 1. 职责边界

| 层 | 负责什么 | 不负责什么 |
|---|---|---|
| MCP Host 中的 LLM | 理解用户描述、提出候选、比较取舍、解释理由、设计叙事段落 | 猜 catalog ID、假定某版本存在 |
| Apple Music MCP 服务 | 搜索、版本解析、元数据、重复检查、dry-run、账号写入 | 给主题契合打分、替模型决定审美 |
| 排序器 | 在已经确定的段落内改善 BPM、调性、能量衔接 | 决定哪些歌曲符合主题 |

MCP 的分工也支持这一点：Prompt 是用户主动选择的工作流模板，Tool 是模型调用的执行能力。
因此 `create_playlist_from_description` 应负责把策展方法放进对话，而工具只提供可验证事实和动作。

参考：

- [Model Context Protocol — Server primitives](https://modelcontextprotocol.io/specification/draft/server/index)
- [MCP Python SDK — Prompts](https://py.sdk.modelcontextprotocol.io/servers/prompts/)

---

## 2. 为什么不用 LLM 浮点评分

`theme_fit=0.82` 看起来规整，但它混合了模型置信度、提示词措辞、候选出现顺序和真实偏好，
不同批次的 0.82 未必可比较。更糟的是，把静态主题分放进叙事弧排序，会把“越契合越好”误读成
“分数应随位置起伏”。之前的实测已经出现主题最强的歌曲被推到末尾的情况。

文本排序研究也发现，直接让模型产出 pointwise relevance label 往往不如让它比较候选；pairwise
或 listwise 判断更能发挥模型已有的语言理解能力：

- [Qin et al., *Large Language Models are Effective Text Rankers with Pairwise Ranking Prompting*, NAACL 2024](https://aclanthology.org/2024.findings-naacl.97/)
- [Yan et al., *Consolidating Ranking and Relevance Predictions of Large Language Models through Post-Processing*, EMNLP 2024](https://aclanthology.org/2024.emnlp-main.25/)
- [Tan et al., *Can Large Language Models Understand Preferences in Personalized Recommendation?*](https://arxiv.org/abs/2501.13391)

这不意味着两两比较所有歌曲。候选先按角色分组，再在小组内做少量比较即可，避免平方级调用。

---

## 3. 推荐工作流

```text
用户描述
  ↓
LLM 保留原文并写可读的策展契约（必须 / 排除 / 参照 / 软语境 / 个性化范围 / 叙事 / 未知）
  ↓
LLM 生成目标数量 1.5–2 倍的候选池
  ↓
am_resolve_candidates 批量落到 Apple Music 真实元数据
  ↓
LLM 按角色直接比较候选，保留自然语言理由
  ↓
最终曲目 + opening / development / peak / release / landing 分段
  ↓
可选 am_optimize_order（只做段内衔接）
  ↓
am_create_playlist dry-run → 修正 → 创建
```

### 3.1 从描述中提取什么

不要求把描述变成权重表，只需保留一份可读、可被用户纠正的“策展契约”：

- **必须满足**：语言、年代、是否有人声、是否允许 explicit、必须出现的艺人或歌曲。
- **排除**：现场版、翻唱、remix、某些艺人、过于悲伤或过于激烈等。
- **仅作参照**：用户用来表达“像它的某一面”“从它出发”“与它相反”的艺人、作品、场景或年代；
  除非另有要求，不能自动加入歌单。
- **软语境 / 推断**：情绪、场景、流派边界、熟悉度、主流与冷门的比例，以及模型从描述推断但
  用户没有明确说出的含义。推断必须能被识别，不能冒充用户原话。
- **叙事**：开场方式、峰值位置、结尾质感、是否需要明显转折。
- **个性化范围**：是必需、可选还是不在范围；需要时再写明参考最近播放、Replay
  排名或音乐库的哪部分。不要默认把每个请求都拉回旧口味。
- **未知**：会显著改变结果但当前证据不足的歧义；只有这类问题才值得打断用户询问。

原始 brief 必须一直和这份契约并列保留，因为抽取本身会丢信息。“像 X、但不要 X”应同时产生
一个参照和一个排除；“不只要 city pop”不能被误写成“禁止 city pop”。这份契约留在宿主模型的
上下文中，不由 MCP 服务解析、存储或打分。

### 3.2 候选不要一步到位

目标 25 首时先提出约 38–50 首。候选不足会让 catalog 未匹配、错误版本和艺人集中度没有修正空间；
候选过大又会稀释模型注意力。1.5–2 倍是工作预算，不是音乐质量公式。

### 3.3 用语言比较，而不是打分

每个候选可以使用下面的临时结构。它留在模型上下文里，不需要服务端保存：

```json
{
  "track": "Song - Artist",
  "decision": "strong",
  "role": "development",
  "reason": "歌词中的城市疏离感贴合雨夜驾驶，同时比开场多一点推进",
  "concern": "需要确认不是现场版"
}
```

`decision` 建议只使用序数类别：

- `essential`：主题不可替代的核心。
- `strong`：明显契合。
- `bridge`：单独看未必最强，但能连接两个段落。
- `optional`：候补。
- `reject`：写清排除原因。

当两个候选争夺同一角色时，直接问：“在用户原始描述下，A 和 B 谁更适合这个位置，为什么？”
必要时交换展示顺序再判断一次，降低位置偏差。

---

## 4. `am_resolve_candidates` 的角色

这个只读工具不选歌。它把模型提出的字符串落到 Apple Music catalog，并返回：

- 输入项与 catalog ID 的对应关系。
- Apple 的真实曲名、艺人、专辑、发行日期、流派、时长和 ISRC。
- `live`、`remix`、`instrumental` 等显式版本标记。
- 相同 catalog ID 的重复候选。
- 超过两首的艺人分布提示。
- `hasLyrics` 的三态值：`true` / `false` / `null`。

`hasLyrics=false` 只说明 Apple 没提供歌词，**不能推出无人声**。歌词缺失可能来自发行、地区、版权
或数据覆盖。服务端不得把“没有证据”改写成“反面证据”。

工具返回 JSON，便于不同 MCP Host 保留输入顺序和明确字段；它不返回 `theme_fit`、综合分或自动
淘汰结果。

---

## 5. 歌词的定位

歌词可以增强 LLM 对主题和意象的理解，但不应成为默认关键路径：

1. 先靠用户描述、模型知识和 Apple 元数据完成候选池。
2. 只有候选难以取舍时，才对 shortlist 做歌词补充。
3. 获取不到歌词时保持 unknown，不自动判为器乐或低质量。
4. 第三方模糊搜索必须有标题、艺人、专辑、时长的置信度门槛。
5. 原始歌词属于授权内容；传给外部模型或持久化前应明确说明数据流。

LRCLIB 可以作为未来的可选适配器，但不应在没有精确匹配、来源可用性和内容处理策略时进入默认
选曲流程。Apple 网页播放器的未公开歌词端点同样不能当作稳定的公共 API 契约。

---

## 6. 算法仍然有用，但只做护栏

确定性代码适合：

- catalog 匹配与地区可用性；
- 同一录音去重；
- 未要求的 Live / Remix / Karaoke / Instrumental 版本提示；
- 曲目数和单一艺人上限；
- explicit、年代等明确硬约束；
- 已确定段落内部的 BPM、调性和能量衔接。

这些结果都能解释为事实或明确规则。它们不回答“这首歌是否真正懂得用户描述”。

---

## 7. 如何评价这条路线

不要用优化器 cost 证明“选得好”。建议保留一组固定自然语言 brief，做盲测：

1. 基线：模型直接生成目标数量后立即创建。
2. 新流程：扩大候选池 → catalog grounding → 角色内比较 → 分段。
3. 对比必须项、排除项、仅参照项和叙事节点是否被正确处理，再看主题契合、错误版本、重复、
   艺人集中、开场/结尾完整度和人工总体偏好。
4. 记录未匹配率与模型为修正 catalog 结果所需的循环次数。

若需要自动回归测试，应测试协议和事实边界：输入顺序、重复标记、缺失值语义、版本识别、无写入副作用。
不要把某一模型当日生成的审美答案写成永久 golden list。

仓库提供 [`examples/curation-evals.json`](../examples/curation-evals.json) 作为可复用的困难任务集。
它覆盖英文叙事、中文收听历史、日文跨年代城市感、韩文情绪边界与西文跨文化呼应；每个案例只给
brief、硬约束、语义判据和盲评问题，不给“正确曲目”。这样可以比较模型或工作流，同时不把一次
生成结果冻结成审美真值。执行步骤、结果记录模板和隐私边界见
[`examples/README.md`](../examples/README.md)。

---

## 8. 本轮明确放弃的方向

- 通用 `arc_axes`：任意字段名会污染排序器内部状态，且把 LLM 判断错误地绑到音频特征覆盖。
- `theme_fit` 浮点分：不可解释、跨批次不可校准，也不属于叙事弧。
- `hasLyrics=false → instrumental`：把缺失数据当反面证据。
- 默认抓取第三方歌词：增加网络、匹配、版权和可用性风险，却不是完成基础选曲所必需。

保留的成果是 `hasLyrics` 的零额外请求持久化、通用版本标记匹配，以及“选曲与排序是两套问题”
这一研究结论。

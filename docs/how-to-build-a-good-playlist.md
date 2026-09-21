# 怎么做一个好听又有意思的歌单

> 研究方向：**只要"好听"和"有意思"**，不要"传播/被发现/上推荐"那一套。
> 调研日期：2026-09-21 ｜ 抓取方式：curl（本机 `web_fetch` 因 DNS 假 IP 不可用）
>
> **本报告剔除了上一版里所有面向分发的内容**（30 秒钩子、艺人分散度、投稿窗口、完播率/保存率），
> 因为那些服务的是"被发现"，跟"好听/有意思"是两套标准，混在一起会自相矛盾。

---

## 0. 一句话结论

**"好听"靠物理约束（相邻衔接），"有意思"靠叙事形状（整体弧线）。**
前者有音乐人共识和实证支撑，但**听众是否真的感知到差别，证据其实很弱**（§1）；
后者不需要证明——因为顺序承载意义本身就是目的。

---

## 1. 必须先说的前提：专业人共识很强，但"听感上真的更好"没被证实

来源：[Neto, Hartmann, Luck & Toiviainen (2025). *An album is a story: Feature arcs in sequences of tracks*. PLOS ONE 20(7): e0316963](https://doi.org/10.1371/journal.pone.0316963)（芬兰 Jyväskylä 大学 "音乐、心智、身体与大脑" 卓越中心）

这篇论文自己就点出了这个尴尬：

> "while we found a significant effect of position in the album on feature values, **small effect sizes raise questions about the practical relevance of these results.**"
> （位置对特征值的影响显著，但**效应量很小，这让人怀疑结论的实际意义**。）

> "The perceptual effect that different sequences of tracks may or may not have from the perspective of the listener, however, remains to be explored."
> （**不同曲序对听众的感知影响，仍待研究。**）

而且他们引用了另一项研究：**把贝多芬作品的乐章随机打乱，既不影响愉悦度，也不影响情绪冲击力。**

**这对我们意味着什么**——我认为是两条：

1. **别把排序规则当物理定律。** 它们是有经验支撑的"手艺规范"，不是"这样做一定更好听"。
2. **但"有意思"这条轴不受影响。** 如果一张歌单的目的是"顺序本身在讲一件事"，那么即使盲听者感知不到差别，**这个顺序的价值依然成立**——它服务的是"读"，不只是"听"。

按「作曲者血脉」组织的那种叙事型歌单，走的正是第二条路。所以下面两节分开讲：**§2–§3 是"好听"（物理约束），§4–§6 是"有意思"（形状与意图）。**

---

## 2. 好听（一）：相邻衔接的四条实证约束

### 2.1 速度——两条"不要"

来自 PLOS 那篇引用的一线音乐人共识：

- **不要两首慢歌相邻**（"musicians should not put two slow songs next to each other"）
- **不要从快歌直接接到"只慢一点"的歌。** 歌手 David Brewis 的原话：
  > "if you go straight from a quite fast song [...] to just a little bit of a slower song, **it can make the slower song seem like it's dragging.**"
  > （从相当快的歌直接接到稍微慢一点的歌，**会让那首慢歌听起来像在拖**。）

  这是一个反直觉的点：**问题不在于"变慢"，而在于"慢得太少"**——降幅不够大时，听者会把前面快歌的节奏惯性带过来，慢歌就显得拖沓。要降就**一次降够**（或者中间插一个过渡）。

配套的 DJ 侧规则（[dj.studio](https://dj.studio/blog/make-a-dj-set)）：

- **大 BPM 变化需要一个"事件"**——breakdown、风格切换、能量转折，不能凭空跳。
- 正常衔接控制在 **±5–6 BPM** 内。

### 2.2 调性——Camelot Wheel

来源：[Mixed In Key — Build a harmonic DJ set](https://mixedinkey.com/workflows/build-a-harmonic-dj-set/)

每首歌的调性映射成 Camelot 码（如 `8A`，A=小调、B=大调）。**最容易的四种移动**：

```
当前 8A  →  8A（同码，最平滑）
         →  7A 或 9A（编号 ±1）
         →  8B（同编号 A↔B 互换）
```

**关键提醒**：**两首调性兼容、BPM 也接近，如果能量级不对，放一起依然会"感觉错了"。** 也就是说调性只是三个变量之一。

### 2.3 最实用的一条：不要让相邻两首在 tempo 和 key 上"同时"相似

这是音乐人共识里我觉得最可操作的一条（PLOS 引用 [6–8]）：

> 相邻曲目**不应该在 tempo 和 key 上同时太相似**；但如果**节奏差异很大，调性相近是可以接受的**。

反面也一样：**节奏相近时，就应该在调性上拉开。**

一句话：**相邻两首至少要在一个维度上有明显差异。** 这是"不无聊"的最小操作单元。

### 2.4 响度：整体前重后轻 + 相邻交替

从同一团队的前作（**51,010 张已发行专辑**的实证分析）：

- **高 valence / energy / loudness 的歌更可能被放在专辑开头**，越往后越安静。
- 更有意思的一条：**连续曲目倾向在 valence 和 energy 上"增减交替"**——不是单调上升或下降，而是锯齿式起伏。

**"交替"是"好听"和"有意思"的交汇点**：它既避免了单调（有意思），又避免了突兀（好听）。

---

## 3. 好听（二）：整体弧线——本文最有价值的一张数据表

同样是 PLOS 那篇：**130 位音乐专业人士**为假想专辑排曲序。结果专业人之间**高度一致**（用 PR 指标衡量，显著高于随机），而且**跨曲目集合、跨流派都一致**（"no effect of set"）。

### 3.1 实测的弧线形状

| 特征 | 形状 | 说明 |
|---|---|---|
| **tempo（速度）** | **倒 U**（中间高） | 首尾最慢 |
| **loudness（响度）** | **U**（两端高、中间低） | |
| **valence（愉悦度）** | **U**（两端高、中间低） | |
| **arousal（唤醒度）** | **U**（两端高、中间低） | |

具体 z-score（首位 / 末位）：

```
valence    首位 +0.459   ← 全场最高    末位 −0.006
loudness   首位 +0.36                  末位 +0.006
arousal    首位 +0.26                  末位 −0.07
tempo      首位 −0.07                  末位 −0.08   ← 两端都最慢
```

**怎么读这张表**（论文自己给的解释，用 circumplex 情绪模型）：

- **开场曲和收尾曲都是"高愉悦 + 高唤醒"** —— 对应兴奋、愉悦、幸福。
- **中段是"低愉悦 + 低唤醒"** —— 对应论文原话："depression, boredom, and tiredness"（抑郁、无聊、疲惫）。

**这跟"通篇保持高能"的做法完全相反。** 专业人的直觉是：**允许中间沉下去**。

### 3.2 共识最高的位置是"第一首"

> "particularly high levels of agreement were found for **the first position** of the albums."

也就是说：**开场曲是专业人分歧最小、最当回事的位置。** 论文里引的一线说法：

> "if you don't catch people right off the bat, they might not hear the hits at the end."

**这跟我们在 §2 讲的物理约束是两件事**——§2 说"衔接"，这里说"第一首承担整张的承诺"。两件事都指向同一个动作：**第一首要单独打磨。**

### 3.3 专辑偏向 "Man in a hole"（先落再起）

> "our findings suggest that album production favors the **Man in a hole** arc."

"Man in a hole" = **valence 先下降、再上升**（掉进坑里，再爬出来）。这正好对应 §3.1 的 U 型 valence 曲线。

**这是本次调研里"好听"和"有意思"唯一的直接交汇点**：那个被文学和音乐共同偏爱的形状，同时也是一个符合专业人响度/情绪直觉的形状。

---

## 4. 有意思（一）：把叙事弧线当模板用

### 4.1 六种基本情感弧（Vonnegut → 实证）

来源：[Reagan et al. (2016). *The emotional arcs of stories are dominated by six basic shapes*. EPJ Data Science 5:31](https://doi.org/10.1140/epjds/s13688-016-0093-1) ｜ 科普版：[MIT Technology Review](https://www.technologyreview.com/2016/07/06/158961/data-mining-reveals-the-six-basic-emotional-arcs-of-storytelling/)、[EurekAlert](https://www.eurekalert.org/news-releases/510292)

对 1,327 部（另一说 1,700+）英文小说做情感分析 + 数据挖掘，发现叙事弧线收敛到**六种基本形状**：

| 形状 | 情绪走向 | 文学原型 |
|---|---|---|
| **Rags to riches** | 持续上升 | 《爱丽丝镜中奇遇》 |
| **Tragedy**（riches to rags） | 持续下降 | 《罗密欧与朱丽叶》 |
| **Man in a hole** | **先落，再起** | Vonnegut 的经典例子 |
| **Icarus** | **先起，再落** | 伊卡洛斯神话 |
| **Cinderella** | 起–落–起 | 灰姑娘 |
| **Oedipus** | 落–起–落 | 俄狄浦斯 |

**"最受欢迎"的形状**（按下载量相关性）：

> 最受欢迎的是 **Icarus** 和 **Oedipus** 弧，以及把基本形状串起来的复杂弧——尤其是**两个连续的 man-in-a-hole**，和 **Cinderella 接 tragedy**。

### 4.2 怎么用到歌单上

**核心动作：显式选一个形状，让顺序成为一条论证，而不是一堆歌的排列。**

- 选 **man in a hole**：最安全，也是专业人排专辑时实际偏好的形状（§3.3）。
- 选 **Icarus**：如果你想让歌单"崩掉"——最后几首把之前建立的东西拆掉。适合概念性强的主题。
- 选 **两个连续的 man-in-a-hole**：这是"最受欢迎"的形状，意思是**允许两次跌落和两次爬升**，而不是只有一个大弧。对 30 首以上的歌单尤其合适——**一个 40 分钟的大弧太难撑，两个 20 分钟的中弧更容易成立。**
- 选 **Cinderella 接 tragedy**：先给希望、再彻底拿走。适合主题本身就是"幻灭"的歌单。

**注意**：文学研究用"愉悦度"衡量，而音乐还有一个"唤醒度"维度（§3.1）。所以音乐的可行形状比文学多——**可以 valence 走高、arousal 走低**（"越来越平静的明亮"）这种文学里没有的组合。

---

## 5. 有意思（二）：一线策展人实际怎么做

来源：[Juno Daily 对 Ben Jones（Two-Piers 厂牌）的访谈](https://www.juno.co.uk/junodaily/2026/05/28/ben-jones-two-piers-interview-theres-no-magic-formula-you-just-need-to-be-careful-to-avoid-going-mad/)（合辑 *Bridges Towards Open Spaces: Circadian Rhythms 1967–2025*）

这一篇是本次调研里**最实操**的材料，因为说话的人是真的靠这个吃饭的。原话摘录：

> **"When I put together my compilations, I always choose a start and an end track, then colour it in from there."**
> （我做合辑时，**总是先定开场曲和收尾曲，然后从中间往里填色**。）

> **"It generally comes from one song – perhaps the closing track, then I build it around that."**
> （通常是从**一首歌**出发——往往是收尾曲——然后围绕它搭。）

> **"there's no magic formula to putting one together – you just need to be careful to avoid going mad over the song selection."**

> **"I like a comp I can put on that takes me somewhere for an hour or so, I like to be fully immersed and invited into the curator's world."**
> （我喜欢那种能**把我带走一小时左右**的合辑，我喜欢完全沉浸、**被邀请进策展人的世界**。）

> **"With Night Train, I wanted to set the scene for a journey and capture the feeling of going from one point to another."**

**其中最有价值的一条是"杂与统一"**：那篇访谈形容他的选曲"on paper, it sounds disparate but his deft touch has added a layer of cohesion"（纸面上看很杂，但他的手艺加了一层凝聚力）。

> **这就是"有意思"的操作性定义：材料要够杂（有信息量），气质要够统一（不散架）。**

以及他的曲目来源：**朋友之间互录的磁带**、唱片店、电台节目（Worldwide、NTS、Soho Radio 等）。他自己说 *Music For The Stars* 的缘起就是"我和朋友互相做磁带、互相介绍音乐"。

→ 对歌单的启发：**"有意思"往往来自"跨越距离的连接"**——不同年代、不同流派、不同语种的东西，因为某个共同点被放在一起。**如果所有歌都是同一流派同一时期，它再顺也不会"有意思"。**

---

## 6. 有意思（三）：ISO 原则——怎么把听众"带走"

来源：[Ding, Fu, Tang & Zhang (2026). *State-Adaptive Versus Target-First Music Sequencing for Working Adults With Occupational Stress*. medRxiv preprint](https://doi.org/10.64898/2026.08.05.26359641)（上海交通大学医学院附属精神卫生中心 + 清华大学心理与认知科学系）

**⚠️ 这是预印本，未经同行评议**（论文自己声明"should not be used to guide clinical practice"）。

**iso principle（等感原则）**：音乐治疗的经典原则——**先用与听者当下情绪状态匹配的音乐，再逐步把情绪引向目标状态**。论文把它形式化成两套排序策略并做了随机对照试验：

- **ISO**：state-adaptive（先匹配当下状态，再逐步引导）
- **DUL**：target-first（直接上"提气"的歌，一步到位）

**方法**：120 名有职业压力的中文母语上班族，1:1 随机分到 ISO / DUL，连续 5 个晚上在自己家里通过网络平台听音乐。

**结果（要如实说）**：

- **主要结局（职业压力 / 焦虑 / 抑郁症状）方向上都偏向 ISO，但没有达到 Holm 校正后的统计显著。**
  （职业压力 −2.45 分，95% CI −7.08 ~ 2.18；焦虑 −2.34，−5.22 ~ 0.54；抑郁 −3.60，−7.19 ~ −0.01）
- **探索性结果**：两套排序策略产生了**不同的 session 内情绪轨迹**（valence / arousal / dominance 三个维度），而且 ISO 完成者的"情绪一致性"随天数增加。
- **结论**：**排序策略确实改变了聆听过程中的情绪走向，但临床症状改善未被证实。**

**对做歌单的启发**：

> **开场不要硬拽。先用一首"接住"听众当下状态的歌，再开始移动。**

这跟 Apple 官方策展规范里"开头放爆款抓注意力"是**直接冲突**的（见 §7）。对"好听/有意思"的歌单，ISO 更合用——**因为"被抓住"和"被带走"是两种不同的体验，而后者才是你想在这条轴上追求的东西。**

---

## 7. 冲突清单：这些建议之间是打架的，得选边

调研中反复出现互相矛盾的建议。**这是正常的**——它们服务不同目标。列出来免得你被绕晕：

| 议题 | A 方 | B 方 | 什么时候选哪边 |
|---|---|---|---|
| **开场曲** | **Apple 官方**：放爆款抓注意力 | **ISO 原则**：先匹配听众当下状态 | 传播选 A；"被带走"选 B |
| **开场曲** | Apple 官方：放爆款 | **PLOS 实证**：专业人排专辑时开场是**低 tempo**、高 valence/arousal | 想跟专业人一致 → 选"慢速但明亮"的开场，而不是"最炸"的开场 |
| **中段** | 直觉/传播：保持高能别掉 | **PLOS 实证**：专业人让中段**低 valence + 低 arousal** | 专辑式整体体验选后者 |
| **艺人** | OneStopWatch：同一艺人 ≤2 首 | **血脉/合辑式策展**：同源恰恰是立意 | 发现型选前者；叙事型选后者 |
| **长度** | OneStopWatch：20–30 首 | Apple 官方：15–50 首；Erasmus 论文：session 越长跳过率越高 | 都指向"别太长" |
| **响度** | 51k 专辑实证：前重后轻 | PLOS 130 人：**首尾都高、中间低**（U 型） | 不冲突——"前重后轻"是长时段趋势，"U 型"是 5 段位置的形状 |
| **顺序重不重要** | 音乐人高度一致认为重要 | **贝多芬洗牌实验**：打乱乐章不影响愉悦度和情绪冲击 | 见 §1：当手艺规范用，别当物理定律 |

---

## 8. 一套可操作的流程（把上面综合）

如果你想认真做一张"好听 + 有意思"的歌单，我建议这个顺序：

1. **先选形状**（§4）。六选一，或者"两个连续的 man-in-a-hole"。**把形状写下来**——这是你后面所有决定的裁判。
2. **先定第一首和最后一首**（Juno 的做法）。第一首是专业人共识最高、最该单独打磨的位置（§3.2）；最后一首往往是你整张的"论点"（访谈里说常常从收尾曲出发倒推）。
3. **用 ISO 决定开场情绪**（§6）：不是"最炸的一首"，而是"能接住听众、又能指向形状第一段走向的那首"。
4. **填中间**，每放一首就检查三条：
   - 不要两首慢歌相邻（§2.1）
   - 不要从快歌直接接到"只慢一点"的歌——**要降就一次降够**（§2.1）
   - **相邻两首至少在 tempo / key 之一上明显不同**（§2.3）
5. **检查整体形状**：把每首按"高/中/低"粗标 valence 和 arousal，看曲线是不是你要的形状。中段该沉就让它沉（§3.1）。
6. **检查"杂与统一"**（§5）：材料够不够杂（年代/流派/语种跨度）？气质够不够统一（有没有一条贯穿的线索）？**两条缺一条，"有意思"就立不住。**
7. **唯一的真检验：整张按顺序听一遍，记录你在第几首想按跳过。** 想跳的位置就是问题位置——这一层没有任何工具能替代。

---

## 9. 数据从哪来：Apple 不给，但可以绕（**本节是对初版错误结论的更正**）

> ⚠️ **更正说明**：本报告初版在这里写了"这些数据不存在，只能靠耳朵"。**那个结论是错的。**
> 经提醒后我重新找，发现有一条免费、无需密钥的链路，已实测跑通并对歌单做了体检。

### 9.1 为什么不能直接用 Apple / Spotify

- **Apple Music 的 catalog API 不提供** tempo / key / loudness / energy / valence ——
  实测完整字段清单只有：`albumName artistName artwork composerName discNumber durationInMillis
  genreNames hasLyrics isAppleDigitalMaster isrc name playParams previews releaseDate
  trackNumber url`。
  （但有个线索：`include=audio-analysis` 返回 **400 "Insufficient Permissions"** ——
  说明这个关系**存在**，只是网页 token 权限不够。**如果用自己申请的 MusicKit 开发者密钥，可能能拿到。未验证。**）
- **Spotify 的 `audio-features` 已于 2024-11-27 对新应用关闭**（同日一起下线的还有 `audio_analysis`、
  `recommendations`、related artists、featured playlists），没有官方替代。
  来源：[DEV — *Spotify's audio_features API died in 2024*](https://dev.to/birrings/spotifys-audiofeatures-api-died-in-2024-heres-what-i-built-to-replace-it-3dn3)
- **AcousticBrainz 已于 2022 年关闭**（数据以一次性 dump 形式冻结发布）。

### 9.2 实测跑通的链路

```
Apple Music 曲目  ──►  ISRC（Apple 直接给）          ← 关键：ISRC 是跨库连接的标准钥匙
       │
       └─► https://api.reccobeats.com/v1/track?ids=<ISRC>      免费、无需密钥
                    └─► 返回 track UUID
                          └─► /v1/audio-features?ids=<UUID>
                                    └─► tempo, key, mode, loudness, energy, valence,
                                        danceability, acousticness, instrumentalness,
                                        liveness, speechiness   ← Spotify 那 11 项
```

实测样例（Bohemian Rhapsody，ISRC `GBUM71029604`）：

```json
{"isrc":"GBUM71029604","acousticness":0.271,"danceability":0.411,"energy":0.404,
 "instrumentalness":0.0,"key":0,"liveness":0.3,"loudness":-9.928,"mode":0,
 "speechiness":0.0511,"tempo":71.068,"valence":0.226}
```

**覆盖率实测**：一张 39 首的实例里 **37 首命中**（缺的 2 首是 2025/2026 的新单曲，尚未被收录）。
日文曲目实测抽 14 首，**14/14 全中**。

已封装成工具 **`playlist_flow.py`**（自动用 ISRC 查、缓存到本地、带速率控制）。

### 9.3 用它对一张 39 首实例做的体检结果

**这是本次调研最有意思的一个结果**：那张歌单是我凭直觉做的（按作曲者血脉分七个乐章），
实测下来 **4 项特征里有 3 项自动符合了专业人的弧线模式**：

| 特征 | 我的歌单实测 | PLOS 专业人模式 | 判定 |
|---|---|---|---|
| **energy** | 高 → 中 → 高 | U 型 | ✅ 符合 |
| **loudness** | 高 → 低 → 高 | U 型 | ✅ 符合 |
| **tempo** | 低 → 高 → 低 | 倒 U 型 | ✅ 符合 |
| **valence** | **0.745 → 0.635 → 0.503（单调下降）** | U 型（两端高） | ❌ **不符** |

**识别出的形状是 Tragedy（持续下降），不是 PLOS 说的 Man in a hole。**
也就是说：我在设计时以为自己在做"海底 → 夏末"的下降叙事，**响度/能量/速度确实做成了专业人的拱形，
但情绪（valence）走成了一路下沉。** 这是数据第一次告诉我一件我自己没意识到的事。

**相邻衔接的问题**（节拍折叠到 [70,160) 后比较，共 36 个衔接）：

| 检查项 | 结果 |
|---|---|
| 两首慢歌相邻（§2.1 明确禁止） | ⚠️ **2 处**：#4→#5（夜明けと蛍 80 → 始発とカフカ 80）、#8→#9（雲と幽霊 85 → あの夏に咲け 80） |
| "只慢一点"（降幅 <12%，会让慢歌显得拖） | ⚠️ **10 处** |
| 相邻在 tempo 和 key 上同时相似（§2.3） | ⚠️ 2 处 |
| 能量骤变且调性不兼容（突兀） | ⚠️ **7 处** |

**⚠️ 关于 tempo 的一个技术说明**：BPM 估计有**倍频歧义**——同一首歌可能被估成 90 或 180。
实测里 13月 被估成 205.6、夜想 203.0、冬眠 180.0，几乎肯定是 ~100 的两倍读数。
所以 `playlist_flow.py` 会把 BPM 折进 [70,160) 再比较（表格里用 `*` 标出被折叠的值）。
**不做这一步，"两首慢歌相邻"会从 2 处误报成 8 处。**

### 9.4 据此重建的一版（前后对比）

用上面的数据 + 模拟退火（`playlist_optimize.py`）重排了一张同题材的歌单。
**结构上唯一的改动**：把情绪最低的一组从**结尾**挪到**中段**——
这一步同时修好了弧线和叙事（起点 → 展开 → **落** → 转出 → 回升）。

| 检查项 | 旧版 | 新版 |
|---|---|---|
| 两首慢歌相邻（§2.1 禁止） | ⚠️ 2 处 | ✅ **0** |
| "只慢一点"（降幅<12%） | ⚠️ 10 处 | ✅ **0** |
| 相邻在 tempo 和 key 上同时相似 | ⚠️ 2 处 | ✅ **0** |
| 能量骤变且调性不兼容 | ⚠️ 7 处 | ✅ **0** |
| **弧线形状** | ❌ **Tragedy（单调下降）** | ✅ **Man in a hole（落-起）** |
| valence 三段 | 0.745 → 0.635 → 0.503 | **0.729 → 0.531 → 0.615** |
| energy / loudness | U ✅ | U ✅ |
| **tempo（期望倒 U）** | 倒 U ✅ | ⚠️ **变成单调上升** |
| 优化目标 cost | 104.46 | **19.41** |

**一个没能同时满足的项，得说清楚**：**tempo 的倒 U 型这一版没做到。**
原因是结构性的——要 tempo 呈倒 U，首尾两段就都得比中段慢；但按主题分块，
第一段（BPM 80–130）和最后一段（BPM 86–103）**本身就不比中段慢**。
想同时满足，就必须**打散主题分块**（把慢曲调到两端），那是拿"有意思"换"好听"。
我把权重给了相邻衔接（权重 6/3/3），所以牺牲了 tempo 的形状。**这是个可以推翻的取舍，不是做不到。**

### 9.5 哪些能自动、哪些仍然不能

| 层面 | 能否自动 | 说明 |
|---|---|---|
| §2 相邻衔接（BPM/调性/响度/能量） | ✅ **能** | 靠 ReccoBeats |
| §3 整体弧线形状 | ✅ **能** | 同上 |
| §4 选定某种叙事弧 | ⚠️ 半自动 | 工具能告诉你**当前是什么形状**，但"想要哪种形状"是审美决定 |
| §5 "有意思"的线索寻找 | ✅ **能** | 靠 Apple 的 `composerName`/`albumName`/`trackNumber` |
| **"这段到底好不好听"** | ❌ **不能** | 见 §1：连贝多芬洗牌实验都没测出差别。**最终仍要靠耳朵。** |

---

## 10. 来源

**实证研究（核心）**
- [Neto, Hartmann, Luck & Toiviainen (2025). *An album is a story: Feature arcs in sequences of tracks*. PLOS ONE 20(7): e0316963](https://doi.org/10.1371/journal.pone.0316963) —— 130 位专业人士排曲序；弧线数据表出自 §3.1/§4.1（PDF 已下载并解析）
- [Reagan et al. (2016). *The emotional arcs of stories are dominated by six basic shapes*. EPJ Data Science 5:31](https://doi.org/10.1140/epjds/s13688-016-0093-1) —— 六种弧线 ｜ 科普版：[MIT Technology Review](https://www.technologyreview.com/2016/07/06/158961/data-mining-reveals-the-six-basic-emotional-arcs-of-storytelling/)、[EurekAlert](https://www.eurekalert.org/news-releases/510292)
- [Ding, Fu, Tang & Zhang (2026). *State-Adaptive Versus Target-First Music Sequencing*. medRxiv **预印本，未经同行评议**](https://doi.org/10.64898/2026.08.05.26359641) —— ISO 原则的随机对照试验（PDF 已下载并解析）

**一线实践**
- [Juno Daily：Ben Jones（Two-Piers）访谈](https://www.juno.co.uk/junodaily/2026/05/28/ben-jones-two-piers-interview-theres-no-magic-formula-you-just-need-to-be-careful-to-avoid-going-mad/) —— 合辑策展人的实际做法
- [BBC Radio 4 — *The Art of Sequencing*](https://www.bbc.co.uk/programmes/b01q95y6)（Guy Garvey 主持，Nick Mason、Peter Hammill 等参与）—— **我只拿到节目介绍页，未能收听内容，因此不引用其中观点**；但它本身说明"曲序是一门艺术"这件事在业界是被认真讨论的
- [dj.studio — How To Make A DJ Set](https://dj.studio/blog/make-a-dj-set)（能量曲线、±5–6 BPM、大变化需要"事件"）
- [Mixed In Key — Build a harmonic DJ set](https://mixedinkey.com/workflows/build-a-harmonic-dj-set/)（Camelot Wheel）
- [Digital DJ Tips — The "Miniset" Method](https://www.digitaldjtips.com/miniset-method-music-free-lesson/)（3–5 首成组）
- [AllAboutJazz — How To Give Your Album The Perfect Flow](https://www.allaboutjazz.com/news/how-to-give-your-album-the-perfect-flow/)（A/B 面思维、把长曲/难曲放后面、张力与释放）

**未能获取**
- PNAS《Predictive processes shape individual musical preferences》(2025)：**403**，未能读到
- David Huron《Sweet Anticipation》正文：只找到书目条目，**未读到内容，故本报告不引用其理论细节**
- BBC《The Art of Sequencing》音频内容：未能收听

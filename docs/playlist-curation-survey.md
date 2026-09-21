# 怎么做出好歌单 —— 教程与讨论调研

> 调研日期：2026-09-21 ｜ 抓取方式：curl（本机 `web_fetch` 因 DNS 假 IP 不可用）
> 所有引文都标注了来源链接。**§8 是我们自己工具链的实测结论，§9 是拿这些原则对照我们自己那张歌单的诊断。**

---

## 0. 先给结论

调研下来，**"好歌单"有三套互不兼容的标准**，先想清楚你要哪一套，否则会自相矛盾：

| 目标 | 评价标准 | 代表来源 |
|---|---|---|
| **被发现**（给艺人带流量、上推荐位） | 完播率、保存率、30 秒内不跳过 | Spotify 算法指标、editorial 投稿规则 |
| **被听完**（个人听感体验） | 顺序有意义、能量有走向、不刺耳 | DJ/混音理论、High Fidelity 式 mixtape 规则 |
| **被理解**（概念/叙事歌单） | 主题单一、每首有存在理由、顺序承载叙事 | Apple 官方策展规范、OneStopWatch 框架 |

一张按「作曲者血脉」组织的叙事型歌单属于**第三类**（被理解）。但按第一、二类的标准，它会有几处明显违规——见 §9。

---

## 1. 最权威的一份：Apple 官方给策展人的规范

来源：[Apple Music Curator Best Practices](https://help.apple.com/itc/musiccuratorbestpractices/en.lproj/itc1ad916359.html)（Apple 官方帮助文档，实测可抓）

原文要求逐条：

- **歌单长度：15–50 首**
- **每张歌单必须有单一主题**（"a single theme that pulls the songs together"）
- **把歌单当成一次聆听体验，而不是一串歌**（"Think of each playlist as a listening experience, not just a list of songs"）← 这句基本是全部的纲领
- **开头放一首爆款/大歌来抓住听众**（"Lead with a breakout hit or a big song to grab the listener's attention"）
- 主题要贴合自己品牌的真实声音，**避开短期热点，要常青（evergreen）**
- 动态歌单要**保持固定更新节奏**（例如每周五更新）
- 至少维护 5 张歌单 + 1 张动态歌单
- 必须通过网页版 Playlist Creator 管理（macOS/iOS 客户端做不到）

> ⚠️ 两点限定，别误用：① 这是给**有 Curator profile 的合作策展人**的准入要求，不是给个人歌单的；② 它服务的是"被发现"这个目标（所以才有"开头放爆款"）。但**"单一主题 + 当成一次体验 + 15–50 首"这三条对个人歌单同样成立**，而且它是唯一来自平台的权威口径。

---

## 2. 最完整的一套教程：OneStopWatch 七步法

来源：[How to Curate Music Playlists: 7 Steps for Success](https://resources.onestowatch.com/how-to-curate-music-playlists/)（OnesToWatch，音乐发现编辑 Kai Eldridge 撰写，2026-08-08 更新）

七步（我按可操作性重排了说明）：

1. **用三个词定义 vibe** —— 例："late-night / introspective / cinematic"。这是 DJ Will Gill 的方法，目的是让长序列的调性保持一致。然后扩写成**一句话 brief**（"A slow-burn late-night drive featuring independent artists with strong atmospheric production"）。
   - 决策点：**写成"Melancholic evenings"而不是"sad songs"**——越具体越好；写不成一句话就说明主题还不够窄。
2. **选 5–8 首"锚曲"** —— 它们定义整张歌单的"声音温度"，后续每首都要相对它们证明自己配得上。
3. **先大量粗放地堆，再狠心砍** —— 先堆 40–60 首候选，砍到 20–30 首。**这个阶段完全不要管顺序。**
4. **划分四个区：开场 / 中段 / 峰值 / 结尾** —— 开场抓注意力，中段铺陈语境，峰值放能量或情绪最高点，结尾要**强化整体氛围**。
   - 决策点：**"三分钟规则"**——歌曲必须在**听众接触歌单的前三分钟**内证明自己（不是它自己播了三分钟）。**如果前 3 首没立住主题，掉线率会陡增。**
5. **用 tempo / key / energy 打磨过渡** —— 逐对检查相邻两首，确保没有哪一处让人想按跳过。
   - 决策点：**突然的风格断层（比如从 ambient 跳到 aggressive EDM）会让听众不再信任这个主题。**
6. **平衡"耳熟的"和"新发现的"** —— 熟曲提供安全感，生曲提供前进动力。
   - 决策点（**这条最狠**）："**避免同一位艺人出现超过一次；同一艺人超过两首是常见的策展失败**。"
7. **命名、设计、维护** —— 标题用**听众真的会去搜的词**（不是只有社交媒体上好看的俏皮话）；每 15–20 分钟做一次周维护，增删 2–3 首。

**FAQ 里的关键数字**：

- **20–30 首**是刻意策展的最佳区间（约 1–2 小时）。**超过 50 首通常就退化成"歌单垃圾场"**，编辑身份被稀释。
- "**策展歌单**"与"**歌曲堆**"的区别不是单曲质量，而是**它是一部旅程还是一座图书馆**。
- 策展已是一个职业：Spotify/Apple Music/Deezer 的编辑、电台与场地、品牌与代理、独立歌单主。

---

## 3. 经典 mixtape 规则（High Fidelity 那一套）

来源：[Esquire India — How To Build A Playlist That Doesn't Suck](https://www.esquireindia.co.in/culture/books-and-music/how-to-build-a-playlist-that-doesnt-suck)

被反复引用的《High Fidelity》mixtape 法则，这篇解释得最清楚：

- **第一首至关重要——它负责钩住听众**；**第二首确认整张的调性**；之后凭直觉走。
- **开场曲要"暗示"vibe，但不要过早冲到顶点**（原文用的是 Anderson .Paak 的 Come Down、Fleetwood Mac 的 Everywhere 作例）。
- **像 DJ 那样流动，而不是像随机播放按钮**：注意 BPM，突然从 Kendrick Lamar 切到 Frank Sinatra 会很突兀。
- **混搭流派/年代/艺人，但必须互相补足**："应该让人意外，但不应让人迷失。"
- **歌单是活的东西**，要持续增删。
- **结尾决定记忆**："人们会记得离开前最后一首。要以爆点结束，还是像 Frank Ocean 的 Pink + White 那样淡出？**无论如何，绝不要让歌单结束在静音里。**"
- 对算法的态度：**用它做起点，但别被它牵着走**。

---

## 4. 最技术的一层：DJ 圈的排序工程

如果你要的是"被听完"，这一层比上面的通用建议更可操作。

### 4.1 能量曲线（dj.studio）

来源：[How To Make A DJ Set: In-Depth Guide](https://dj.studio/blog/make-a-dj-set)

一句话规划整场的能量走向，五个动作：

```
Open    —— 建立 vibe（groove、留白、hook）
Build   —— 分「台阶」抬升 tempo/energy，不要跳跃
Peaks   —— 1–3 个高潮；不要把高潮叠在一起
Resets  —— 大时刻之后要「喘气」（breakdown、清唱、冷门曲）
Close   —— 一个记得住的收尾或优雅落地
```

**每个过渡检查三件事**：

- **Phrasing**：是否在 8/16/32 小节的边界上衔接；
- **Key**：调性是匹配还是"有品味地移动"（关系调、五度、升能变化）；
- **Tempo**：能否在 **±5–6 BPM** 内对齐而不出伪影。

另一条实用规则：**短场次 = 更窄的 BPM 范围和更紧的主题；长场次 = 有空间做 tempo/key 的弧形和风格探索。** 选曲时准备需求量 **2–3 倍**的候选。

### 4.2 Miniset 法（Digital DJ Tips）

来源：[The "Miniset" Method](https://www.digitaldjtips.com/miniset-method-music-free-lesson/)

把音乐按 **3–5 首一小组**组织，而不是逐首思考"下一首放什么"。每一组内部天然自洽（同年代、同 vibe、同受众、同调性、同能量都行——**按什么分组不重要，重要的是组内一定流得通**）。

好处：不用在几千首里滚动找下一首，进入某一组之后"闭着眼挑都行"。

### 4.3 Camelot Wheel 和声混音（Mixed In Key）

来源：[Build a harmonic DJ set](https://mixedinkey.com/workflows/build-a-harmonic-dj-set/)

- 每首歌的调性映射成一个 Camelot 码（如 `8A`，**A = 小调，B = 大调**）。
- **最容易的四种移动**：停在同一个码；**编号 +1**；**编号 −1**；**同编号 A/B 互换**。
  （例：当前 `8A` → 最优 `8A`，可试 `7A` / `9A`，或 `8B`。）
- **BPM**：小变化自然；**大变化需要一个"事件"**（breakdown、风格切换、能量转折）。
- **Energy Level 决定情绪走向**：想推进就逐步提高；想保持就维持同一档；想制造新段落就做一次明显的能量跳变；**想给下一个 build 留空间就把能量降下来**。
- 注意：**两首调性兼容、BPM 也接近，如果能量级不对，放一起依然会"感觉错了"。**

### 4.4 一个现成的工具思路

[fdemusso/SpotifyMixer](https://github.com/fdemusso/SpotifyMixer) —— 一个 Python CLI，**按 BPM + Camelot 调性自动重排歌单**（滑动 BPM 窗口排序 + Camelot 匹配 + 缺失回退），改之前自动备份。这是"把 §4.3 自动化"的现成参考实现（面向 Spotify，见 §8 关于 Apple Music 的差异）。

---

## 5. 学术证据：跳过率研究（结论反直觉）

来源：[Predicting Skipping Behavior in Music Streaming: The Impact of Recommendation Types on User Engagement](https://thesis.eur.nl/pub/72722/Thesis-final_v2_BENCE_BILIBOK_2024.07.18.pdf) —— Erasmus University Rotterdam, Erasmus School of Economics 硕士论文（Bence Bilibók, 2024-07-18），用 **Spotify 真实 session 级数据**，把跳过细分成四个时间点（不只是"跳没跳"），用 Ordered Logistic Regression + Ordinal Forest + SHAP 做归因。

**摘要里的主结论**：

> "Users are generally most engaged in algorithmically created personalized recommendations and less with mood or genre based automated radio stations. The users own created playlists performed better than radios overall, and no real conclusion can be said about the song recommendations made by industry professionals."
>
> （用户对**算法生成的个性化推荐**投入度最高，对**基于情绪/流派的自动电台**最低。**用户自建歌单整体好于电台**；而**行业专业人士的推荐无法得出明确结论**。）

**SHAP 归因里更具体的发现**（针对"开头就跳"这个点）：

- **用户自建歌单 → 开头跳过概率更高。** 论文原话："If a track is listened to from the user's own playlists, then it contributes to a higher skipping probability at the first point."（符合直觉：在自己歌单里是在"翻找"，不是在"听"。）
- **算法个性化歌单 → 开头跳过概率明显最低**（"clearly the biggest negative effect on skipping probability at this point"）。
- **编辑歌单（editorial）→ 中性**，正负影响相抵。
- **自动电台 → 开头跳过概率高**（和个性化歌单同为机器生成，效果却相反——这点论文也觉得有意思）。
- **播放前有停顿 → 降低跳过概率；连续不停地听 → 提高**在该点的跳过概率。
- **session 长度**：**"a session of 20 songs leads to a higher skipping probability in each song"**；较短 session 的开头跳过概率更低，且这个效应强一倍。

> 对我们的意义：**"20 首"这个门槛在两端都出现**——OneStopWatch 说 20–30 首是最佳区间，这篇论文说 20 首的 session 会推高每首的跳过率。两边都指向"**别做太长**"。

**行业侧对应的算法信号**（来源：[iMusician — Spotify Playlisting Strategy in 2026](https://imusician.pro/en/resources/blog/spotify-playlisting-strategy-2026)）：

- **Save rate**（保存率）、**Completion rate**（完播率）、**User playlist adds**（被用户加进自己歌单的次数）、**Follower growth**。
- 明确提到：**"Skips at the 30-second mark register as negative feedback, so strong openings and early hooks really matter."**（30 秒处跳过会被记为负反馈，所以开头和早期 hook 非常关键。）
- 投稿时的描述要具体："melancholic indie folk for late-night drives" 优于泛泛的 "pop"。

---

## 6. 生态视角：三类歌单，三种玩法

同样来自 iMusician 那篇，值得单独记一下，因为它解释了为什么"好歌单"的标准会打架：

| 类型 | 例子 | 怎么进去 | 目标 |
|---|---|---|---|
| **编辑歌单** | RapCaviar、New Music Friday | 只能通过 Spotify for Artists 在发行前投递（**发行日窗口关闭**） | 一夜百万播放 |
| **算法歌单** | Discover Weekly、Release Radar、Daily Mix | **无法投递**，只能靠互动信号（保存、完播、被加入歌单）喂出来 | 持续曝光 |
| **独立策展人歌单** | 博客、社群、tastemaker | 直接联系策展人 | 最可达，且**能给算法喂数据** |

三层是连着的：独立歌单 → 互动数据 → 算法推荐 → 积累的profile → 吸引编辑注意。

---

## 7. 社区讨论这一层：抓取受限（我试了什么，结果如何）

你问的是"教程**和讨论**"。坦白说：**教程这一层我拿到了不少，讨论这一层是这次调研最薄的部分。** 逐条报告我试过什么：

### 7.1 英文社区：Reddit 全线不可达

| 路径 | 结果 |
|---|---|
| `reddit.com/r/*/search.json` | **403** |
| `old.reddit.com/r/*/search` | 200，但返回的是 "Welcome to Reddit" 拦截页（三次搜索返回字节数完全相同 = 同一个通用页，无真实内容） |
| `redlib.catsarch.com` | **429** |
| `safereddit.com` | 200，但内容是 Anubis 的**浏览器验证页**（"Verifying your browser"） |
| `libreddit.privacydev.net` | **502** |

**结论：从这台机器拿不到 Reddit 上的讨论。** 所以"r/spotify / r/AppleMusic / r/DJs 里大家怎么吵歌单该不该排序"这个问题，**我无法回答**，不能用我读过的印象代替。

### 7.2 替代源也几乎没有内容

- **Hacker News（Algolia API，可用）**：搜 `playlist` 有 4178 条，但**几乎全是产品发布帖，不是方法论讨论**。比较相关且有点分量的只有：
  - [Spotify revises TOS to allow transfers of user-created playlists](https://news.ycombinator.com/item?id=42436072)（546 分 / 128 评论）
  - [FreeYourMusic lets users migrate their playlists off Spotify](https://news.ycombinator.com/item?id=42436072)（377 分 / 262 评论）
  - Ask HN：*Does anybody manage their own music collection anymore?*（8 分 / 10 评论）、*Options for curating a music library in the 2020s*（2 分 / 1 评论）
  - 这些谈的是**歌单的可携带性/所有权**，不是"怎么排顺序"。
- **Stack Exchange API（可用）**：`music.stackexchange.com` 搜 "playlist order" **只返回 1 条**，且是 [Reading emotions from a song](https://music.stackexchange.com/questions/48549/reading-emotions-from-a-song)（1 分）——不相关。

### 7.3 中文圈：能抓到站，抓不到"方法论"

- **中文站本身能抓**：sspai、豆瓣、简书、B站、36kr 都返回 200（知乎、Medium 是 403）。
- **豆瓣播客有一期直接对题**：[《54 如何打造 1.5 亿播放量的歌单？（嘉宾：陈北及）》](https://www.douban.com/podcast_episode/317787)。**但我抓不到正文**——页面是 JS 渲染的，HTML 里没有文字。**我没听过这期，所以不引用它的任何观点。** 同名的网易云音乐人页面连 TCP 都连不上（http=000）。
- **一篇看着对题、实测不对题的**：[豆瓣小组「自己做🍉歌单的一些小 tips」](https://www.douban.com/group/topic/300730531/) —— 抓下来发现是**粉丝刷榜/刷播放量的操作技巧**（控制在"一小时多几秒到几十秒"、首小时点赞、循环播放、下载后删除等），**与策展无关**，我不把它算作材料。
- **知乎相关页全部 403**。

### 7.4 所以这份调研的"讨论层"实际来自哪里

不是论坛，而是**带强烈实践者视角的长文**（它们本身是 DJ/策展人社群产出的方法论）：

- [Digital DJ Tips](https://www.digitaldjtips.com/miniset-method-music-free-lesson/)（DJ 培训社群，作者 Phil Morse 有 15 年驻场经历）
- [dj.studio](https://dj.studio/blog/make-a-dj-set)（工具方，但内容是实操向）
- [Mixed In Key](https://mixedinkey.com/workflows/build-a-harmonic-dj-set/)（和声混音方法的源头厂商）
- [Esquire India](https://www.esquireindia.co.in/culture/books-and-music/how-to-build-a-playlist-that-doesnt-suck)（媒体视角，但明确引用了 High Fidelity 的经典规则）

**这是我这次没能补上的缺口，明确记在这里。** 如果你想要真实的论坛争论，可行的办法是：你本人在浏览器里打开 Reddit/知乎（我这边的网络路径被封），或者把链接贴给我、我试试能否通过别的路径抓。

---

## 8. 落到我们自己的工具上：一个硬约束（实测）

这是本次调研对我们最有价值的发现，因为**它决定了哪些方法论根本无法自动化**。

**实测：Apple Music 的 catalog API 不提供任何速度/调性/能量/情绪字段。** 拉一首歌的全部属性，只有这些：

```
albumName  artistName  artwork  composerName  discNumber  durationInMillis
genreNames  hasLyrics  isAppleDigitalMaster  isrc  name  playParams
previews  releaseDate  trackNumber  url
```

按 `tempo / bpm / key / energy / mood / beat / valence / dance / loud` 检索字段名 —— **一个都没有**。

这意味着：

- **❌ §4.1 的能量曲线、§4.3 的 Camelot 和声混音、§4.4 的 BPM/调性自动重排，在 Apple Music 上都无法仅凭 API 元数据实现。** SpotifyMixer 那类工具在 Apple Music 上**没有对应的数据源**。
- （旁证：Spotify 自身也在收紧 API。据 Digital Music News 报道 [Spotify Tightens API Access, Removes Several Data Points](https://www.digitalmusicnews.com/2024/12/01/spotify-tightens-api-access-removes-several-data-points/)（2024-12-01，**该站 Cloudflare 拦截，我未能读到正文，仅凭标题与搜索摘要，请自行核实**）以及开发者社区的 "Deprecated endpoints for new apps" 讨论，`audio-features` 一类端点对新应用已关闭。）

**可行的替代路径**（按可靠性排序）：

1. **人工判断**（最可靠，无法自动化）：顺序靠耳朵定。
2. **分析试听片段**（技术可行，实测通了）：每首歌的 `previews[0].url` 实测可下载 —— HTTP 200、`audio/x-m4p`、约 1 MB、容器是 **m4a/AAC**（magic `ftypM4A`）。所以"下载 30 秒试听 → 估计 BPM/调性"这条路是通的，代价是需要解码器 + BPM/调性估计（`librosa`/`aubio` 之类，本机**未安装**，我没做这一步验证）。**注意 30 秒片段估 BPM 会有误差**，且片段常从中段截取。
3. **第三方元数据**：MusicBrainz / Deezer 等（未验证 Apple Music 曲目覆盖率）。
4. **用能拿到的信号做"弱排序"**：`genreNames`、`durationInMillis`、`releaseDate`、`trackNumber`、`composerName`、`albumName`。这只能做很粗的结构（比如按年代、按专辑内序、按长短交替），**做不到真正的能量曲线**。

**一个能用的小发现**：`artwork` 里带 `bgColor` / `textColor1..4` 六位色值。这意味着**可以根据锚曲封面的主色调做视觉统一**（封面配色），这是唯一一个"设计层"能自动化的信号。

---

## 9. 实例诊断：一张叙事型歌单踩了哪些线

拿 §1–§5 的原则逐条对照一个真实实例（39 首，按「作曲者血脉」分七个乐章），诚实版：

| 原则 | 来源 | 那张实例（39 首） | 判定 |
|---|---|---|---|
| 单一主题 | Apple 官方 | 「作曲者血脉」一条线到底 | ✅ 通过 |
| 15–50 首 | Apple 官方 | 39 首 | ✅ 通过 |
| 20–30 首更佳；>50 退化成垃圾场 | OneStopWatch | 39 首，偏长 | ⚠️ 偏长 |
| **开头放爆款抓注意力** | **Apple 官方** | **第 1 首是冷门的ボカロ曲 `ウミユリ海底譚`** | ❌ **明确违规** |
| 前 3 首立住主题（三分钟规则） | OneStopWatch | 前 3 首全是同一张 2015 年专辑的曲子——**主题立住了**，但立的是"这是那个年代"而不是"这是这位作者" | ⚠️ 有争议 |
| 同一艺人不超过 2 首 | OneStopWatch | **按艺人名算 22 首集中在 2 位**；**按作曲者算前 27 首全部出自同一人** | ❌ 严重违规（但见下） |
| 歌单当成一次体验，顺序有意义 | Apple 官方 | 七个乐章 + 三条文字暗线 | ✅ 通过 |
| 能量曲线（Open/Build/Peak/Reset/Close） | dj.studio | **没做**——因为我们没有 BPM/能量数据（§8） | ❌ 未实现 |
| 结尾决定记忆，不要结束在静音 | Esquire | 用 2:30 的最短曲 `造花のダンス` 轻着地 | ⚠️ 与"以爆点结束"相反，是我刻意的反向选择 |
| 每 15–20 分钟做一次维护 | OneStopWatch | 没有维护节奏 | ❌ 未做 |

**关于"同一艺人不超过 2 首"这条，我要说清楚**：那条规则的语境是**发现型歌单**（给不同艺人带曝光）。那张实例是**血脉探索型**（一条作曲者线索贯穿），22 首同源恰恰是它的**立意本身**，不是失误。所以这不是"违反"，而是**选错了标准**——但如果你的目标是"被推荐、被发现"，那这张歌单必然不合格。

> 数字口径说明：本节的检查结果来自新写的 `playlist_audit.py`。**"艺人分布"按 `artistName` 统计（22 首集中在 2 位）**；而"前 27 首作曲者同一"是按 `composerName` 统计。两个口径都成立，但别混用。

**如果按上述原则改，具体动作**：

1. **换开场**：把 `ウミユリ海底譚` 从第 1 位挪走（比如挪到第 3 位），第 1 位换成一首更有抓力的——按 Apple 的口径应该是一首"大歌"。
2. **砍长度**：39 → 30 首上下（论文和教程都指向更短）。第一乐章 6 首可以砍到 3–4 首。
3. **补能量曲线**：这条**只能靠你耳朵**（§8 说数据拿不到）。但可以做一个粗版：把时长和"专辑内位置"当代理——比如把 5 分钟级的大曲放在乐章中后段，把 2–3 分钟的放在过渡处。
4. **定维护节奏**：每周固定 15 分钟，替换 2–3 首。
5. **命名**：叙事型标题（如「某某の系譜 —— 从甲到乙」）偏"品牌化"；OneStopWatch 建议用听众真会搜的词（把艺人名放进去通常更有效）。

---

## 10. 可执行清单

做新歌单时按顺序过一遍：

- [ ] **一句话 brief**：写不出就说明主题不够窄
- [ ] 三个形容词定 vibe
- [ ] 选 5–8 首锚曲（定义"声音温度"）
- [ ] 粗堆 40–60 首候选 → 狠心砍到 20–30 首（**此阶段不管顺序**）
- [ ] 分区：开场 / 中段 / 峰值 / 结尾
- [ ] **检查前 3 首**是否立住主题（三分钟规则）
- [ ] 逐对检查过渡：BPM 是否在 ±5–6 内 / 调性是否兼容 / 能量走向是否合理（**Apple Music 无数据，需人工或分析试听片段**）
- [ ] 平衡"耳熟"与"新发现"
- [ ] 总长控制在 20–30 首（硬上限别过 50）
- [ ] 结尾：以爆点结束，或刻意淡出——**绝不要结束在静音里**
- [ ] 标题用可被搜索的词
- [ ] 定一个维护节奏（每周 15–20 分钟，增删 2–3 首）

**如果是给艺人做（目标是"被发现"）**，再额外加：30 秒内必须有 hook、别做太长（影响完播率）、投编辑歌单要在发行前 ≥7 天。

---

## 11. 来源

**官方**
- [Apple Music Curator Best Practices](https://help.apple.com/itc/musiccuratorbestpractices/en.lproj/itc1ad916359.html)（Apple 官方，实测抓取成功）

**教程与方法论**
- [OnesToWatch — How to Curate Music Playlists: 7 Steps for Success](https://resources.onestowatch.com/how-to-curate-music-playlists/)
- [Esquire India — How To Build A Playlist That Doesn't Suck](https://www.esquireindia.co.in/culture/books-and-music/how-to-build-a-playlist-that-doesnt-suck)
- [Digital DJ Tips — The "Miniset" Method](https://www.digitaldjtips.com/miniset-method-music-free-lesson/)
- [dj.studio — How To Make A DJ Set: In-Depth Guide](https://dj.studio/blog/make-a-dj-set)
- [Mixed In Key — Build a harmonic DJ set](https://mixedinkey.com/workflows/build-a-harmonic-dj-set/)

**研究**
- [Bilibók, B. (2024). *Predicting Skipping Behavior in Music Streaming*. Erasmus University Rotterdam.](https://thesis.eur.nl/pub/72722/Thesis-final_v2_BENCE_BILIBOK_2024.07.18.pdf)（PDF 已下载并解析，引用出自摘要与 §6 结果讨论）

**行业**
- [iMusician — Spotify Playlisting Strategy in 2026](https://imusician.pro/en/resources/blog/spotify-playlisting-strategy-2026)
- [fdemusso/SpotifyMixer](https://github.com/fdemusso/SpotifyMixer)（BPM+Camelot 自动重排工具）

**中文（缺口）**
- [豆瓣播客：如何打造 1.5 亿播放量的歌单（嘉宾：陈北及）](https://www.douban.com/podcast_episode/317787) —— 对题但**抓不到正文，未引用**
- [豆瓣小组：自己做🍉歌单的一些小 tips](https://www.douban.com/group/topic/300730531/) —— **实测是刷榜技巧，不适用**

**未能核实**
- Spotify `audio-features` 端点关闭的具体范围（DMR 原文被 Cloudflare 挡，仅凭标题与摘要）
- 网易云音乐人那期节目的内容（TCP 连不上）
- 知乎相关内容（403）

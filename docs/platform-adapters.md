# 平台适配器：把核心和某个音乐平台隔开

这份文档记录**边界在哪、为什么在那、以及接下一个平台时会撞上什么**。
它不是为了将来某天再读，而是为了让下一个平台的实现有唯一的接口可依。

## 现状：边界已经划出来了

```
playlist_core.py         ← 平台无关。导入本项目任何模块？没有。导入第三方？没有。
                            Camelot、BPM 折叠、四条相邻规则、六种叙事弧
playlist_optimize.py     ← 平台无关的算法层，只依赖 playlist_core
                            模拟退火、cost 函数、清单解析
am_paths.py              ← 平台无关。目录、版本号
─────────────────────────── 以上这一层，接新平台时**一行都不该改** ───────────
playlist_flow.py         ← 混合：特征获取（reccobeats，平台无关） + Apple 取曲目
am_playlist.py           ← Apple：令牌、搜索、歌单增删改查
am_meta.py               ← Apple：catalog 元数据
am_library.py            ← Apple：音乐库导出
playlist_audit.py        ← Apple：元数据体检
listening_stats.py       ← Apple：播放历史
profile_library.py       ← Apple：口味画像
build_pool.py            ← Apple：候选池
```

`tests/test_rules.py::TestSingleSourceOfTruth` 和
`tests/test_guards.py::TestPlatformNeutralCore` 会**强制**这条分界：
`playlist_core` 不许引入任何项目或第三方依赖，`playlist_optimize` 不许 import
`playlist_flow` / `am_playlist` / `am_meta`。所以边界不会因为一次顺手 import 而烂掉。

## 适配器该提供什么

下面这组操作是从 Apple 实现里**实际用到的**东西反推出来的，不是想象的：

| 操作 | 谁需要 | 备注 |
|---|---|---|
| `track_ref(id) -> TrackRef` | 核心 | 见下方"可移植身份" |
| `search(query) -> [TrackRef]` | 建歌单 | 需要版本后缀打分（`best_song_match`） |
| `catalog_meta(ids)` | 体检、画像、候选池 | 至少要能给出 ISRC / 年 / 流派 |
| `library_songs()` | 候选池 | 分页；"材料够杂"的原料 |
| `playlist_list()` / `playlist_show(id)` | 体检 | |
| `playlist_create(name, ids)` | 建歌单 | **必须一次性带上曲目**（见 Apple 的 iCloud 传播延迟） |
| `playlist_add(id, ids)` / `playlist_delete(id)` | 维护 | |
| `recently_played()` / `top_played(period, kind)` | 画像、候选池 | 播放次数是最强的"你实际在听什么"信号 |
| `auth_status()` / `login()` | 全部 | 各平台形态完全不同，不强行统一 |

## 最硬的一个约束：可移植身份

**音频特征链只认 ISRC。** 这是整个项目最不可替代的一环：

```
Apple 曲目 ──► ISRC ──► reccobeats ──► tempo/key/energy/valence/...
```

Apple 会给 ISRC，但**只有 88%**（实测 1581 首里 1395 首）。剩下的 12% 现在是被
**静默丢掉**的——它们进不了候选池、进不了体检表。

这不是小问题：它就是接下一个平台时最先崩的地方。

- **Spotify** 会给 ISRC，这一环可以直接复用。
- **网易云 / QQ 音乐**的接口**不返回 ISRC**。所以要么按"歌名 + 艺人"去第三方库
  反查（错配率会很难看，尤其中文同名的现场版/翻唱），要么自己下音频做本地分析。
- **本地文件**根本没有 ISRC，除非文件标签里写了。

**结论：适配器必须把"特征覆盖率"变成一等公民**——一个可报告的数字，而不是
一次静默的 `continue`。

**这一条已经落地了。** 覆盖率现在按**原因**分解
（`playlist_core.COVERAGE_STAGES` / `classify_coverage()` / `coverage_report()`），
体检、优化器、候选池三条路都会打印它，低于 90% 时明确警告"cost 只描述了能测量的那部分
曲目"。实测某账号的音乐库：1581 首里 **186 首没有 ISRC（11.8%）**——这部分是硬损失。

接新平台时要做的，是**照着 `COVERAGE_STAGES` 把新平台的失败原因填进去**，
而不是另起一套词汇。这样"覆盖率掉了"在任何平台上都是同一句话、同一张表。

## 网易云 / QQ 音乐：先看清楚风险

两边都**没有**面向第三方的公开歌单 API。现有做法全部基于逆向出来的私有接口：

| | 网易云 | QQ 音乐 |
|---|---|---|
| 写入接口 | `weapi`，请求体要 AES + RSA 加密 | 私有接口，参数签名 |
| 登录 | 扫码 / cookie（`MUSIC_U`） | cookie（含 `uin` + `qqmusic_key`） |
| 曲目 id | `songId`（数字） | `songmid`（字符串） |
| ISRC | 不提供 | 不提供 |
| 区域 | 部分曲目仅内地可播 | VIP / 版权限制更严 |

**风险要说清楚：**

1. **两家的用户协议都禁止自动化访问。** 现实风险不是被起诉，而是**账号被限制**。
   所以登录态应当由使用者自己提供，工具**不应该**替人保管密码。
2. **私有接口会变。** 加密方式或签名规则一改，整个适配器失效。这类代码需要
   "坏了就坏了"的心理预期，不能承诺长期可用。
3. **没有 ISRC → 特征链断掉。** 这会让排序能力实质退化：只剩时长、年代、流派
   这类元数据可用，BPM/调性全部拿不到。**这是接这两个平台真正的代价**，
   比"接口会不会变"更值得先想清楚。

## 建议的第一个适配器

如果要验证这套接口是否成立，**本地文件导出（`.m3u8`）是成本最低的一个**：

- 不需要账号，不碰任何平台的 ToS；
- 会立刻暴露接口里所有"其实是为 Apple 定制"的假设；
- 它本身就有用——把现有排序结果交给 foobar2000 / MusicBee 直接播。

网易云 / QQ 可以做，但建议排在这个之后——先确认接口站得住，再往一个会变、
有 ToS 风险、而且拿不到音频特征的平台上投。

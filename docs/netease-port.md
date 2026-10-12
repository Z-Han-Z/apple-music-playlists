# 网易云 MCP 公开预览 — 1.6.1

本项目为非官方、实验性的网易云适配，使用独立的 `nc-mcp` / `nc-login`，不改变默认 Apple 服务。
网易云用户说明仅维护简体中文版。接口可能受风控、地区、版权或服务端变更影响；
不提供音频播放、下载、解灰、会员或 DRM 绕过。

这是 MCP 服务，不是独立应用。宿主 LLM 直接理解你的描述、策划候选和顺序；
工具提供资料库事实、录音版本校验和确认后的写入，不另接 LLM，不要求额外模型 API key。
方向标签仅补充原始需求，不把审美判断压成数值权重。

## 1. 安装与对话式引导

普通 Windows x64 用户优先下载[完整 ZIP](https://github.com/Z-Han-Z/apple-music-playlists/releases/download/v1.6.1/NetEase-Curator-1.6.1-Windows-Preview.zip)。
需要已有正常 Python 3.10+ 和能启动本地 MCP stdio 子进程的客户端；不捆绑 Python。
完整包自带私有 Node 24.19.0 与锁定的 API Enhanced 4.41.1 扫码依赖，
不需要自行安装 Node、部署网关或复制 Cookie。

1. 解压，把包内 `README.txt` 交给有本地工具的 Agent，请它安装并协助合并客户端配置。
2. Agent 可运行 `install.cmd`；没有本地执行工具时，自己双击运行。离线安装至私有环境，
   不修改全局 PATH 或包，不覆盖已有 MCP 服务。
3. 合并生成的配置并重新连接。保留 `NETEASE_LOGIN_BUNDLE` 指向解压目录，它不是凭证。
4. 在对话中说“帮我开始使用网易云 MCP”。Agent 先调用 `nc_setup` 获取离线配置事实，
   再调用 `nc_status` 验证登录及权限，解释缺口并征得授权。
5. 同意后调用 `nc_login(action=start, confirm=true)`。二维码只在本机浏览器打开，
   用官方网易云 App 扫码确认；Agent 轮询同一任务，再通过 `nc_status` 验证。

初始化不启动登录或访问账号。显示二维码、已保存会话均不等于验证登录成功。
可在对话中取消登录；完成或取消后临时网关关闭，宿主断开也会触发清理。
`getting_started` Prompt 是可选入口，普通聊天即可；没有独立向导、菜单、问卷或策划网页。
服务必须先接入宿主，不能假称未连接的 MCP 可以自行配置客户端。
不要把 Cookie、MUSIC_U、密码、二维码图片、扫码密钥或授权链接发到聊天。

### PyPI 与源码：进阶安装

公开版本同步到 PyPI 后可运行：

```bash
python -m pip install apple-music-playlists==1.6.1
uvx --from apple-music-playlists==1.6.1 nc-mcp
```

源码安装：

```bash
python -m pip install .
nc-login --help
```

**wheel 包含工具和中文指南，但不捆绑扫码运行时。** 独立 CLI 扫码需要下面的外部本地网关；
若希望通过对话管理随包扫码组件，请使用完整 Windows ZIP。
PATH 不可用时使用解释器或命令的绝对路径。

维护者使用 `python scripts/build_beta_bundle.py` 构建：官方 Node 下载做 SHA256 校验，
npm 依赖按完整性锁文件安装并禁用生命周期脚本，许可证和来源记录随包提供。
`--light` 是不含扫码组件的进阶导入包，不是普通用户推荐包。
更新比较 wheel SHA256，即使版本号相同也检测不同构建；失败保留旧环境，成功后需重新连接。

## 2. 本地授权与凭证保存

完整 ZIP 首选上述对话扫码流程。以下是独立 wheel / 源码 CLI 的备用入口。

```bash
nc-login import --save
nc-login status --verify
```

只在交互终端的隐藏提示中粘贴自己从官方站点取得的 MUSIC_U 或 Cookie header，
不要放在命令参数、截图、Git 或聊天里。只提取认证字段，不导入分析或设备 Cookie。
登录与 CSRF 校验成功后才保存；不加 `--save` 则只验证，不持久化。

Windows 使用当前用户 DPAPI 加密，保存在用户配置目录 `am-playlist/netease/session.bin`；
同一用户的 MCP 客户端可读取，不适用于跨用户、跨机器或 Linux 容器。
macOS/Linux 尚未接入系统密钥库：保存须明确增加 `--allow-plaintext`，文件为当前用户所有、
权限 0600，**仍是明文，不是加密**。不愿明文保存时使用环境变量，不写入仓库配置。

`NETEASE_COOKIE` 优先于保存会话；`NETEASE_CSRF` 可覆盖 CSRF，
否则使用服务端实际签发的 Set-Cookie，不伪造值。`login-expired` 需要重新本地授权，
网络失败不等于登录过期，不自动反复重试。

```bash
nc-login forget --confirm
```

这只删除本地会话，不撤销网易云服务器令牌；已泄露的会话应在官方账号中退出或撤销。

### 独立 CLI 扫码网关

```bash
nc-login qr --save
```

独立 CLI 需安装并信任 [API Enhanced 本地网关](https://github.com/NeteaseCloudMusicApiEnhanced/api-enhanced)，
设置 `NETEASE_API_URL=http://127.0.0.1:3000`。隐藏导入和直连读取不需要网关。
完整 Windows ZIP 的 `nc_login` 自行管理随包临时网关，无需填写地址。
`login-qr.cmd` 只是本机备用入口。扫码最多轮询两分钟，不输出 Cookie，并清理临时页面。

仅允许 loopback HTTP(S) 地址，拒绝远程代理、URL 凭据和跨源重定向。
网关是能够接触令牌的受信任进程，不要公开部署或启用解灰。
Windows 授权、加密保存及关闭网关后的直连登录已做内部实测；其他环境不视为已认证。

## 3. MCP 客户端、Harness 与容器

仅支持本地 stdio，不提供远程 HTTP/SSE。能启动 MCP 子进程的客户端与 Harness 可使用。
配置示例中服务名保留兼容旧内测配置，实际命令为 `nc-mcp`：

```json
{
  "mcpServers": {
    "netease-curator-beta": { "command": "nc-mcp" }
  }
}
```

源码方式使用绝对路径：

```json
{
  "mcpServers": {
    "netease-curator-beta": {
      "command": "<PYTHON_ABSOLUTE_PATH>",
      "args": ["<PROJECT_ROOT>/netease_mcp_server.py"]
    }
  }
}
```

先验证 `nc_status`，再直接描述需求，例如：

> 做一张从午夜便利店出发、逐渐走到清晨海边的 12 首歌单，以城市流行的空间感为起点，
> 逐渐转到更有机的乐器；包含几首我最近爱听的歌，但不要把热榜当成主题答案。先给预览。

Agent 获取必要的有界证据页，提出候选池、校验版本、提供定性方向调整，再回到原需求比较候选。
输出包含简洁文本和有界 `structuredContent`，不重复倾倒整份个人音乐库。

### 容器

从源码构建，默认入口仍为 Apple；没有发布预构建镜像。
切换网易云入口时使用环境变量，不把会话放入命令参数：

```bash
docker build -t am-curator-preview:1.6.1 .
docker run --rm -i --entrypoint python --env NETEASE_COOKIE am-curator-preview:1.6.1 /app/netease_mcp_server.py
```

Windows 扫码包不是 Linux 容器登录运行时，DPAPI 文件不能在 Linux 解密。
使用独立用户配置/缓存卷和正确的非 root 所有权。
容器 localhost 不是宿主机；网关只支持同一网络命名空间的 loopback，不通过远程代理绕过限制。
MCP stdio 不加 `-t`。跨系统会话及真实容器登录尚未完成外部验证。

## 4. 20 个工具与读取边界

| 工具 | 功能与边界 |
|---|---|
| `nc_setup` | 离线配置事实；保存了会话不代表登录有效，由宿主解释下一步 |
| `nc_login` | 经同意后启动本机扫码、查询进度或取消；不在聊天中传递凭证及二维码 |
| `nc_status` | 验证登录、会话来源、能力和后续步骤；网络失败不等于登录过期 |
| `nc_search_songs`, `nc_resolve_candidates` | Unicode 身份及录音版本校验；元数据不证明可播放性 |
| `nc_list_playlists`, `nc_show_playlist` | 有界歌单汇总和曲目页，默认 20、最大 100 |
| `nc_liked_songs` | 红心成员及数字 ID 顺序，不代表收藏或收听日期 |
| `nc_collected_albums`, `nc_followed_artists` | 分页收藏成员，不代表歌曲播放次数 |
| `nc_get_songs` | 最多 100 个明确 ID，保留输入顺序、重复项和缺失位置 |
| `nc_recently_played` | 最多 100 条近期事件，Unix 毫秒时间，不是完整历史 |
| `nc_top_played` | 周榜与历史榜；播放次数、排序得分分开，缺失次数为 null |
| `nc_tag_directions` | 定性方向及网易云专属声明来源链，不核实自由文本标签的含义 |
| `nc_create_playlist`, `nc_add_tracks`, `nc_delete_playlist` | 默认预览，写入需开启权限、确认并核验所有者及结果 |
| `nc_audit_playlist`, `nc_analyze_flow`, `nc_optimize_order` | 事实检查与共享物理规则；缺少测量时保持未知 |

按 `has_more/next_offset` 翻页，不能把一页当全部。歌单汇总、曲目和红心的后续页须传回
`snapshot`；成员或顺序变化返回 `snapshot-changed`，应从零重读。
专辑、艺人、榜单和近期窗口没有可靠的服务端快照，不能把跨页读取视为某一时刻的完整历史。
元数据缺失时保留 ID、位置和缺失列表。红心、关注或收藏本身不能证明听歌日期或播放次数。
历史榜不等于年度 Replay，也不是带日期的终生历史；内部完整读取只用于审计和写入核验。

## 5. 写入安全与特征边界

1. 校验候选与不明确的录音版本，先用 `dry_run=true` 预览。
2. 征得用户确认，在本机启用 `NETEASE_ENABLE_WRITES=1` 并重新连接。
3. 实际写入还需 `dry_run=false, confirm=true`；新建歌单默认私密。
4. 检查 `verified`、`status` 与 MCP `isError`，请求被接受不等于已核验成功。

创建是多步操作，可能部分成功；保留已知歌单 ID，**不自动重试、删除或回滚**。
`partial-or-unknown` 必须先在官方客户端检查。追加核对原曲、曲序、所有者及并发变化，
异常返回 `needs-review`，不擅自重排。重复已有歌曲阻止写入，创建核对隐私和所请求的描述。
删除仅限本工具记录创建且当前用户拥有的歌单；服务端接受删除不等于独立核验已消失。

创建日志仅在用户缓存记录歌单 ID → 所有者 ID，不存歌名、历史或令牌；清空会撤销工具的删除资格。
没有可靠网易云原生 ISRC → 音频特征链，不虚构 BPM/key，也不做同名跨平台猜测。
`features` 必须由调用方显式提供测量值并声明来源，服务端不独立核实该来源。
缺特征时报告覆盖率及未评估相邻对；覆盖不完整则保持原序，不输出误导的 cost。
未知衔接不等于零成本或“完美排序”。

## 验证状态与隐私

经用户授权的内部测试已验证登录、CSRF、账号歌单、红心、收藏专辑、关注艺人、周榜及历史榜，
以及近期事件的有界读取和翻页。此前真实创建私密测试歌单并读回核对。
不把个人数量、账号 ID、Cookie、选曲或听歌记录写入发布文档和测试，也不将单账号测试视为通用认证。
追加、删除、更多并发写入、其他网关/系统及真实容器登录仍需明确授权下的外部验证。

所有离线测试模拟网络和资料库写入；DPAPI 测试使用合成令牌。
宿主或模型可能接收工具返回的音乐信息，请检查其隐私设置。
校验文件检测损坏，不替代发布者身份认证；仅使用可信下载渠道。

```bash
python -m unittest discover -s tests -v
git diff --check
```

`mcp_common.py`、`catalog_matching.py` 保持标准库及平台中立，已有 Apple 导出保持兼容。
`playlist_core.check_pair` 仍是统一的物理规则定义，不引入平台依赖。

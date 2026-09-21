# 凭证配置

这个工具需要**两个**令牌，都只保存在你本机的用户配置目录里，**不会**被打包、提交或上传。

> 🔒 **本仓库不含任何令牌。** 如果你 fork 或修改，请确保 `config.json`、`.p8` 私钥、
> 以及任何 `.env` 都被 `.gitignore` 挡住。仓库里的 `.gitignore` 已经配好了。

---

## 概览

| 令牌 | 它证明什么 | 从哪来 | 有效期 | 能否自动拿 |
|---|---|---|---|---|
| **developer token**（ES256 JWT） | "我是可信客户端"——**每个请求**都要 | ① 网页播放器内嵌的公开 token ② 自己的 MusicKit `.p8` 私钥 | 网页版约 70 天；自己签 ≤6 个月 | ✅ 完全自动（首次运行任意命令时自动抓取） |
| **music-user-token** | "我是这个用户"——**读写音乐库必需** | 登录 `music.apple.com` 后的 `media-user-token` cookie | 约 **6 个月** | ⚠️ 需要一次性登录 |

**配置文件位置**（脚本自动创建，权限设为仅本人可读）：

```
Windows : %APPDATA%\am-playlist\config.json
macOS   : ~/.config/am-playlist/config.json
Linux   : $XDG_CONFIG_HOME/am-playlist/config.json   （默认 ~/.config/...）
```

内容形如（下面全是**占位符**，不是真实令牌）：

```json
{
  "developer_token": "<ES256 JWT: header.payload.signature>",
  "developer_token_fetched_at": 1700000000,
  "music_user_token": "<opaque music-user-token string>",
  "music_user_token_saved_at": 1700000000
}
```

---

## 第 1 步：developer token（通常不用管）

首次运行任何命令（例如 `python am_playlist.py status`）时，脚本会自动：

1. 拉取 `https://music.apple.com/us/browse`
2. 找到它引用的 `/assets/index~*.js`
3. 正则扫出其中的 JWT，挑出 `iss == "AMPWebPlay"` 的那个
4. 缓存进 `config.json`，过期前自动重抓

**所以这一步你什么都不用做。** 想手动确认：

```bash
python am_playlist.py status
# developer token: 有效 (iss=AMPWebPlay, 剩余 60.4 天)
```

> 这个 token 是 Apple 内嵌在**公开前端**里的，任何人都能读到。它只能访问公共 catalog，
> 拿不到任何用户数据——真正的门锁是第 2 步的 user token。

---

## 第 2 步：music-user-token（唯一需要动手的一步）

Apple 没有提供"零登录"的口子：写音乐库必须由 Apple ID 登录 + 双重认证换来。
**但登录一次之后，约 6 个月内全自动。**

三条路，脚本按顺序自动尝试前两条，都失败会打印第三条的手动步骤：

### 方式 A（最省事，之后全自动）：从 Apple Music Windows 客户端读

商店版 Apple Music 应用用的是 **WebView2**，其 cookie 库只用了 **DPAPI** 加密
（不是 Edge/Chrome 那套 App-Bound 加密），所以同用户下的脚本能解密读取。

```powershell
# 先在商店版 Apple Music 应用里登录一次，然后：
pip install cryptography
python am_playlist.py login
```

### 方式 B（半自动）：用 Playwright 开浏览器登录

```powershell
pip install playwright
python am_playlist.py login
```

脚本会用系统自带的 Edge（`channel="msedge"`，**不需要额外下载 Chromium**）打开
`music.apple.com/login`，你在窗口里登录（含 2FA），脚本自动读 cookie 并保存。
profile 会持久化，下次不用重登。

### 方式 C（零依赖，最稳）：手动复制 cookie

30 秒，不需要装任何东西：

1. 浏览器打开 <https://music.apple.com> 并**登录**
2. `F12` → **Application**（应用）→ 左侧 **Cookies** → `https://music.apple.com`
3. 找到 **`media-user-token`**，双击 Value 全选复制
4. 回来运行：

```powershell
python am_playlist.py login --from-clipboard
# 或： python am_playlist.py login --token <粘贴的值>
```

`--from-clipboard` 会自动容错：多带了 `media-user-token=` 前缀、引号、或整行 cookie 都能处理。

> ⚠️ **`media-user-token` 只有在你已登录 music.apple.com 时才存在。**
> Cookies 列表里找不到它，就说明当前浏览器没登录 Apple Music。
> 另外注意：网页里那个 `devToken=` 参数**不是**它——那是 developer token。

### 保存成功的样子

```
$ python am_playlist.py login --from-clipboard
· 从剪贴板读到 246 个字符，按 media-user-token 处理
✓ token 校验通过，storefront = cn
✓ 已保存到 C:\Users\<你>\AppData\Roaming\am-playlist\config.json（此后创建歌单全自动）
```

---

## 可选：用自己的 MusicKit 密钥（批量导入才需要）

网页 token 的配额是**共享**的：几百首的批量导入会撞上 **429**，而 Apple 不返回
`Retry-After`，窗口约 60 分钟且滚动。**交互式使用完全够用；批量场景才需要自己的密钥。**

需要 [Apple Developer Program](https://developer.apple.com/programs/)（$99/年）：

1. [Apple Developer Portal → Keys](https://developer.apple.com/account/resources/authkeys/list)
   → **+** → 勾选 **MusicKit** → Register → 下载 `.p8`（**只能下载一次**）
2. 记下 **Key ID** 和 **Team ID**（Membership 页面）
3. 生成并保存：

```bash
pip install cryptography
python am_playlist.py devtoken --key-path ~/AuthKey_XXXX.p8 --key-id ABC123DEFG --team-id DEF123GHIJ
```

> 🔒 `.p8` 是私钥，**永远不要提交**。`.gitignore` 已挡住 `*.p8`。

---

## 安全须知

1. **`config.json` 里的 `music-user-token` 等同于你音乐库的读写凭证**（约 6 个月有效）。
   别外传、别放进共享目录、别提交到 Git。
2. 令牌是**明文存在本地**的（脚本只做了文件权限收紧）。这是这类工具的常规做法——
   任何能读你用户目录的程序都能读它。介意的话，用完可以 `python am_playlist.py logout`
   把令牌清掉，下次再 `login`。
3. 如果你**不小心把令牌提交了**：
   - 立刻在 Apple ID 里改密码 / 撤销授权——撤销后该 token 立即失效
   - 从 Git 历史里清除（`git filter-repo` 或 BFG），**只删最新提交是不够的**
   - 用 `python am_playlist.py login` 重新获取一个新 token

---

## 排错

| 现象 | 原因与处理 |
|---|---|
| `403 Authentication required for request` | 没有 user token，或它已失效（约 6 个月）→ 重新 `login` |
| `401` | developer token 无效 → 删掉 `config.json` 里的 `developer_token` 让它重抓；或你在对 `api.music.apple.com` 做 DELETE（要改用 `amp-api`） |
| `429` | 限流。网页 token 配额共享、窗口约 60 分钟滚动。**别急着重试**，重试会延长限流 |
| `429` 后想批量导入 | 换自己的 `.p8`（见上面「可选」一节） |
| 写入歌单 `403` | 该歌单不是本工具创建的。Apple 限制：**只有创建者能写**。手机上手动建的歌单，API 改不了 |
| 抓 developer token 失败 | Apple 改了前端结构。检查 `music.apple.com` 首页引用的 `/assets/index~*.js` 是否还在 |

---

## 不想用命令行？

登录之后，所有能读 `%APPDATA%\am-playlist\config.json` 的工具都能直接用，包括
MCP 服务（`am_mcp_server.py`）——它会自动读同一份配置。

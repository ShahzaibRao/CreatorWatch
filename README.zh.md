# 📥 CreatorWatch — v0.1.0

🌐 语言: [English](README.md) · [Roman Urdu](README.ur.md) · [Español](README.es.md) · **中文**

自动跟踪 YouTube、TikTok、Instagram 和 X (Twitter) 的频道/主页。
添加链接 → 创建 prospect 文件夹 → **仅下载最新视频** → 之后按间隔**只下载新上传**。

---

## 安装方式(2 种)
1. **源码:** clone 仓库 → 按下面 Setup → 网页模式 http://127.0.0.1:5000。
2. **EXE(简单):** 从 [Releases](https://github.com/ShahzaibRao/CreatorWatch/releases) 下载 `CreatorWatch.exe` → 双击 → 同样界面自动打开。无需 Python。应用内更新(⬆ Updates)。

## 1. 安装(首次)

```bash
cd downloader
python -m venv venv

# Windows:
venv\Scripts\activate
# Git-Bash / Linux / Mac:
source venv/bin/activate

pip install -r requirements.txt
python app.py
```

然后打开: **http://127.0.0.1:5000**

> 无需单独安装 `ffmpeg` — 已通过 `imageio-ffmpeg` 内置。

---

## 2. 添加 prospect(频道)

面板上的 **Add prospect** 表单:

| 字段 | 含义 |
|---|---|
| Name | 名称,例如 `ali_tiktok` → 创建 `downloads/youtube_ali_tiktok/` |
| Channel / Profile link | YouTube 频道、TikTok `@user`、Instagram 或 X 主页链接 |
| Every (min) | 每隔多少分钟检查新视频(5–1440,默认 15) |
| Quality | `720p`(默认) / `1080p` / `480p` / `360p` / `Best` — 仅 YouTube |

**添加后:**
1. 在 `downloads/` 下创建文件夹
2. 后台**仅下载最新 1 个视频**
3. 旧视频标记为 `skipped` — **永不下载**

---

## 3. 日常使用

| 按钮 | 作用 |
|---|---|
| **Check** | 立即检查 + 后台下载新内容(看实时进度条) |
| **Check all now** | 一次检查所有 prospect |
| **⏸ Stop / ▶ Resume** | 暂停 / 恢复自动检查 |
| **Edit** | 改名、链接、间隔、清晰度(文件夹不变) |
| **Del** | 删除 prospect 及其记录 |

**状态:** `OK` · `Error`(悬停看原因) · `Working` · `Paused`。

**注意:**
- 每个 profile 按自己的间隔自动检查。
- 下载记录在**数据库**中 — 即使删除文件也**不会重新下载**。
- `0 new` = 博主没有新上传。

**其他:** 🔔 新下载铃铛 + NEW 标记、实时进度条、⚙ workers 指示、🌐 语言切换(EN/UR/ES/中文)、◐ 深浅主题。

---

## 4. 🍪 Cookies 管理(`/cookies` 页面,顶部按钮)

Instagram 和 X (Twitter) **未登录不提供数据**。
YouTube + TikTok 一般无需 cookies。

**导入方法:**
1. 安装浏览器扩展 **"Get cookies.txt LOCALLY"**
2. 登录该站点(如 instagram.com)
3. 用扩展 Export → 复制文本
4. 粘贴到 `/cookies` 并 **Save**(自动校验格式)

**页面显示:** 文件状态、分站点卡片(✅ Ready · ❌ Login missing · ⚠️ Expired · ○ Optional)、**实时检测**(Test Now,10–30 秒)、一键删除。无需重启。

---

## 5. 常见问题

| 错误 / 现象 | 原因 + 解决 |
|---|---|
| `members-only / Join this channel` | 付费会员视频 — 换公开频道测试 |
| `Unable to extract data` (Instagram) | 需要登录 → 导入 cookies |
| `login required` / `AuthRequired` / 0 条 | Cookies 缺失/过期 → 重新导入 + 检测(X 需要登录态 `auth_token`) |
| Check 一直转 | 正常 — 正在下载,看进度条 |
| `0 new` | 没有新上传,或数据库中已有 |

---

## 6. 项目结构

```
downloader/
├── app.py               # Flask 面板 + 调度 + 线程池
├── downloader.py        # yt-dlp/gallery-dl 引擎
├── database.py          # SQLite: profiles、videos、settings
├── translations.py      # 界面文本: en / ur / es / zh
├── data.db              # 数据库(自动创建)
├── downloads/           # 每个 prospect 一个文件夹
├── cookies.txt          # 你的登录 cookies(面板管理,切勿提交)
├── templates/           # dashboard、edit、cookies、settings
├── requirements.txt
└── server.log
```

**⚙ 性能(`/settings`):** 并行 workers 1–10 + 自动计算器(CPU/内存/网速)。

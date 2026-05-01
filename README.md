<div align="center">

<img src="./banner.png" alt="Banner">

**API调用限频器** —— 让你的 AstrBot 机器人不再"疯狂烧钱"

[中文](./README.md) | [English](./README-en.md) | [日本語](./README-ja.md) | [한국어](./README-ko.md)

<a href="https://github.com/xiaohondan/astrbot_plugin_api_limiter/releases">
  <img src="https://img.shields.io/github/v/release/xiaohondan/astrbot_plugin_api_limiter?style=flat-square" alt="Release">
</a>
<a href="https://github.com/xiaohondan/astrbot_plugin_api_limiter">
  <img src="https://img.shields.io/badge/AstrBot-Plugin-blue?style=flat-square" alt="AstrBot">
</a>
<a href="https://github.com/xiaohondan/astrbot_plugin_api_limiter/blob/main/main.py">
  <img src="https://img.shields.io/badge/License-MIT-green?style=flat-square" alt="License">
</a>

![:name](https://count.getloli.com/@小红蛋?name=%E5%B0%8F%E7%BA%A2%E8%9B%8B&theme=booru-lewd&padding=7&offset=0&align=top&scale=1&pixelated=1&darkmode=auto)

</div>

---

<details>
<summary><h2>✨ 功能一览</h2></summary>

### 1. 调用间隔限制
每次 LLM API 调用前强制等待一段冷却时间，防止短时间内大量请求消耗 API 余额。

> 例：设置 3 秒间隔，机器人每回复一条消息后至少等待 3 秒才能调用下一次 API。

### 2. 次数限制 + 冷却重开
机器人连续发送指定条数的消息后自动暂停 API 调用，等待一段时间后自动恢复。

> 例：设置最大调用 10 次，冷却 5 分钟。机器人发完 10 条消息后会"安静" 5 分钟，之后自动恢复工作。

### 3. 安静时段（定时切断 API）
设置一个时间段，在该时间段内完全禁止 API 调用，防止机器人半夜在群里发消息扰民。

> 例：设置安静时段 23:00 ~ 07:00，机器人在这段时间内不会调用 API，不会回复任何需要 LLM 的消息。

### 4. 每日调用配额
每天最多允许的 API 调用总次数，第二天自动重置。与次数限制不同，每日配额是按自然日计算的硬上限。

> 例：设置每日配额 100 次，当天累计调用 100 次后所有请求被拦截，次日 0 点自动恢复。

### 5. 白名单 / 黑名单
- **白名单**：指定不受限频影响的用户 ID，管理员使用不受任何限制
- **黑名单**：指定用户直接拒绝，不占用配额

> 例：设置白名单为 `123456,789012`，这两个用户的所有请求直接放行。

### 6. 自定义拒绝消息
请求被拦截时自动回复用户的消息，留空则静默拦截。

> 例：设置拒绝消息为"请求太频繁，请稍后再试~"，用户被拦截时会收到这条提示。

### 7. 调用统计面板
提供两种方式查看统计数据：

- **聊天统计**：发送 `/webui` 在聊天中查看文字版统计，底部附有开启网页面板的提示
- **WebUI 面板**：管理员发送 `开启统计面板` 开启浏览器统计页面，支持局域网访问 + Token 认证

> WebUI 面板在浏览器中显示今日调用、累计放行/拦截、放行率、当前配置状态等，支持一键刷新。

### 8. 对话切断
防止单个用户或全体用户在短时间内耗尽 API 余额。支持两种模式（二选一）：

- **单用户模式**：每个用户独立计数，达到上限只阻断该用户，不影响其他人
- **全局模式**：所有人加起来计数，达到上限后所有人被阻断

> 私聊和群聊分开计算，每个群聊/私聊独立计数。次日自动重置。
>
> 例：设置单用户模式、上限 20 次、冷却 30 分钟。用户 A 连续对话 20 次后 API 被阻断 30 分钟，期间用户 B 不受影响。

### 9. 分时段限频
按小时设置不同的限频参数（间隔、次数、冷却），白天宽松、晚上严格。

### 10. 超额提醒
每日配额用到 80% 时自动提醒管理员。

### 11. 群聊独立配额
不同群设置不同的每日配额，互不影响。

### 12. 管理员指令
- `重置限频` — 重置所有计数和冷却
- `重置冷却` — 仅重置冷却状态
- `重置配额` — 仅重置每日配额
- `重置对话` — 仅重置对话切断计数
- `清空日志` — 清空拦截日志
- `导出日志` — 导出拦截记录为文本

</details>

---

<details>
<summary><h2>📦 安装</h2></summary>

**方法一：从 GitHub 克隆（推荐）**

```bash
cd AstrBot/data/plugins/
git clone https://github.com/xiaohondan/astrbot_plugin_api_limiter.git
```

**方法二：从插件市场安装**

在 AstrBot WebUI → 插件市场 中搜索 **API调用限频器** 或 **小红蛋**，点击安装。

**方法三：手动安装**

1. 下载本仓库的 ZIP 压缩包
2. 解压到 AstrBot 的 `data/plugins/` 目录下
3. 重启 AstrBot

</details>

---

<details>
<summary><h2>⚙️ 配置说明</h2></summary>

安装后在 AstrBot WebUI → 插件管理 → **API调用限频器** → 配置 中进行设置：

| 配置项 | 类型 | 默认值 | 说明 |
|:---|:---:|:---:|:---|
| **调用冷却间隔** | 整数 | 3 | 每次 API 调用前需等待的秒数。设为 0 则不限制 |
| **最大调用次数** | 整数 | 0 | 连续发送多少条消息后暂停 API。设为 0 则不限制 |
| **冷却等待时间** | 整数 | 0 | 达到次数上限后需等待的分钟数。设为 0 则不自动恢复 |
| **每日调用配额** | 整数 | 0 | 每天最多 API 调用次数，次日自动重置。设为 0 则不限制 |
| **安静时段开始** | 字符串 | 空 | 格式 `HH:MM`（如 `23:00`），留空不启用 |
| **安静时段结束** | 字符串 | 空 | 格式 `HH:MM`（如 `07:00`），留空不启用 |
| **白名单用户ID** | 字符串 | 空 | 多个用英文逗号分隔，留空无白名单 |
| **黑名单用户ID** | 字符串 | 空 | 多个用英文逗号分隔，留空无黑名单 |
| **分时段限频** | 字符串 | 空 | JSON 格式，按小时设置不同限频参数 |
| **群聊独立配额** | 字符串 | 空 | 格式：群号:配额，分号分隔 |
| **自定义拒绝消息** | 字符串 | 空 | 拦截时回复用户的消息，留空则静默拦截 |
| **统计面板端口** | 整数 | 6285 | WebUI 统计面板的 HTTP 端口 |
| **统计面板令牌** | 字符串 | 空 | 访问面板需携带的 Token，留空则不验证 |
| **对话切断模式** | 下拉 | 空 | `单用户` 或 `全局`，留空不启用 |
| **对话切断上限** | 整数 | 0 | 对话次数达到此值后阻断 API |
| **对话切断冷却** | 整数 | 0 | 达到上限后等待多少分钟恢复 |

### 配置示例

**场景一：防止 API 余额消耗过快**
```
调用冷却间隔：3 秒
最大调用次数：20 条
冷却等待时间：10 分钟
每日调用配额：100 条
自定义拒绝消息：请求太频繁，请稍后再试~
```
> 机器人每 3 秒最多回复一条消息，连续发 20 条后休息 10 分钟，每天最多 100 次。

**场景二：防止半夜扰民**
```
安静时段开始：23:00
安静时段结束：07:00
自定义拒绝消息：现在是安静时段，请明天再来~
```
> 晚上 11 点到早上 7 点机器人完全不调用 API。

**场景三：全面保护 + 管理员白名单**
```
调用冷却间隔：3 秒
最大调用次数：15 条
冷却等待时间：5 分钟
每日调用配额：200 条
安静时段开始：00:00
安静时段结束：07:00
白名单用户ID：123456789
```
> 管理员不受任何限制，其他用户白天每 3 秒回复一条，凌晨完全屏蔽。

</details>

---

<details>
<summary><h2>📊 统计面板</h2></summary>

**聊天统计**：发送 `/webui` 即可查看 API 限频统计数据。

**WebUI 网页面板**：管理员发送以下指令控制：

```bash
开启统计面板    # 开启，返回访问地址（含 Token）
关闭统计面板    # 关闭面板
```

面板在浏览器中展示：
- 今日已调用 / 每日配额
- 累计放行 / 累计拦截 / 放行率
- 冷却状态进度条
- 当前所有配置状态
- 最近拦截记录

支持局域网访问 + Token 认证，防止未授权查看。

</details>

---

<details>
<summary><h2>🔧 兼容性</h2></summary>

- **AstrBot 版本**：>= 4.16, < 5
- **支持平台**：所有 AstrBot 支持的平台（QQ、Telegram、Discord 等）
- **额外依赖**：无（WebUI 使用 AstrBot 自带的 aiohttp）

</details>

---

<details>
<summary><h2>📁 文件结构</h2></summary>

```
astrbot_plugin_api_limiter/
├── main.py              # 插件主逻辑
├── metadata.yaml        # 插件元数据
├── _conf_schema.json    # WebUI 配置项定义
├── CHANGELOG.md         # 更新日志
├── requirements.txt     # 依赖声明（无额外依赖）
└── README.md            # 本文件
```

</details>

---

<details>
<summary><h2>📄 更新日志</h2></summary>

详见 [CHANGELOG.md](./CHANGELOG.md)

</details>

---

<details>
<summary><h2>👤 作者</h2></summary>

**小红蛋**

</details>

---

<details>
<summary><h2>📄 许可证</h2></summary>

MIT License

</details>

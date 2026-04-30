<div align="center">

<img src="./banner.png" alt="Banner">

**API Rate Limiter** — Stop your AstrBot bot from burning through API credits

[中文](./README.md) | [English](./README-en.md) | [日本語](./README-ja.md) | [한국어](./README-ko.md)

![:name](https://count.getloli.com/@小红蛋?name=%E5%B0%8F%E7%BA%A2%E8%9B%8B&theme=booru-lisu&padding=7&offset=0&align=top&scale=1&pixelated=1&darkmode=auto)

A multi-purpose API call management plugin for [AstrBot](https://github.com/AstrBotDevs/AstrBot). Take precise control of LLM API usage frequency, prevent rapid credit consumption, and stop your bot from being "annoying" late at night.

</div>

---

<details>
<summary><h2>✨ Features</h2></summary>

### 1. Call Interval Limit
Enforces a cooldown between each LLM API call, preventing rapid-fire requests from draining your API balance.

> Example: Set a 3-second interval — the bot must wait at least 3 seconds between consecutive API calls.

### 2. Call Count Limit + Cooldown Reset
Automatically pauses API calls after a specified number of consecutive messages, then resumes after a cooldown period.

> Example: Set max 10 calls with a 5-minute cooldown. After 10 messages, the bot goes silent for 5 minutes, then resumes automatically.

### 3. Quiet Hours (Scheduled API Cutoff)
Completely blocks API calls during a specified time window, preventing late-night messages from disturbing group chats.

> Example: Set quiet hours 23:00 ~ 07:00. During this window, the bot won't call any LLM APIs.

### 4. Daily Quota
A hard daily cap on total API calls, automatically reset at midnight.

> Example: Set daily quota to 100. Once 100 calls are reached, all requests are blocked until the next day.

### 5. Whitelist / Blacklist
- **Whitelist**: Specified user IDs are exempt from all rate limiting
- **Blacklist**: Specified user IDs are immediately rejected without consuming quota

> Example: Set whitelist to `123456,789012` — these two users bypass all restrictions.

### 6. Custom Rejection Message
Automatically reply to users when their request is blocked. Leave empty for silent blocking.

> Example: Set rejection message to "Too many requests, please try again later~"

### 7. Statistics Dashboard
Two ways to view statistics:

- **Chat Stats**: Send `/webui` to view text-based statistics in chat
- **WebUI Dashboard**: Admin sends `开启统计面板` to launch a browser-based dashboard with LAN access + Token authentication

> The WebUI dashboard displays today's calls, total allowed/blocked, pass rate, cooldown status, and more.

### 8. Conversation Cutoff
Prevents individual users or all users from rapidly depleting API credits. Two modes:

- **Per-user mode**: Each user counted independently — reaching the limit only blocks that user
- **Global mode**: All users counted together — reaching the limit blocks everyone

> Private and group chats are tracked separately. Automatically resets daily.
>
> Example: Per-user mode, limit 20, cooldown 30 min. User A gets blocked after 20 messages for 30 min; User B is unaffected.

### 9. Time-Based Rate Limiting
Set different rate limit parameters (interval, count, cooldown) per hour — relaxed during the day, strict at night.

### 10. Quota Warning
Automatically alerts the admin when daily quota reaches 80%.

### 11. Per-Group Quota
Set different daily quotas for different groups, independent of each other.

### 12. Admin Commands
- `重置限频` — Reset all counters and cooldowns
- `重置冷却` — Reset cooldown state only
- `重置配额` — Reset daily quota only
- `重置对话` — Reset conversation cutoff counters only
- `清空日志` — Clear block logs
- `导出日志` — Export block logs as text

</details>

---

<details>
<summary><h2>📦 Installation</h2></summary>

**Method 1: Clone from GitHub (Recommended)**

```bash
cd AstrBot/data/plugins/
git clone https://github.com/xiaohondan/astrbot_plugin_api_limiter.git
```

**Method 2: Install from Plugin Marketplace**

Search for **API Rate Limiter** or **xiaohondan** in AstrBot WebUI → Plugin Marketplace, then click Install.

**Method 3: Manual Installation**

1. Download the ZIP archive from this repository
2. Extract to AstrBot's `data/plugins/` directory
3. Restart AstrBot

</details>

---

<details>
<summary><h2>⚙️ Configuration</h2></summary>

After installation, go to AstrBot WebUI → Plugin Management → **API Rate Limiter** → Configuration:

| Setting | Type | Default | Description |
|:---|:---:|:---:|:---|
| **Cooldown Interval** | Integer | 3 | Seconds to wait between API calls. Set to 0 for no limit |
| **Max Call Count** | Integer | 0 | Messages before pausing API. Set to 0 for no limit |
| **Cooldown Duration** | Integer | 0 | Minutes to wait after reaching the limit. Set to 0 for no auto-recovery |
| **Daily Quota** | Integer | 0 | Max API calls per day, auto-resets at midnight. Set to 0 for no limit |
| **Quiet Hours Start** | String | Empty | Format `HH:MM` (e.g. `23:00`). Leave empty to disable |
| **Quiet Hours End** | String | Empty | Format `HH:MM` (e.g. `07:00`). Leave empty to disable |
| **Whitelist User IDs** | String | Empty | Comma-separated user IDs. Leave empty for no whitelist |
| **Blacklist User IDs** | String | Empty | Comma-separated user IDs. Leave empty for no blacklist |
| **Time Slots** | String | Empty | JSON format, set rate limit params per hour |
| **Group Quotas** | String | Empty | Format: groupId:quota, semicolon-separated |
| **Rejection Message** | String | Empty | Message sent when request is blocked. Leave empty for silent blocking |
| **Dashboard Port** | Integer | 6285 | HTTP port for the WebUI dashboard |
| **Dashboard Token** | String | Empty | Token required for dashboard access. Leave empty for no auth |
| **Cutoff Mode** | Dropdown | Empty | `Per-user` or `Global`. Leave empty to disable |
| **Cutoff Limit** | Integer | 0 | Conversation count before API is blocked |
| **Cutoff Cooldown** | Integer | 0 | Minutes before recovery after reaching the limit |

### Configuration Examples

**Scenario 1: Prevent rapid credit consumption**
```
Cooldown Interval: 3 seconds
Max Call Count: 20
Cooldown Duration: 10 minutes
Daily Quota: 100
Rejection Message: Too many requests, please try again later~
```
> Bot replies at most once every 3 seconds, rests 10 minutes after 20 messages, max 100 calls per day.

**Scenario 2: Prevent late-night disturbance**
```
Quiet Hours Start: 23:00
Quiet Hours End: 07:00
Rejection Message: It's quiet hours, please come back tomorrow~
```
> Bot completely stops calling APIs from 11 PM to 7 AM.

**Scenario 3: Full protection + Admin whitelist**
```
Cooldown Interval: 3 seconds
Max Call Count: 15
Cooldown Duration: 5 minutes
Daily Quota: 200
Quiet Hours Start: 00:00
Quiet Hours End: 07:00
Whitelist User IDs: 123456789
```
> Admin is unrestricted. Other users: 3-second intervals, 15-message limit with 5-min cooldown, completely blocked from midnight to 7 AM.

</details>

---

<details>
<summary><h2>📊 Statistics Dashboard</h2></summary>

**Chat Stats**: Send `/webui` to view API rate limiting statistics in chat.

**WebUI Dashboard**: Admin sends these commands to control the web panel:

```bash
开启统计面板    # Start dashboard, returns access URL (with token)
关闭统计面板    # Stop dashboard
```

The dashboard displays in your browser:
- Today's calls / Daily quota
- Total allowed / Total blocked / Pass rate
- Cooldown status progress bar
- Current configuration status
- Recent block logs

Supports LAN access with Token authentication to prevent unauthorized viewing.

</details>

---

<details>
<summary><h2>🔧 Compatibility</h2></summary>

- **AstrBot Version**: >= 4.16, < 5
- **Supported Platforms**: All AstrBot-supported platforms (QQ, Telegram, Discord, etc.)
- **Additional Dependencies**: None (WebUI uses AstrBot's built-in aiohttp)

</details>

---

<details>
<summary><h2>📁 File Structure</h2></summary>

```
astrbot_plugin_api_limiter/
├── main.py              # Plugin main logic
├── metadata.yaml        # Plugin metadata
├── _conf_schema.json    # Configuration schema definition
├── CHANGELOG.md         # Changelog
├── requirements.txt     # Dependencies (none required)
└── README.md            # This file
```

</details>

---

<details>
<summary><h2>📄 Changelog</h2></summary>

See [CHANGELOG.md](./CHANGELOG.md)

</details>

---

<details>
<summary><h2>👤 Author</h2></summary>

**xiaohondan (小红蛋)**

</details>

---

<details>
<summary><h2>📄 License</h2></summary>

MIT License

</details>

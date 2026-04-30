import asyncio
import json
import socket
import time
from datetime import datetime, date
from aiohttp import web
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger, AstrBotConfig
from astrbot.api.provider import ProviderRequest


# ==================== WebUI HTML ====================

STATS_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>API限频统计面板</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    min-height: 100vh; display: flex; justify-content: center; align-items: center;
    padding: 20px;
  }
  .card {
    background: #fff; border-radius: 16px; box-shadow: 0 20px 60px rgba(0,0,0,0.3);
    max-width: 480px; width: 100%; padding: 32px; overflow: hidden;
  }
  h1 { text-align: center; color: #333; font-size: 22px; margin-bottom: 4px; }
  .subtitle { text-align: center; color: #999; font-size: 13px; margin-bottom: 24px; }
  .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-bottom: 20px; }
  .stat {
    background: #f8f9fa; border-radius: 12px; padding: 16px; text-align: center;
    transition: transform 0.2s;
  }
  .stat:hover { transform: translateY(-2px); }
  .stat.green { background: #e8f5e9; }
  .stat.red { background: #ffebee; }
  .stat.orange { background: #fff3e0; }
  .stat.blue { background: #e3f2fd; }
  .stat.purple { background: #f3e5f5; }
  .stat-value { font-size: 28px; font-weight: 700; line-height: 1.2; }
  .stat-label { font-size: 12px; color: #888; margin-top: 4px; }
  .stat.green .stat-value { color: #2e7d32; }
  .stat.red .stat-value { color: #c62828; }
  .stat.orange .stat-value { color: #e65100; }
  .stat.blue .stat-value { color: #1565c0; }
  .stat.purple .stat-value { color: #7b1fa2; }
  .section { margin-top: 20px; }
  .section-title { font-size: 13px; color: #999; font-weight: 600; margin-bottom: 8px; text-transform: uppercase; letter-spacing: 0.5px; }
  .config-row {
    display: flex; justify-content: space-between; align-items: center;
    padding: 10px 0; border-bottom: 1px solid #f0f0f0; font-size: 14px;
  }
  .config-row:last-child { border-bottom: none; }
  .config-key { color: #666; }
  .config-val { color: #333; font-weight: 600; }
  .config-val.active { color: #2e7d32; }
  .config-val.inactive { color: #bbb; }
  .cooldown-bar { width: 100%; height: 6px; background: #eee; border-radius: 3px; overflow: hidden; margin-top: 8px; }
  .cooldown-fill { height: 100%; background: linear-gradient(90deg, #667eea, #764ba2); border-radius: 3px; transition: width 1s; }
  .footer { text-align: center; margin-top: 20px; font-size: 12px; color: #ccc; }
  .refresh { float: right; cursor: pointer; background: none; border: 1px solid #ddd; border-radius: 6px;
    padding: 4px 12px; font-size: 12px; color: #666; transition: all 0.2s; }
  .refresh:hover { background: #f5f5f5; border-color: #999; }
  .section-content { font-size: 13px; color: #555; line-height: 1.6; }
  .log-entry { padding: 8px 0; border-bottom: 1px solid #f0f0f0; }
  .log-entry:last-child { border-bottom: none; }
  .log-time { font-size: 11px; color: #aaa; }
  .log-msg { font-size: 13px; }
</style>
</head>
<body>
<div class="card">
  <h1>📊 API限频统计</h1>
  <p class="subtitle" id="datetime">加载中...</p>
  <button class="refresh" onclick="location.reload()">🔄 刷新</button>
  <div class="grid">
    <div class="stat blue">
      <div class="stat-value" id="daily_count">0</div>
      <div class="stat-label">今日已调用</div>
    </div>
    <div class="stat green">
      <div class="stat-value" id="stats_total">0</div>
      <div class="stat-label">累计放行</div>
    </div>
    <div class="stat red">
      <div class="stat-value" id="stats_blocked">0</div>
      <div class="stat-label">累计拦截</div>
    </div>
    <div class="stat orange">
      <div class="stat-value" id="pass_rate">0%</div>
      <div class="stat-label">放行率</div>
    </div>
  </div>
  <div id="extra_stats"></div>
  <div id="cooldown_section" style="display:none;">
    <div class="section">
      <div class="section-title">⏳ 冷却状态</div>
      <div style="font-size:14px;color:#e65100;" id="cooldown_text"></div>
      <div class="cooldown-bar"><div class="cooldown-fill" id="cooldown_bar" style="width:0%"></div></div>
    </div>
  </div>
  <div class="section">
    <div class="section-title">⚙️ 当前配置</div>
    <div id="config_list"></div>
  </div>
  <div class="section">
    <div class="section-title">📝 最近拦截记录</div>
    <div class="section-content" id="log_list">暂无记录</div>
  </div>
  <div class="footer">API限频器 v2.4.0 · by 小红蛋</div>
</div>
<script>
const data = __DATA__;
document.getElementById('datetime').textContent = data.date + ' ' + data.time;
document.getElementById('daily_count').textContent = data.daily_count + (data.daily_limit > 0 ? ' / ' + data.daily_limit : '');
document.getElementById('stats_total').textContent = data.stats_total;
document.getElementById('stats_blocked').textContent = data.stats_blocked;
const total = data.stats_total + data.stats_blocked;
document.getElementById('pass_rate').textContent = total > 0 ? Math.round(data.stats_total / total * 100) + '%' : '-';

let extra = '';
if (data.stats_cooldown_triggered > 0) extra += '<div class="config-row"><span class="config-key">冷却触发</span><span class="config-val">' + data.stats_cooldown_triggered + ' 次</span></div>';
if (data.stats_daily_blocked > 0) extra += '<div class="config-row"><span class="config-key">每日限额拦截</span><span class="config-val">' + data.stats_daily_blocked + ' 次</span></div>';
if (data.stats_dialog_blocked > 0) extra += '<div class="config-row"><span class="config-key">对话上限拦截</span><span class="config-val">' + data.stats_dialog_blocked + ' 次</span></div>';
if (data.stats_blacklist_blocked > 0) extra += '<div class="config-row"><span class="config-key">黑名单拦截</span><span class="config-val">' + data.stats_blacklist_blocked + ' 次</span></div>';
document.getElementById('extra_stats').innerHTML = extra;

if (data.cooldown_remaining > 0) {
  document.getElementById('cooldown_section').style.display = 'block';
  document.getElementById('cooldown_text').textContent = '冷却中，剩余 ' + Math.round(data.cooldown_remaining) + ' 秒';
  const pct = Math.min(100, data.cooldown_remaining / data.cooldown_total * 100);
  document.getElementById('cooldown_bar').style.width = pct + '%';
}

let configs = [
  ['调用间隔', data.cooldown_seconds > 0 ? data.cooldown_seconds + ' 秒' : '未设置', data.cooldown_seconds > 0],
  ['次数限制', data.max_calls > 0 ? data.max_calls + ' 次' : '未设置', data.max_calls > 0],
  ['冷却时间', data.cooldown_minutes > 0 ? data.cooldown_minutes + ' 分钟' : '未设置', data.cooldown_minutes > 0],
  ['每日配额', data.daily_limit > 0 ? data.daily_limit + ' 次' : '未设置', data.daily_limit > 0],
  ['对话切断', data.quota_limit > 0 ? (data.quota_mode === '单用户' ? '单用户 ' : '全局 ') + data.quota_limit + ' 次' : '未设置', data.quota_limit > 0],
  ['安静时段', data.quiet_hours || '未设置', !!data.quiet_hours],
  ['白名单', data.whitelist_count + ' 人', data.whitelist_count > 0],
  ['黑名单', data.blacklist_count + ' 人', data.blacklist_count > 0],
  ['分时段', data.timeslot_enabled ? data.timeslot_info : '未设置', data.timeslot_enabled],
  ['群独立配额', data.group_quotas > 0 ? data.group_quotas + ' 个群' : '未设置', data.group_quotas > 0],
  ['拒绝消息', data.reject_message ? '已设置' : '未设置', !!data.reject_message],
];
let html = '';
configs.forEach(function(c) {
  html += '<div class="config-row"><span class="config-key">' + c[0] + '</span><span class="config-val ' + (c[2] ? 'active' : 'inactive') + '">' + c[1] + '</span></div>';
});
document.getElementById('config_list').innerHTML = html;

// 拦截记录
if (data.logs && data.logs.length > 0) {
  let logHtml = '';
  data.logs.forEach(function(log) {
    logHtml += '<div class="log-entry"><div class="log-time">' + log.time + '</div><div class="log-msg">' + log.msg + '</div></div>';
  });
  document.getElementById('log_list').innerHTML = logHtml;
}
</script>
</body>
</html>"""


def _get_local_ip() -> str:
    """获取本机局域网 IP"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


@register(
    "astrbot_plugin_api_limiter",
    "小红蛋",
    "多功能API调用管理插件，包含调用间隔限制、次数限制加冷却重开、安静时段定时切断、白/黑名单、分时段限频、群聊独立配额七大功能",
    "2.4.0",
    "https://github.com/xiaohondan/astrbot_plugin_api_limiter"
)
class APIRateLimiter(Star):
    """API调用限频器 - 防止API过度调用导致余额不足"""

    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        # 间隔限制
        self.last_call_time: float = 0.0
        # 次数限制 + 冷却
        self.call_count: int = 0
        self.cooldown_until: float = 0.0
        self._cooldown_total: float = 0.0
        # 安静时段
        self._quiet_parse_error: bool = False
        self._quiet_parse_result: tuple[int, int] | None = None
        # 配额耗尽告警（仅首次）
        self._quota_exhausted_warned: bool = False
        # 超额提醒
        self._daily_warned: bool = False
        # 每日配额
        self._daily_count: int = 0
        self._daily_date: date = date.today()
        # 对话切断
        self._dialog_counts: dict[str, int] = {}  # key -> 对话计数
        self._dialog_cooldowns: dict[str, float] = {}  # key -> 冷却截止时间
        # 拦截日志（最多保留200条）
        self._block_logs: list[dict] = []
        self._max_logs: int = 200
        # 分时段限频（缓存解析结果）
        self._timeslot_cache: dict = {}  # hour -> {cooldown_seconds, max_calls, cooldown_minutes}
        self._timeslot_parse_error: bool = False
        # 群聊独立配额
        self._group_quotas: dict[str, int] = {}  # group_id -> daily_limit
        # 统计数据
        self._stats_total: int = 0
        self._stats_blocked: int = 0
        self._stats_cooldown_triggered: int = 0
        self._stats_daily_blocked: int = 0
        self._stats_dialog_blocked: int = 0
        self._stats_blacklist_blocked: int = 0
        # 并发锁
        self._lock = asyncio.Lock()
        # WebUI
        self._webui_runner: web.AppRunner | None = None
        self._webui_port: int = 0
        self._webui_site: web.TCPSite | None = None

    # ==================== 安静时段 ====================

    def _get_quiet_hours(self) -> tuple[int, int] | None:
        """解析安静时段配置，返回 (开始分钟, 结束分钟) 或 None"""
        quiet_start: str = self.config.get("quiet_start", "")
        quiet_end: str = self.config.get("quiet_end", "")
        if not quiet_start or not quiet_end:
            self._quiet_parse_error = False
            self._quiet_parse_result = None
            return None
        if self._quiet_parse_error:
            return None
        try:
            start: int = self._parse_time(quiet_start, "quiet_start")
            end: int = self._parse_time(quiet_end, "quiet_end")
            if start == end:
                logger.warning("[API限频器] 安静时段开始与结束时间相同，视为未启用")
                self._quiet_parse_error = True
                return None
            self._quiet_parse_result = (start, end)
            return self._quiet_parse_result
        except (ValueError, TypeError) as e:
            logger.warning(f"[API限频器] 安静时段配置格式错误（{e}），已跳过")
            self._quiet_parse_error = True
            return None

    def _parse_time(self, time_str: str, field_name: str = "") -> int:
        """将 HH:MM 或纯数字（视为分钟）解析为当天分钟数（0-1439）"""
        time_str = str(time_str).strip()
        if not time_str:
            raise ValueError("时间为空")
        if ":" in time_str:
            parts = time_str.split(":")
            if len(parts) != 2:
                raise ValueError(
                    f"字段 '{field_name}' 格式错误: '{time_str}'，期望 HH:MM 或纯分钟数"
                )
            try:
                total = int(parts[0]) * 60 + int(parts[1])
            except ValueError:
                raise ValueError(
                    f"字段 '{field_name}' 格式错误: '{time_str}'，小时和分钟必须是整数"
                )
        else:
            try:
                total = int(time_str)
            except ValueError:
                raise ValueError(
                    f"字段 '{field_name}' 格式错误: '{time_str}'，必须是整数"
                )
        if total < 0 or total > 1439:
            raise ValueError(
                f"字段 '{field_name}' 时间值 {total} 超出范围 (0-1439)"
            )
        return total

    def _is_in_quiet_hours(self) -> bool:
        """判断当前是否在安静时段内"""
        quiet = self._get_quiet_hours()
        if not quiet:
            return False
        start_min, end_min = quiet
        now = datetime.now()
        now_min: int = now.hour * 60 + now.minute
        if start_min < end_min:
            return start_min <= now_min < end_min
        else:
            return now_min >= start_min or now_min < end_min

    # ==================== 白名单 ====================

    def _is_whitelisted(self, event: AstrMessageEvent) -> bool:
        """判断发送者是否在白名单中"""
        whitelist_str: str = self.config.get("whitelist", "")
        if not whitelist_str:
            return False
        try:
            sender_id = str(event.get_sender_id())
        except Exception:
            return False
        whitelist_ids = [
            uid.strip() for uid in whitelist_str.split(",") if uid.strip()
        ]
        return sender_id in whitelist_ids

    # ==================== 黑名单 ====================

    def _is_blacklisted(self, event: AstrMessageEvent) -> bool:
        """判断发送者是否在黑名单中"""
        blacklist_str: str = self.config.get("blacklist", "")
        if not blacklist_str:
            return False
        try:
            sender_id = str(event.get_sender_id())
        except Exception:
            return False
        blacklist_ids = [
            uid.strip() for uid in blacklist_str.split(",") if uid.strip()
        ]
        return sender_id in blacklist_ids

    # ==================== 分时段限频 ====================

    def _parse_timeslots(self) -> dict:
        """解析分时段限频配置，返回 {小时: {cooldown_seconds, max_calls, cooldown_minutes}}"""
        timeslot_str: str = self.config.get("timeslots", "")
        if not timeslot_str:
            return {}
        if self._timeslot_parse_error:
            return {}

        result = {}
        try:
            slots = json.loads(timeslot_str)
            if not isinstance(slots, dict):
                self._timeslot_parse_error = True
                return {}
            for hour_str, params in slots.items():
                h = int(hour_str)
                if h < 0 or h > 23:
                    continue
                cs = params.get("cooldown_seconds", 0) if isinstance(params, dict) else 0
                mc = params.get("max_calls", 0) if isinstance(params, dict) else 0
                cm = params.get("cooldown_minutes", 0) if isinstance(params, dict) else 0
                result[h] = {
                    "cooldown_seconds": max(0, int(cs)),
                    "max_calls": max(0, int(mc)),
                    "cooldown_minutes": max(0, int(cm)),
                }
            self._timeslot_parse_error = False
            self._timeslot_cache = result
            return result
        except (json.JSONDecodeError, ValueError, TypeError) as e:
            logger.warning(f"[API限频器] 分时段配置解析错误（{e}），使用上次缓存")
            self._timeslot_parse_error = True
            return self._timeslot_cache

    def _get_timeslot_params(self) -> tuple[int, int, int]:
        """获取当前时段的限频参数，返回 (cooldown_seconds, max_calls, cooldown_minutes)"""
        timeslots = self._parse_timeslots()
        current_hour = datetime.now().hour
        if current_hour in timeslots:
            t = timeslots[current_hour]
            return t["cooldown_seconds"], t["max_calls"], t["cooldown_minutes"]
        return (
            self._safe_get_int("cooldown_seconds", 3),
            self._safe_get_int("max_calls", 0),
            self._safe_get_int("cooldown_minutes", 0),
        )

    # ==================== 群聊独立配额 ====================

    def _parse_group_quotas(self) -> dict:
        """解析群聊独立配额配置，返回 {group_id: daily_limit}"""
        group_quotas_str: str = self.config.get("group_quotas", "")
        if not group_quotas_str:
            return {}
        result = {}
        try:
            for item in group_quotas_str.split(";"):
                item = item.strip()
                if not item:
                    continue
                parts = item.split(":")
                if len(parts) == 2:
                    gid = parts[0].strip()
                    try:
                        limit = int(parts[1].strip())
                        if limit > 0:
                            result[gid] = limit
                    except ValueError:
                        continue
        except Exception as e:
            logger.warning(f"[API限频器] 群聊独立配额解析错误（{e}）")
        return result

    def _get_daily_limit(self, event: AstrMessageEvent) -> int:
        """获取适用的每日配额（优先群聊独立配额，其次全局配额）"""
        try:
            group_id = event.get_group_id()
            if group_id:
                gid = str(group_id)
                if gid in self._group_quotas:
                    return self._group_quotas[gid]
        except Exception:
            pass
        return self._safe_get_int("daily_limit", 0)

    # ==================== 每日配额 ====================

    def _reset_daily_if_needed(self) -> None:
        """如果跨天了，重置每日计数和对话切断计数"""
        today = date.today()
        if self._daily_date != today:
            logger.info(
                f"[API限频器] 新的一天，重置每日配额"
                f"（昨日调用 {self._daily_count} 次）"
            )
            self._daily_count = 0
            self._daily_date = today
            self._daily_warned = False
            # 重置对话切断计数
            if self._dialog_counts:
                logger.info(
                    f"[API限频器] 新的一天，重置对话切断计数"
                    f"（追踪 {len(self._dialog_counts)} 个对象）"
                )
            self._dialog_counts.clear()
            self._dialog_cooldowns.clear()

    def _is_daily_exceeded(self, event: AstrMessageEvent) -> bool:
        """判断是否超出每日配额"""
        daily_limit = self._get_daily_limit(event)
        if daily_limit <= 0:
            return False
        return self._daily_count >= daily_limit

    # ==================== 超额提醒 ====================

    def _check_daily_warning(self, event: AstrMessageEvent) -> bool:
        """检查是否需要发送超额提醒，返回 True 表示刚刚触发了提醒"""
        daily_limit = self._get_daily_limit(event)
        if daily_limit <= 0:
            return False
        threshold = int(daily_limit * 0.8)
        if threshold <= 0:
            return False
        if self._daily_count >= threshold and not self._daily_warned:
            self._daily_warned = True
            return True
        return False

    async def _send_daily_warning(self, event: AstrMessageEvent) -> None:
        """发送超额提醒"""
        daily_limit = self._get_daily_limit(event)
        try:
            await event.send(
                f"⚠️ API调用已达今日配额的 80%（{self._daily_count}/{daily_limit}），"
                f"剩余 {daily_limit - self._daily_count} 次"
            )
        except Exception as e:
            logger.warning(f"[API限频器] 发送超额提醒失败: {e}")

    # ==================== 对话切断 ====================

    def _get_dialog_key(self, event: AstrMessageEvent) -> str:
        """获取对话切断的 key"""
        try:
            sender_id = str(event.get_sender_id())
        except Exception:
            return ""
        quota_mode: str = self.config.get("quota_mode", "")
        if not quota_mode:
            return ""

        is_private = True
        try:
            group_id = event.get_group_id()
            if group_id:
                is_private = False
        except Exception:
            pass

        if quota_mode == "单用户":
            prefix = "pm" if is_private else "grp"
            return f"{prefix}:{sender_id}"
        elif quota_mode == "全局":
            if is_private:
                return f"global_pm:{sender_id}"
            else:
                try:
                    group_id = str(event.get_group_id())
                    return f"global_grp:{group_id}"
                except Exception:
                    return f"global_pm:{sender_id}"
        return ""

    def _check_dialog_limit(self, event: AstrMessageEvent) -> bool:
        """检查对话切断限制，返回 True 表示应拦截"""
        quota_mode: str = self.config.get("quota_mode", "")
        quota_limit = self._safe_get_int("quota_limit", 0)
        quota_cooldown = self._safe_get_int("quota_cooldown_minutes", 0)

        if not quota_mode or quota_limit <= 0:
            return False

        key = self._get_dialog_key(event)
        if not key:
            return False

        if key in self._dialog_cooldowns:
            if time.time() < self._dialog_cooldowns[key]:
                return True
            else:
                del self._dialog_cooldowns[key]
                self._dialog_counts[key] = 0

        return False

    def _update_dialog_count(self, event: AstrMessageEvent) -> None:
        """放行后更新对话计数"""
        quota_mode: str = self.config.get("quota_mode", "")
        quota_limit = self._safe_get_int("quota_limit", 0)
        quota_cooldown = self._safe_get_int("quota_cooldown_minutes", 0)

        if not quota_mode or quota_limit <= 0:
            return

        key = self._get_dialog_key(event)
        if not key:
            return

        if key not in self._dialog_counts:
            self._dialog_counts[key] = 0

        self._dialog_counts[key] += 1

        if self._dialog_counts[key] > quota_limit:
            self._stats_dialog_blocked += 1
            if quota_cooldown > 0:
                self._dialog_cooldowns[key] = time.time() + quota_cooldown * 60
                self._dialog_counts[key] = 0
                logger.info(
                    f"[API限频器] 对话切断：{key} 已达上限 "
                    f"（{quota_limit}次），进入冷却 {quota_cooldown} 分钟"
                )
            else:
                logger.info(
                    f"[API限频器] 对话切断：{key} 已达上限 "
                    f"（{quota_limit}次），持续阻断"
                )

    # ==================== 拦截日志 ====================

    def _add_block_log(self, reason: str, event: AstrMessageEvent) -> None:
        """记录拦截日志"""
        sender = "unknown"
        try:
            sender = str(event.get_sender_id())[:8]
        except Exception:
            pass
        group = ""
        try:
            gid = event.get_group_id()
            if gid:
                group = f" (群{str(gid)[:6]})"
        except Exception:
            pass
        now_str = datetime.now().strftime("%H:%M:%S")
        entry = {
            "time": now_str,
            "msg": f"[{reason}] {sender}{group}",
        }
        self._block_logs.append(entry)
        # 保持最大数量
        if len(self._block_logs) > self._max_logs:
            self._block_logs = self._block_logs[-self._max_logs:]

    # ==================== 工具方法 ====================

    def _is_in_cooldown(self) -> bool:
        """判断是否在冷却期中"""
        return time.time() < self.cooldown_until

    def _safe_get_int(self, key: str, default: int = 0) -> int:
        """安全获取整数配置，防止负值"""
        value = self.config.get(key, default)
        try:
            value = int(value)
        except (ValueError, TypeError):
            logger.warning(
                f"[API限频器] 配置项 '{key}' 值无效（{value}），使用默认值 {default}"
            )
            return default
        if value < 0:
            logger.warning(
                f"[API限频器] 配置项 '{key}' 为负值（{value}），已修正为 0"
            )
            return 0
        return value

    async def _send_reject(self, event: AstrMessageEvent) -> None:
        """发送自定义拒绝消息"""
        msg: str = self.config.get("reject_message", "")
        if msg:
            try:
                await event.send(msg)
            except Exception as e:
                logger.warning(f"[API限频器] 发送拒绝消息失败: {e}")

    # ==================== WebUI 统计面板 ====================

    def _build_stats_data(self) -> dict:
        """构建统计面板数据"""
        daily_limit = self._safe_get_int("daily_limit", 0)
        cooldown_seconds = self._safe_get_int("cooldown_seconds", 0)
        max_calls = self._safe_get_int("max_calls", 0)
        cooldown_minutes = self._safe_get_int("cooldown_minutes", 0)
        quota_limit = self._safe_get_int("quota_limit", 0)
        quota_cooldown = self._safe_get_int("quota_cooldown_minutes", 0)
        whitelist_str: str = self.config.get("whitelist", "")
        blacklist_str: str = self.config.get("blacklist", "")
        reject_msg: str = self.config.get("reject_message", "")
        quota_mode: str = self.config.get("quota_mode", "")
        quiet_hours = self._get_quiet_hours()
        timeslots = self._parse_timeslots()
        timeslot_enabled = bool(timeslots)

        quiet_text = ""
        if quiet_hours:
            quiet_text = f"{quiet_hours[0] // 60:02d}:{quiet_hours[0] % 60:02d} - {quiet_hours[1] // 60:02d}:{quiet_hours[1] % 60:02d}"

        whitelist_count = len([u for u in whitelist_str.split(",") if u.strip()])
        blacklist_count = len([u for u in blacklist_str.split(",") if u.strip()])

        # 分时段信息
        if timeslot_enabled:
            current_hour = datetime.now().hour
            if current_hour in timeslots:
                t = timeslots[current_hour]
                timeslot_info = f"当前({current_hour}时): 间隔{t['cooldown_seconds']}s 限次{t['max_calls']}次 冷却{t['cooldown_minutes']}分钟"
            else:
                timeslot_info = f"共 {len(timeslots)} 个时段，当前时段使用默认"
        else:
            timeslot_info = ""

        cooldown_remaining = 0.0
        if self._is_in_cooldown():
            cooldown_remaining = self.cooldown_until - time.time()

        # 最近10条日志
        logs = self._block_logs[-10:] if self._block_logs else []

        return {
            "date": date.today().strftime("%Y-%m-%d"),
            "time": datetime.now().strftime("%H:%M:%S"),
            "daily_count": self._daily_count,
            "daily_limit": daily_limit,
            "stats_total": self._stats_total,
            "stats_blocked": self._stats_blocked,
            "stats_cooldown_triggered": self._stats_cooldown_triggered,
            "stats_daily_blocked": self._stats_daily_blocked,
            "stats_dialog_blocked": self._stats_dialog_blocked,
            "stats_blacklist_blocked": self._stats_blacklist_blocked,
            "cooldown_seconds": cooldown_seconds,
            "max_calls": max_calls,
            "cooldown_minutes": cooldown_minutes,
            "quota_mode": quota_mode,
            "quota_limit": quota_limit,
            "quota_cooldown_minutes": quota_cooldown,
            "whitelist_count": whitelist_count,
            "blacklist_count": blacklist_count,
            "reject_message": reject_msg,
            "quiet_hours": quiet_text,
            "cooldown_remaining": round(cooldown_remaining, 1),
            "cooldown_total": self._cooldown_total,
            "timeslot_enabled": timeslot_enabled,
            "timeslot_info": timeslot_info,
            "group_quotas": len(self._group_quotas),
            "logs": logs,
        }

    async def _webui_handler(self, request: web.Request) -> web.Response:
        """WebUI 统计面板 HTTP 处理器"""
        data = self._build_stats_data()
        html = STATS_HTML.replace("__DATA__", json.dumps(data, ensure_ascii=False))
        return web.Response(text=html, content_type="text/html", charset="utf-8")

    async def _webui_api_handler(self, request: web.Request) -> web.Response:
        """WebUI API 接口"""
        data = self._build_stats_data()
        return web.json_response(data)

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("开启统计面板")
    async def webui_start(self, event: AstrMessageEvent):
        """开启统计面板"""
        if self._webui_runner is not None:
            local_ip = _get_local_ip()
            yield event.plain_result(
                f"📊 统计面板已在运行中\n"
                f"🔗 本地访问：http://localhost:{self._webui_port}\n"
                f"🔗 局域网：http://{local_ip}:{self._webui_port}"
            )
            return

        port = self._safe_get_int("stats_port", 6285)
        app = web.Application()
        app.router.add_get("/", self._webui_handler)
        app.router.add_get("/api", self._webui_api_handler)
        self._webui_runner = web.AppRunner(app)

        try:
            await self._webui_runner.setup()
            self._webui_site = web.TCPSite(self._webui_runner, "0.0.0.0", port)
            await self._webui_site.start()
            self._webui_port = port
            local_ip = _get_local_ip()
            logger.info(f"[API限频器] 统计面板已启动：http://localhost:{port}")
            yield event.plain_result(
                f"📊 统计面板已开启！\n"
                f"🔗 本地访问：http://localhost:{port}\n"
                f"🔗 局域网：http://{local_ip}:{port}\n"
                f"发送「关闭统计面板」可关闭面板"
            )
        except OSError as e:
            self._webui_runner = None
            self._webui_site = None
            logger.error(f"[API限频器] 统计面板启动失败：{e}")
            yield event.plain_result(f"❌ 统计面板启动失败：端口 {port} 可能被占用\n{e}")

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("关闭统计面板")
    async def webui_stop(self, event: AstrMessageEvent):
        """关闭统计面板"""
        if self._webui_runner is None:
            yield event.plain_result("📊 统计面板未在运行")
            return

        try:
            await self._webui_runner.cleanup()
            logger.info(f"[API限频器] 统计面板已关闭（端口 {self._webui_port}）")
            self._webui_runner = None
            self._webui_site = None
            self._webui_port = 0
            yield event.plain_result("📊 统计面板已关闭")
        except Exception as e:
            logger.error(f"[API限频器] 关闭统计面板失败：{e}")
            yield event.plain_result(f"❌ 关闭失败：{e}")

    # ==================== 统计面板指令 ====================

    @filter.command("webui")
    async def stats(self, event: AstrMessageEvent):
        """查看 API 调用统计"""
        daily_limit = self._get_daily_limit(event)
        cooldown_remain = 0.0
        if self._is_in_cooldown():
            cooldown_remain = self.cooldown_until - time.time()

        today_str = date.today().strftime("%Y-%m-%d")
        now_str = datetime.now().strftime("%H:%M:%S")

        lines = [
            "📊 **API限频统计**",
            f"📅 日期：{today_str}  ⏰ 时间：{now_str}",
            "",
            f"🔥 今日已调用：**{self._daily_count}**"
            + (f" / {daily_limit}" if daily_limit > 0 else "（无限制）"),
            f"✅ 累计放行：**{self._stats_total}** 次",
            f"🚫 累计拦截：**{self._stats_blocked}** 次",
        ]

        if self._stats_cooldown_triggered > 0:
            lines.append(f"⏳ 冷却触发：**{self._stats_cooldown_triggered}** 次")
        if self._stats_daily_blocked > 0:
            lines.append(f"📋 每日限额拦截：**{self._stats_daily_blocked}** 次")
        if self._stats_dialog_blocked > 0:
            lines.append(f"✂️ 对话切断拦截：**{self._stats_dialog_blocked}** 次")
        if self._stats_blacklist_blocked > 0:
            lines.append(f"🚫 黑名单拦截：**{self._stats_blacklist_blocked}** 次")
        if cooldown_remain > 0:
            lines.append(f"🔴 当前冷却剩余：**{cooldown_remain:.0f}** 秒")

        # 当前限制状态摘要
        cooldown_sec = self._safe_get_int("cooldown_seconds", 0)
        max_calls = self._safe_get_int("max_calls", 0)
        quiet_hours = self._get_quiet_hours()
        quota_mode: str = self.config.get("quota_mode", "")
        quota_limit = self._safe_get_int("quota_limit", 0)
        timeslots = self._parse_timeslots()
        blacklist_str: str = self.config.get("blacklist", "")
        group_quotas_str: str = self.config.get("group_quotas", "")

        status_parts: list[str] = []
        if cooldown_sec > 0:
            status_parts.append(f"间隔 {cooldown_sec}s")
        if max_calls > 0:
            status_parts.append(f"次数 {max_calls}")
        if daily_limit > 0:
            status_parts.append(f"日限 {daily_limit}")
        if quota_limit > 0 and quota_mode:
            status_parts.append(f"对话切断({quota_mode})")
        if quiet_hours:
            status_parts.append("安静时段")
        if timeslots:
            status_parts.append(f"分时段({len(timeslots)}档)")
        if blacklist_str:
            status_parts.append(f"黑名单({len([u for u in blacklist_str.split(',') if u.strip()])}人)")
        if group_quotas_str:
            status_parts.append(f"群独立配额({len(group_quotas_str.split(';'))}个群)")
        if status_parts:
            lines.append(f"⚙️ 已启用：{', '.join(status_parts)}")
        else:
            lines.append("⚙️ 当前：无任何限制")

        lines.append("")
        lines.append("🌐 发送「开启统计面板」可在浏览器中查看可视化统计")

        yield event.plain_result("\n".join(lines))

    # ==================== 重置指令 ====================

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("重置限频")
    async def reset_all(self, event: AstrMessageEvent):
        """管理员手动重置所有计数和冷却"""
        async with self._lock:
            self.last_call_time = 0
            self.call_count = 0
            self.cooldown_until = 0
            self._cooldown_total = 0
            self._daily_count = 0
            self._daily_date = date.today()
            self._daily_warned = False
            self._quota_exhausted_warned = False
            self._dialog_counts.clear()
            self._dialog_cooldowns.clear()
            self._block_logs.clear()

        yield event.plain_result(
            "🔄 已重置所有限频数据：\n"
            "- 调用间隔计数 → 0\n"
            "- 次数限制计数 → 0\n"
            "- 冷却状态 → 已解除\n"
            "- 每日配额 → 已清零\n"
            "- 对话切断计数 → 已清零\n"
            "- 拦截日志 → 已清空"
        )

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("重置冷却")
    async def reset_cooldown(self, event: AstrMessageEvent):
        """重置冷却状态"""
        async with self._lock:
            self.cooldown_until = 0
            self._cooldown_total = 0
            self.call_count = 0
            self._quota_exhausted_warned = False
        yield event.plain_result("🔄 冷却已重置，可以继续调用")

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("重置配额")
    async def reset_daily(self, event: AstrMessageEvent):
        """重置每日配额"""
        self._daily_count = 0
        self._daily_date = date.today()
        self._daily_warned = False
        yield event.plain_result(f"🔄 每日配额已重置（剩余 {self._get_daily_limit(event)} 次）")

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("重置对话")
    async def reset_dialog(self, event: AstrMessageEvent):
        """重置对话切断计数"""
        self._dialog_counts.clear()
        self._dialog_cooldowns.clear()
        yield event.plain_result("🔄 对话切断计数已全部重置")

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("清空日志")
    async def clear_logs(self, event: AstrMessageEvent):
        """清空拦截日志"""
        self._block_logs.clear()
        yield event.plain_result("🗑️ 拦截日志已清空")

    # ==================== 导出日志 ====================

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("导出日志")
    async def export_logs(self, event: AstrMessageEvent):
        """导出拦截日志"""
        if not self._block_logs:
            yield event.plain_result("📝 暂无拦截记录")
            return

        lines = [
            f"API限频器 拦截日志",
            f"导出时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"共 {len(self._block_logs)} 条记录",
            "─" * 40,
        ]
        for entry in self._block_logs:
            lines.append(f"[{entry['time']}] {entry['msg']}")

        text = "\n".join(lines)
        # AstrBot 单条消息有长度限制，分段发送
        chunk_size = 3000
        chunks = [text[i:i+chunk_size] for i in range(0, len(text), chunk_size)]
        for i, chunk in enumerate(chunks):
            if i == len(chunks) - 1:
                yield event.plain_result(chunk)
            else:
                yield event.plain_result(chunk + "（未完）")

    # ==================== 核心拦截逻辑 ====================

    @filter.on_llm_request()
    async def handle_llm_request(self, event: AstrMessageEvent, req: ProviderRequest):
        # 黑名单检查（优先级最高，直接拒绝不占配额）
        if self._is_blacklisted(event):
            self._stats_blocked += 1
            self._stats_blacklist_blocked += 1
            self._add_block_log("黑名单", event)
            logger.info("[API限频器] 黑名单用户，已直接拒绝")
            await self._send_reject(event)
            event.stop_event()
            return

        # 白名单检查
        if self._is_whitelisted(event):
            return

        # 跨天重置每日配额和对话切断计数
        self._reset_daily_if_needed()

        # 同步群聊独立配额配置
        self._group_quotas = self._parse_group_quotas()

        # 每日配额检查
        if self._is_daily_exceeded(event):
            self._stats_blocked += 1
            self._stats_daily_blocked += 1
            daily_limit = self._get_daily_limit(event)
            logger.info(
                f"[API限频器] 今日调用已达每日配额 "
                f"（{self._daily_count}/{daily_limit}），已拒绝本次请求"
            )
            self._add_block_log("每日配额", event)
            await self._send_reject(event)
            event.stop_event()
            return

        # 超额提醒（在请求放行前检查）
        if self._check_daily_warning(event):
            await self._send_daily_warning(event)

        # 获取当前时段限频参数
        cooldown_seconds, max_calls, cooldown_minutes = self._get_timeslot_params()

        # 功能二、三、四：冷却期 + 间隔限制 + 计数更新 + 对话切断（全部在同一锁内）
        async with self._lock:
            # 冷却期检查
            if self._is_in_cooldown():
                self._stats_blocked += 1
                remain = self.cooldown_until - time.time()
                logger.info(f"[API限频器] 冷却中，剩余 {remain:.0f} 秒")
                self._add_block_log("冷却中", event)
                await self._send_reject(event)
                event.stop_event()
                return

            # 对话切断检查（在间隔检查之前，优先级更高）
            if self._check_dialog_limit(event):
                self._stats_blocked += 1
                key = self._get_dialog_key(event)
                quota_limit = self._safe_get_int("quota_limit", 0)
                quota_cooldown = self._safe_get_int("quota_cooldown_minutes", 0)
                logger.info(
                    f"[API限频器] 对话切断生效：{key} "
                    f"（上限 {quota_limit} 次"
                    + (f"，冷却 {quota_cooldown} 分钟" if quota_cooldown > 0 else "，持续阻断")
                    + "）"
                )
                self._add_block_log("对话切断", event)
                await self._send_reject(event)
                event.stop_event()
                return

            # 间隔检查
            now = time.time()
            elapsed = now - self.last_call_time
            if cooldown_seconds > 0 and elapsed < cooldown_seconds:
                self._stats_blocked += 1
                wait_time = cooldown_seconds - elapsed
                logger.info(
                    f"[API限频器] 调用间隔限制：距上次调用仅 {elapsed:.2f} 秒，"
                    f"需等待 {wait_time:.2f} 秒，已拒绝本次请求"
                )
                self._add_block_log("间隔限制", event)
                await self._send_reject(event)
                event.stop_event()
                return

            # 更新调用时间与计数
            self.last_call_time = now
            self.call_count += 1
            self._daily_count += 1
            self._stats_total += 1

            # 更新对话切断计数（放行后也要计数）
            self._update_dialog_count(event)

            # 检查是否达到次数上限
            max_calls_t = max_calls
            cooldown_minutes_t = cooldown_minutes
            if max_calls_t > 0 and self.call_count > max_calls_t:
                self._stats_cooldown_triggered += 1
                if cooldown_minutes_t > 0:
                    self._cooldown_total = cooldown_minutes_t * 60.0
                    self.cooldown_until = time.time() + cooldown_minutes_t * 60
                    self.call_count = 0
                    self._quota_exhausted_warned = False
                    logger.info(
                        f"[API限频器] 已达调用上限 ({max_calls_t}次)，"
                        f"进入冷却期 {cooldown_minutes_t} 分钟"
                    )
                else:
                    if not self._quota_exhausted_warned:
                        logger.warning(
                            f"[API限频器] 已达调用上限 ({max_calls_t}次)，"
                            f"未设置冷却时间，后续请求将被持续拒绝"
                        )
                        self._quota_exhausted_warned = True
                self._stats_blocked += 1
                self._add_block_log("次数上限", event)
                await self._send_reject(event)
                event.stop_event()
                return

    async def terminate(self):
        # 关闭 WebUI 服务器
        if self._webui_runner is not None:
            try:
                await self._webui_runner.cleanup()
            except Exception:
                pass
            self._webui_runner = None
            self._webui_site = None
        logger.info("[API限频器] 插件已卸载，资源已释放")

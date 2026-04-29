import asyncio
import time
from datetime import datetime, date
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger, AstrBotConfig
from astrbot.api.provider import ProviderRequest


@register(
    "astrbot_plugin_api_limiter",
    "小红蛋",
    "多功能API调用管理插件，包含调用间隔限制、次数限制加冷却重开、安静时段定时切断三大功能",
    "2.0.0",
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
        # 安静时段
        self._quiet_parse_error: bool = False
        self._quiet_parse_result: tuple[int, int] | None = None
        # 配额耗尽告警（仅首次）
        self._quota_exhausted_warned: bool = False
        # 每日配额
        self._daily_count: int = 0
        self._daily_date: date = date.today()
        # 统计数据
        self._stats_total: int = 0
        self._stats_blocked: int = 0
        self._stats_cooldown_triggered: int = 0
        self._stats_daily_blocked: int = 0
        # 并发锁
        self._lock = asyncio.Lock()

    # ==================== 安静时段 ====================

    def _get_quiet_hours(self) -> tuple[int, int] | None:
        """解析安静时段配置，返回 (开始分钟, 结束分钟) 或 None

        配置解析失败时仅打印一次警告，避免日志刷屏。
        """
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

    # ==================== 每日配额 ====================

    def _reset_daily_if_needed(self) -> None:
        """如果跨天了，重置每日计数"""
        today = date.today()
        if self._daily_date != today:
            logger.info(
                f"[API限频器] 新的一天，重置每日配额"
                f"（昨日调用 {self._daily_count} 次）"
            )
            self._daily_count = 0
            self._daily_date = today

    def _is_daily_exceeded(self) -> bool:
        """判断是否超出每日配额"""
        daily_limit = self._safe_get_int("daily_limit", 0)
        if daily_limit <= 0:
            return False
        return self._daily_count >= daily_limit

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
        """发送自定义拒绝消息（如果配置了的话）"""
        msg: str = self.config.get("reject_message", "")
        if msg:
            try:
                await event.send(msg)
            except Exception as e:
                logger.warning(f"[API限频器] 发送拒绝消息失败: {e}")

    # ==================== 统计面板指令 ====================

    @filter.command("限频统计")
    async def stats(self, event: AstrMessageEvent):
        """查看 API 调用统计"""
        daily_limit = self._safe_get_int("daily_limit", 0)
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
        if cooldown_remain > 0:
            lines.append(f"🔴 当前冷却剩余：**{cooldown_remain:.0f}** 秒")

        # 当前限制状态摘要
        cooldown_sec = self._safe_get_int("cooldown_seconds", 0)
        max_calls = self._safe_get_int("max_calls", 0)
        quiet_hours = self._get_quiet_hours()

        status_parts: list[str] = []
        if cooldown_sec > 0:
            status_parts.append(f"间隔 {cooldown_sec}s")
        if max_calls > 0:
            status_parts.append(f"次数 {max_calls}")
        if daily_limit > 0:
            status_parts.append(f"日限 {daily_limit}")
        if quiet_hours:
            status_parts.append("安静时段")
        if status_parts:
            lines.append(f"⚙️ 已启用：{', '.join(status_parts)}")
        else:
            lines.append("⚙️ 当前：无任何限制")

        yield event.plain_result("\n".join(lines))

    # ==================== 核心拦截逻辑 ====================

    @filter.on_llm_request()
    async def handle_llm_request(self, event: AstrMessageEvent, req: ProviderRequest):
        # 白名单检查
        if self._is_whitelisted(event):
            return

        # 跨天重置每日配额
        self._reset_daily_if_needed()

        # 每日配额检查
        if self._is_daily_exceeded():
            self._stats_blocked += 1
            self._stats_daily_blocked += 1
            daily_limit = self._safe_get_int("daily_limit", 0)
            logger.info(
                f"[API限频器] 今日调用已达每日配额 "
                f"（{self._daily_count}/{daily_limit}），已拒绝本次请求"
            )
            await self._send_reject(event)
            event.stop_event()
            return

        # 功能一：安静时段 - 屏蔽API调用
        if self._is_in_quiet_hours():
            self._stats_blocked += 1
            quiet_start = self.config.get("quiet_start", "")
            quiet_end = self.config.get("quiet_end", "")
            logger.info(
                f"[API限频器] 当前处于安静时段 "
                f"({quiet_start} - {quiet_end})，已屏蔽API调用"
            )
            await self._send_reject(event)
            event.stop_event()
            return

        # 功能二、三：冷却期 + 间隔限制 + 计数更新（全部在同一锁内）
        cooldown_seconds = self._safe_get_int("cooldown_seconds", 3)
        async with self._lock:
            # 冷却期检查
            if self._is_in_cooldown():
                self._stats_blocked += 1
                remain = self.cooldown_until - time.time()
                logger.info(f"[API限频器] 冷却中，剩余 {remain:.0f} 秒")
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
                await self._send_reject(event)
                event.stop_event()
                return

            # 更新调用时间与计数
            self.last_call_time = now
            self.call_count += 1
            self._daily_count += 1
            self._stats_total += 1

            # 检查是否达到次数上限
            max_calls = self._safe_get_int("max_calls", 0)
            cooldown_minutes = self._safe_get_int("cooldown_minutes", 0)
            if max_calls > 0 and self.call_count > max_calls:
                self._stats_cooldown_triggered += 1
                if cooldown_minutes > 0:
                    self.cooldown_until = time.time() + cooldown_minutes * 60
                    self.call_count = 0
                    self._quota_exhausted_warned = False
                    logger.info(
                        f"[API限频器] 已达调用上限 ({max_calls}次)，"
                        f"进入冷却期 {cooldown_minutes} 分钟"
                    )
                else:
                    if not self._quota_exhausted_warned:
                        logger.warning(
                            f"[API限频器] 已达调用上限 ({max_calls}次)，"
                            f"未设置冷却时间，后续请求将被持续拒绝，"
                            f"请配置 cooldown_minutes"
                        )
                        self._quota_exhausted_warned = True
                self._stats_blocked += 1
                await self._send_reject(event)
                event.stop_event()
                return

    async def terminate(self):
        logger.info("[API限频器] 插件已卸载，资源已释放")

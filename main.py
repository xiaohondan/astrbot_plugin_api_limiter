import asyncio
import time
from datetime import datetime
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger, AstrBotConfig
from astrbot.api.llm import ProviderRequest


@register(
    "astrbot_plugin_api_rate_limiter",
    "小红蛋",
    "多功能API调用管理插件，包含调用间隔限制、次数限制加冷却重开、安静时段定时切断三大功能",
    "1.0.0",
    "https://github.com/xiaohondan/astrbot_plugin_api_rate_limiter"
)
class APIRateLimiter(Star):
    """API调用限频器 - 防止API过度调用导致余额不足"""

    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        self.last_call_time: float = 0.0
        self.call_count: int = 0
        self.cooldown_until: float = 0.0
        self._lock = asyncio.Lock()

    def _get_quiet_hours(self) -> tuple[int, int] | None:
        """解析安静时段配置，返回 (开始分钟, 结束分钟) 或 None"""
        quiet_start: str = self.config.get("quiet_start", "")
        quiet_end: str = self.config.get("quiet_end", "")
        if not quiet_start or not quiet_end:
            return None
        try:
            start: int = self._parse_time(quiet_start, "quiet_start")
            end: int = self._parse_time(quiet_end, "quiet_end")
            if start == end:
                logger.warning("[API限频器] 安静时段开始与结束时间相同，视为未启用")
                return None
            return (start, end)
        except (ValueError, TypeError) as e:
            logger.warning(f"[API限频器] 安静时段配置格式错误（{e}），已跳过")
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

    @filter.on_llm_request()
    async def handle_llm_request(self, event: AstrMessageEvent, req: ProviderRequest):
        # 功能一：安静时段 - 屏蔽API调用
        if self._is_in_quiet_hours():
            quiet_start = self.config.get("quiet_start", "")
            quiet_end = self.config.get("quiet_end", "")
            logger.info(
                f"[API限频器] 当前处于安静时段 "
                f"({quiet_start} - {quiet_end})，已屏蔽API调用"
            )
            event.stop_event()
            return

        # 功能二、三：冷却期 + 间隔限制 + 计数更新（全部在同一锁内）
        cooldown_seconds = self._safe_get_int("cooldown_seconds", 3)
        async with self._lock:
            # 冷却期检查
            if self._is_in_cooldown():
                remain = self.cooldown_until - time.time()
                logger.info(f"[API限频器] 冷却中，剩余 {remain:.0f} 秒")
                event.stop_event()
                return

            # 间隔检查
            now = time.time()
            elapsed = now - self.last_call_time
            if cooldown_seconds > 0 and elapsed < cooldown_seconds:
                wait_time = cooldown_seconds - elapsed
                logger.info(
                    f"[API限频器] 调用间隔限制：距上次调用仅 {elapsed:.2f} 秒，"
                    f"需等待 {wait_time:.2f} 秒，已拒绝本次请求"
                )
                event.stop_event()
                return

            # 更新调用时间与计数
            self.last_call_time = now
            self.call_count += 1

            # 检查是否达到次数上限
            max_calls = self._safe_get_int("max_calls", 0)
            cooldown_minutes = self._safe_get_int("cooldown_minutes", 0)
            if max_calls > 0 and self.call_count > max_calls:
                if cooldown_minutes > 0:
                    self.cooldown_until = time.time() + cooldown_minutes * 60
                    self.call_count = 0
                    logger.info(
                        f"[API限频器] 已达调用上限 ({max_calls}次)，"
                        f"进入冷却期 {cooldown_minutes} 分钟"
                    )
                else:
                    logger.warning(
                        f"[API限频器] 已达调用上限 ({max_calls}次)，"
                        f"未设置冷却时间，后续请求将被持续拒绝，请配置 cooldown_minutes"
                    )
                event.stop_event()
                return

    async def terminate(self):
        logger.info("[API限频器] 插件已卸载，资源已释放")

import asyncio
import time
from datetime import datetime
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star
from astrbot.api import logger, AstrBotConfig


class APIRateLimiter(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        self.last_call_time = 0.0
        self.call_count = 0
        self.cooldown_until = 0.0  # 冷却截止时间

    def _get_quiet_hours(self):
        """解析安静时段配置，返回 (开始分钟, 结束分钟) 或 None"""
        quiet_start = self.config.get("quiet_start", "")
        quiet_end = self.config.get("quiet_end", "")
        if not quiet_start or not quiet_end:
            return None
        return self._parse_time(quiet_start), self._parse_time(quiet_end)

    def _parse_time(self, time_str):
        """将 HH:MM 或纯数字（视为分钟）解析为当天分钟数"""
        time_str = str(time_str).strip()
        if ":" in time_str:
            parts = time_str.split(":")
            return int(parts[0]) * 60 + int(parts[1])
        # 纯数字，视为分钟数
        val = int(time_str)
        return val

    def _is_in_quiet_hours(self):
        """判断当前是否在安静时段内"""
        quiet = self._get_quiet_hours()
        if not quiet:
            return False
        start_min, end_min = quiet
        now_min = datetime.now().hour * 60 + datetime.now().minute
        if start_min <= end_min:
            # 同一天内，如 23:00 - 06:00 这种跨天的情况
            if start_min <= now_min < end_min:
                return True
        else:
            # 跨天，如 23:00(1380) - 06:00(360)
            if now_min >= start_min or now_min < end_min:
                return True
        return False

    def _is_in_cooldown(self):
        """判断是否在冷却期中"""
        return time.time() < self.cooldown_until

    @filter.on_llm_request()
    async def handle_llm_request(self, event: AstrMessageEvent):
        # 功能一：定时切断API（安静时段）
        if self._is_in_quiet_hours():
            quiet_start = self.config.get("quiet_start", "")
            quiet_end = self.config.get("quiet_end", "")
            logger.info(f"[API限频器] 当前处于安静时段 ({quiet_start} - {quiet_end})，已屏蔽API调用")
            event.stop_event()  # 阻止API调用
            return

        # 功能二：冷却期检查（次数用完后等待恢复）
        if self._is_in_cooldown():
            remain = self.cooldown_until - time.time()
            logger.info(f"[API限频器] 冷却中，剩余 {remain:.0f} 秒")
            event.stop_event()
            return

        # 功能三：冷却间隔（每次API调用前的最小间隔）
        cooldown_seconds = self.config.get("cooldown_seconds", 0)
        if cooldown_seconds and cooldown_seconds > 0:
            now = time.time()
            elapsed = now - self.last_call_time
            if elapsed < cooldown_seconds:
                wait_time = cooldown_seconds - elapsed
                logger.info(f"[API限频器] 调用间隔限制：需等待 {wait_time:.2f} 秒")
                await asyncio.sleep(wait_time)

        # 更新调用计数
        self.last_call_time = time.time()
        self.call_count += 1

        # 检查是否达到次数上限
        max_calls = self.config.get("max_calls", 0)
        cooldown_minutes = self.config.get("cooldown_minutes", 0)
        if max_calls and max_calls > 0 and self.call_count >= max_calls:
            if cooldown_minutes and cooldown_minutes > 0:
                self.cooldown_until = time.time() + cooldown_minutes * 60
                logger.info(
                    f"[API限频器] 已达调用上限 ({max_calls}次)，"
                    f"进入冷却期 {cooldown_minutes} 分钟"
                )
                self.call_count = 0

    async def terminate(self):
        logger.info("[API限频器] 插件已卸载")

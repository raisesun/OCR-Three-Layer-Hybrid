#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
内存日志缓冲区

记录最近的日志条目，供 Demo 页面显示。
"""

import logging
import time
from collections import deque
from typing import List, Dict, Optional


class MemoryLogHandler(logging.Handler):
    """内存日志处理器，存储最近 N 条日志"""

    def __init__(self, capacity: int = 200):
        super().__init__()
        self.capacity = capacity
        self.logs = deque(maxlen=capacity)

    def emit(self, record: logging.LogRecord):
        try:
            log_entry = {
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(record.created)),
                "level": record.levelname,
                "logger": record.name,
                "message": record.getMessage(),
            }
            self.logs.append(log_entry)
        except Exception:
            self.handleError(record)

    def get_logs(
        self,
        level: Optional[str] = None,
        logger: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict]:
        """获取日志（支持过滤）"""
        logs = list(self.logs)

        if level:
            logs = [l for l in logs if l["level"] == level]

        if logger:
            logs = [l for l in logs if logger in l["logger"]]

        # 返回最新的 limit 条
        return logs[-limit:]

    def clear(self):
        """清空日志"""
        self.logs.clear()


# 全局实例
log_buffer = MemoryLogHandler(capacity=200)


def setup_memory_logging():
    """配置内存日志（添加到根 logger）"""
    root_logger = logging.getLogger()
    root_logger.addHandler(log_buffer)
    log_buffer.setLevel(logging.INFO)
    return log_buffer

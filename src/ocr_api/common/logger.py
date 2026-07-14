#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
结构化日志模块

提供 JSON 格式日志输出，便于日志分析系统（ELK、Loki 等）解析。

特性：
- JSON 格式输出（timestamp, level, message, module, function, line, 上下文字段）
- 支持上下文注入（task_id, api_key, duration_ms 等）
- 兼容传统文本格式（通过环境变量 OCR_LOG_FORMAT 控制）
- 自动添加请求 ID（trace_id）

使用示例：
    from ocr_api.common.logger import get_logger, set_log_context

    logger = get_logger(__name__)

    # 设置上下文（后续日志自动包含）
    set_log_context(task_id="task_123", api_key="key_abc")

    # 记录日志（自动包含上下文）
    logger.info("任务开始处理", extra={"duration_ms": 1234})
"""

import json
import logging
import os
import sys
import time
import uuid
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any, Dict, Optional


# ========== 上下文变量（线程/协程安全）==========

_log_context: ContextVar[Dict[str, Any]] = ContextVar("log_context", default={})


def set_log_context(**kwargs: Any) -> None:
    """设置日志上下文（后续日志自动包含这些字段）

    Args:
        task_id: 任务 ID
        api_key: API Key（脱敏后）
        duration_ms: 耗时（毫秒）
        doc_type: 文档类型
        layer: 处理层
        ... 其他自定义字段

    示例：
        set_log_context(task_id="task_123", api_key="key_***")
        logger.info("任务处理完成")  # 自动包含 task_id 和 api_key
    """
    current = _log_context.get({}).copy()
    current.update(kwargs)
    _log_context.set(current)


def clear_log_context() -> None:
    """清空日志上下文"""
    _log_context.set({})


def get_log_context() -> Dict[str, Any]:
    """获取当前日志上下文"""
    return _log_context.get({}).copy()


# ========== JSON 格式化器 ==========

class JSONFormatter(logging.Formatter):
    """JSON 格式日志输出器

    输出格式：
    {
        "timestamp": "2026-07-09T18:30:45.123456Z",
        "level": "INFO",
        "message": "任务处理完成",
        "module": "task_manager",
        "function": "mark_completed",
        "line": 123,
        "logger": "ocr_three_layer_hybrid.task_manager",
        "task_id": "task_123",
        "api_key": "key_***",
        "duration_ms": 1234,
        "trace_id": "abc-123-def"
    }
    """

    def format(self, record: logging.LogRecord) -> str:
        """格式化日志记录为 JSON 字符串"""
        # 基础字段
        log_data: Dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
            "logger": record.name,
        }

        # 添加上下文（task_id, api_key, duration_ms 等）
        context = get_log_context()
        log_data.update(context)

        # 添加 extra 字段（通过 logger.info(..., extra={...}) 传入）
        if hasattr(record, "extra_fields"):
            log_data.update(record.extra_fields)

        # 添加异常信息
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        # 序列化为 JSON
        return json.dumps(log_data, ensure_ascii=False, default=str)


class TextFormatter(logging.Formatter):
    """传统文本格式日志输出器（兼容原有格式）"""

    def __init__(self):
        super().__init__(
            fmt="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )


# ========== 日志配置 ==========

def setup_logging(
    level: str = "INFO",
    log_format: Optional[str] = None,
    log_file: Optional[str] = None,
) -> None:
    """配置日志系统

    Args:
        level: 日志级别 (DEBUG/INFO/WARNING/ERROR)
        log_format: 日志格式 ("json" 或 "text")，默认从环境变量 OCR_LOG_FORMAT 读取
        log_file: 日志文件路径（可选，不指定则只输出到控制台）

    环境变量：
        OCR_LOG_FORMAT: 日志格式（json/text），默认 text
        OCR_LOG_LEVEL: 日志级别，默认 INFO
    """
    # 从环境变量读取配置
    if log_format is None:
        log_format = os.getenv("OCR_LOG_FORMAT", "text").lower()

    if level is None:
        level = os.getenv("OCR_LOG_LEVEL", "INFO").upper()

    # 创建格式化器
    if log_format == "json":
        formatter = JSONFormatter()
    else:
        formatter = TextFormatter()

    # 配置根日志记录器
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    # 清空现有处理器
    root_logger.handlers.clear()

    # 控制台处理器
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # 文件处理器（可选）
    if log_file:
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

    # 降低第三方库日志级别
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("requests").setLevel(logging.WARNING)
    logging.getLogger("PIL").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """获取日志记录器

    Args:
        name: 日志记录器名称（通常使用 __name__）

    Returns:
        logging.Logger 实例
    """
    return logging.getLogger(name)


# ========== 便捷函数 ==========

def log_with_context(
    logger: logging.Logger,
    level: int,
    message: str,
    **context_fields: Any,
) -> None:
    """带上下文的日志记录（便捷函数）

    Args:
        logger: 日志记录器
        level: 日志级别（logging.INFO, logging.ERROR 等）
        message: 日志消息
        **context_fields: 额外上下文字段

    示例：
        log_with_context(
            logger,
            logging.INFO,
            "任务处理完成",
            task_id="task_123",
            duration_ms=1234,
        )
    """
    # 合并上下文
    current_context = get_log_context()
    current_context.update(context_fields)

    # 临时设置上下文
    token = _log_context.set(current_context)
    try:
        logger.log(level, message)
    finally:
        _log_context.reset(token)


class LogContext:
    """日志上下文管理器（用于 with 语句）

    示例：
        with LogContext(task_id="task_123", api_key="key_***"):
            logger.info("开始处理")  # 自动包含 task_id 和 api_key
            # ... 处理逻辑
            logger.info("处理完成")
    """

    def __init__(self, **kwargs: Any):
        self.context = kwargs
        self.token = None
        self.previous_context = None

    def __enter__(self):
        self.previous_context = get_log_context()
        self.previous_context.update(self.context)
        self.token = _log_context.set(self.previous_context)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.token:
            _log_context.reset(self.token)
        return False

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OCR API 服务 — 异步任务管理器

基于 SQLite 的持久化任务管理，支持：
- 任务提交与状态跟踪
- 并发控制（信号量）
- 任务取消
- 结果持久化存储

架构设计：
- TaskManager: 管理任务生命周期（提交/查询/取消）
- TaskWorker: 执行实际 OCR 处理（后台线程）
- 使用 thread-local SQLite 连接保证线程安全

可独立复用：其他项目可直接导入 TaskManager，只需提供 OCRService 实例。
"""

import sqlite3
import threading
import time
import uuid
import asyncio
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class TaskManager:
    """异步任务管理器（SQLite 持久化）

    特性：
    - SQLite 持久化：重启不丢失任务状态
    - 线程安全：每个线程使用独立连接
    - 并发控制：限制同时处理的任务数
    - 可取消：支持取消 pending/processing 状态的任务
    """

    def __init__(
        self,
        db_path: str = "/tmp/ocr_tasks.db",
        max_concurrent: int = 100,
    ):
        self._db_path = db_path
        self._max_concurrent = max_concurrent
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._local = threading.local()
        self._cancel_flags: Dict[str, bool] = {}  # task_id -> cancelled
        self._init_db()
        logger.info(f"[TaskManager] 初始化完成 | db={db_path} | 并发上限={max_concurrent}")

    # ========== 数据库连接管理 ==========

    def _get_conn(self) -> sqlite3.Connection:
        """获取当前线程的 SQLite 连接（thread-local）"""
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(self._db_path)
            self._local.conn.row_factory = sqlite3.Row
            # 启用 WAL 模式，提高并发读写性能
            self._local.conn.execute("PRAGMA journal_mode=WAL")
        return self._local.conn

    def _init_db(self):
        """初始化数据库表结构"""
        conn = self._get_conn()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS tasks (
                id TEXT PRIMARY KEY,
                status TEXT NOT NULL DEFAULT 'pending',
                file_count INTEGER NOT NULL DEFAULT 0,
                processed_count INTEGER NOT NULL DEFAULT 0,
                priority TEXT NOT NULL DEFAULT 'normal',
                callback_url TEXT,
                created_at TEXT NOT NULL,
                started_at TEXT,
                completed_at TEXT,
                total_time_ms INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS task_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT NOT NULL,
                file_name TEXT NOT NULL,
                file_path TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                result_json TEXT,
                error_message TEXT,
                processed_at TEXT,
                timing_ms INTEGER DEFAULT 0,
                FOREIGN KEY (task_id) REFERENCES tasks(id)
            );

            CREATE INDEX IF NOT EXISTS idx_task_results_task_id
                ON task_results(task_id);

            -- 配额追踪表
            CREATE TABLE IF NOT EXISTS api_usage (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                api_key TEXT NOT NULL,
                endpoint TEXT NOT NULL,
                called_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_api_usage_key_time
                ON api_usage(api_key, called_at);
        """)
        conn.commit()

    # ========== 任务生命周期 ==========

    def create_task(
        self,
        file_count: int,
        priority: str = "normal",
        callback_url: Optional[str] = None,
    ) -> str:
        """创建新任务，返回 task_id"""
        task_id = f"task_{datetime.now().strftime('%Y%m%d')}_{uuid.uuid4().hex[:12]}"
        now = datetime.now().isoformat()

        conn = self._get_conn()
        conn.execute(
            """INSERT INTO tasks (id, status, file_count, priority, callback_url, created_at)
               VALUES (?, 'pending', ?, ?, ?, ?)""",
            (task_id, file_count, priority, callback_url, now),
        )
        conn.commit()
        logger.info(f"[TaskManager] 创建任务 | id={task_id} | files={file_count}")
        return task_id

    def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        """获取任务信息"""
        conn = self._get_conn()
        row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if row:
            return dict(row)
        return None

    def mark_processing(self, task_id: str):
        """标记任务为处理中"""
        now = datetime.now().isoformat()
        conn = self._get_conn()
        conn.execute(
            "UPDATE tasks SET status = 'processing', started_at = ? WHERE id = ?",
            (now, task_id),
        )
        conn.commit()

    def mark_completed(self, task_id: str, total_time_ms: int = 0):
        """标记任务为已完成"""
        now = datetime.now().isoformat()
        conn = self._get_conn()
        conn.execute(
            "UPDATE tasks SET status = 'completed', completed_at = ?, total_time_ms = ? WHERE id = ?",
            (now, total_time_ms, task_id),
        )
        conn.commit()
        logger.info(f"[TaskManager] 任务完成 | id={task_id} | 耗时={total_time_ms}ms")

    def mark_cancelled(self, task_id: str) -> bool:
        """标记任务为已取消

        Returns:
            True 表示成功取消，False 表示任务不存在或状态不允许取消
        """
        task = self.get_task(task_id)
        if not task:
            return False
        if task["status"] not in ("pending", "processing"):
            return False

        now = datetime.now().isoformat()
        conn = self._get_conn()
        conn.execute(
            "UPDATE tasks SET status = 'cancelled', completed_at = ? WHERE id = ?",
            (now, task_id),
        )
        conn.commit()
        self._cancel_flags[task_id] = True
        logger.info(f"[TaskManager] 任务已取消 | id={task_id}")
        return True

    def mark_failed(self, task_id: str, error_message: str):
        """标记任务为失败"""
        now = datetime.now().isoformat()
        conn = self._get_conn()
        conn.execute(
            "UPDATE tasks SET status = 'failed', completed_at = ? WHERE id = ?",
            (now, task_id),
        )
        conn.commit()
        logger.error(f"[TaskManager] 任务失败 | id={task_id} | error={error_message}")

    # ========== 文件结果管理 ==========

    def add_file_result(
        self,
        task_id: str,
        file_name: str,
        file_path: str,
    ):
        """添加文件记录（初始状态 pending）"""
        conn = self._get_conn()
        conn.execute(
            """INSERT INTO task_results (task_id, file_name, file_path, status)
               VALUES (?, ?, ?, 'pending')""",
            (task_id, file_name, file_path),
        )
        conn.commit()

    def update_file_result(
        self,
        task_id: str,
        file_name: str,
        status: str,
        result_json: str = "",
        error_message: str = "",
        timing_ms: int = 0,
    ):
        """更新文件处理结果"""
        now = datetime.now().isoformat()
        conn = self._get_conn()
        conn.execute(
            """UPDATE task_results
               SET status = ?, result_json = ?, error_message = ?,
                   processed_at = ?, timing_ms = ?
               WHERE task_id = ? AND file_name = ?""",
            (status, result_json, error_message, now, timing_ms, task_id, file_name),
        )
        conn.commit()

    def increment_processed(self, task_id: str):
        """增加已处理计数"""
        conn = self._get_conn()
        conn.execute(
            "UPDATE tasks SET processed_count = processed_count + 1 WHERE id = ?",
            (task_id,),
        )
        conn.commit()

    def get_file_results(self, task_id: str) -> List[Dict[str, Any]]:
        """获取任务的所有文件结果"""
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT * FROM task_results WHERE task_id = ? ORDER BY id",
            (task_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    # ========== 查询接口 ==========

    def get_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """获取任务状态（含进度和结果）"""
        task = self.get_task(task_id)
        if not task:
            return None

        file_results = self.get_file_results(task_id)
        total = task["file_count"]
        processed = task["processed_count"]
        progress = int((processed / total * 100) if total > 0 else 0)

        # 计算预估剩余时间
        estimated_remaining = None
        if task["status"] == "processing" and processed > 0:
            started = datetime.fromisoformat(task["started_at"])
            elapsed = (datetime.now() - started).total_seconds()
            avg_per_file = elapsed / processed
            remaining_files = total - processed
            estimated_remaining = int(avg_per_file * remaining_files)

        result = None
        if task["status"] == "completed":
            result = self._build_result(task, file_results)

        return {
            "task_id": task_id,
            "status": task["status"],
            "progress": progress,
            "processed": processed,
            "total": total,
            "submitted_at": task["created_at"],
            "started_at": task["started_at"],
            "completed_at": task["completed_at"],
            "estimated_remaining": estimated_remaining,
            "result": result,
            "error": None,  # TODO: 存储失败原因
        }

    def _build_result(
        self,
        task: Dict[str, Any],
        file_results: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """构建任务完成后的结果数据"""
        import json

        results = []
        for fr in file_results:
            item = {
                "file_name": fr["file_name"],
                "status": fr["status"],
            }
            if fr["status"] == "success" and fr["result_json"]:
                try:
                    item.update(json.loads(fr["result_json"]))
                except json.JSONDecodeError:
                    pass
            elif fr["status"] == "failed":
                item["error"] = fr["error_message"]
            results.append(item)

        total = task["file_count"]
        success = sum(1 for r in results if r.get("status") == "success")
        failed = total - success

        return {
            "results": results,
            "summary": {
                "total": total,
                "success": success,
                "failed": failed,
                "total_time_ms": task["total_time_ms"],
                "avg_time_ms": round(task["total_time_ms"] / total, 1) if total > 0 else 0,
            },
        }

    # ========== 取消检查 ==========

    def is_cancelled(self, task_id: str) -> bool:
        """检查任务是否被取消（供 Worker 调用）"""
        return self._cancel_flags.get(task_id, False)

    # ========== 配额追踪 ==========

    def record_api_call(self, api_key: str, endpoint: str):
        """记录 API 调用（用于配额统计）"""
        now = datetime.now().isoformat()
        conn = self._get_conn()
        conn.execute(
            "INSERT INTO api_usage (api_key, endpoint, called_at) VALUES (?, ?, ?)",
            (api_key, endpoint, now),
        )
        conn.commit()

    def get_quota(self, api_key: str) -> Dict[str, Any]:
        """获取 API Key 的配额使用情况"""
        conn = self._get_conn()

        # 统计本小时调用次数
        hour_start = datetime.now().replace(minute=0, second=0, microsecond=0)
        hour_start_str = hour_start.isoformat()
        reset_at = hour_start.replace(hour=hour_start.hour + 1 if hour_start.hour < 23 else 0)
        if reset_at.hour == 0:
            reset_at = reset_at.replace(day=reset_at.day + 1)

        row = conn.execute(
            "SELECT COUNT(*) as cnt FROM api_usage WHERE api_key = ? AND called_at >= ?",
            (api_key, hour_start_str),
        ).fetchone()
        calls_used = row["cnt"] if row else 0
        calls_limit = 6000  # 默认每小时 6000 次（100次/分钟）

        # 统计异步任务
        row = conn.execute(
            "SELECT COUNT(*) as cnt FROM tasks WHERE status IN ('pending', 'processing')",
        ).fetchone()
        pending_tasks = row["cnt"] if row else 0

        # 统计存储使用
        upload_dir = Path("/tmp/ocr_uploads")
        storage_used = 0
        if upload_dir.exists():
            for f in upload_dir.rglob("*"):
                if f.is_file():
                    storage_used += f.stat().st_size

        return {
            "api_calls": {
                "used": calls_used,
                "limit": calls_limit,
                "reset_at": reset_at.isoformat(),
            },
            "storage": {
                "used_mb": round(storage_used / (1024 * 1024), 2),
                "limit_mb": 10240,  # 10GB
            },
            "async_tasks": {
                "pending": pending_tasks,
                "limit": self._max_concurrent,
            },
        }


class TaskWorker:
    """任务处理 Worker（后台线程执行）

    从 TaskManager 获取任务，调用 OCRService 处理文件，更新结果。
    """

    def __init__(self, task_manager: TaskManager, ocr_service):
        self._tm = task_manager
        self._ocr = ocr_service

    async def process(self, task_id: str, files: List[Dict[str, str]]):
        """处理任务中的所有文件

        Args:
            task_id: 任务 ID
            files: [{"file_name": "xxx.jpg", "file_path": "/tmp/xxx.jpg"}, ...]
        """
        import json

        total = len(files)
        logger.info(f"[Worker] 开始处理任务 | id={task_id} | files={total}")

        self._tm.mark_processing(task_id)
        start_time = time.time()

        try:
            for idx, file_info in enumerate(files):
                # 检查取消标志
                if self._tm.is_cancelled(task_id):
                    logger.info(f"[Worker] 任务已取消 | id={task_id} | 进度={idx}/{total}")
                    return

                file_name = file_info["file_name"]
                file_path = file_info["file_path"]

                file_start = time.time()
                try:
                    # 调用 OCRService 处理单张图片
                    result = await asyncio.to_thread(
                        self._ocr.process_single,
                        file_path,
                    )

                    # 存储成功结果
                    result_json = json.dumps(result, ensure_ascii=False)
                    self._tm.update_file_result(
                        task_id=task_id,
                        file_name=file_name,
                        status="success",
                        result_json=result_json,
                        timing_ms=int((time.time() - file_start) * 1000),
                    )
                    self._tm.increment_processed(task_id)
                    logger.info(
                        f"[Worker] 文件处理成功 | task={task_id} | file={file_name} | "
                        f"进度={idx + 1}/{total}"
                    )

                except Exception as e:
                    # 存储失败结果
                    self._tm.update_file_result(
                        task_id=task_id,
                        file_name=file_name,
                        status="failed",
                        error_message=str(e),
                        timing_ms=int((time.time() - file_start) * 1000),
                    )
                    self._tm.increment_processed(task_id)
                    logger.error(
                        f"[Worker] 文件处理失败 | task={task_id} | file={file_name} | error={e}"
                    )

            # 所有文件处理完成
            total_time_ms = int((time.time() - start_time) * 1000)
            self._tm.mark_completed(task_id, total_time_ms)
            logger.info(
                f"[Worker] 任务完成 | id={task_id} | 耗时={total_time_ms}ms"
            )

        except Exception as e:
            total_time_ms = int((time.time() - start_time) * 1000)
            self._tm.mark_failed(task_id, str(e))
            logger.error(f"[Worker] 任务异常 | id={task_id} | error={e}")

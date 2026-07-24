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

import atexit
import sqlite3
import threading
import time
import uuid
import asyncio
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta

from ocr_api.common.logger import set_log_context, clear_log_context

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
        self._background_tasks: set = set()  # 后台任务引用，防止被 GC 回收
        self._init_db()
        # 注册 atexit 钩子，确保进程退出时关闭连接
        atexit.register(self.close)
        logger.info("[TaskManager] 初始化完成 | db=%s | 并发上限=%s", db_path, max_concurrent)

    # ========== 数据库连接管理 ==========

    def _get_conn(self) -> sqlite3.Connection:
        """获取当前线程的 SQLite 连接（thread-local）"""
        # threading.local 属性在首次访问前不存在；用 getattr 默认值替代 hasattr
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            # 启用 WAL 模式，提高并发读写性能
            conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn = conn
        return conn

    def close(self):
        """关闭当前线程的 SQLite 连接"""
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            try:
                conn.close()
                logger.debug("[TaskManager] 连接已关闭 | thread=%s", threading.current_thread().name)
            except Exception as e:
                logger.warning("[TaskManager] 关闭连接失败: %s", e)
            finally:
                self._local.conn = None

    def __enter__(self):
        """支持上下文管理器"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """退出上下文时关闭连接"""
        self.close()
        return False

    def submit_background(self, coro):
        """提交后台协程任务，保存引用防止被 GC 回收

        解决 asyncio.create_task 引用未保存导致任务中途被 GC 回收的问题。
        任务完成后自动从集合移除；异常会被记录日志而非静默丢失。

        Args:
            coro: 协程对象

        Returns:
            asyncio.Task
        """
        task = asyncio.create_task(coro)
        self._background_tasks.add(task)

        def _on_done(t: asyncio.Task):
            self._background_tasks.discard(t)
            if t.cancelled():
                return
            exc = t.exception()
            if exc is not None:
                logger.error(
                    "[TaskManager] 后台任务异常退出 | error=%s", exc, exc_info=exc,
                )

        task.add_done_callback(_on_done)
        return task

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
                total_time_ms INTEGER DEFAULT 0,
                error_message TEXT
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
        # 向后兼容迁移：已有数据库可能缺少新列
        migrations = [
            ("ALTER TABLE tasks ADD COLUMN error_message TEXT", "error_message"),
            ("ALTER TABLE tasks ADD COLUMN api_key TEXT", "api_key"),
            ("ALTER TABLE task_results ADD COLUMN file_size INTEGER DEFAULT 0", "file_size"),
        ]

        for alter_sql, column_name in migrations:
            try:
                conn.execute(alter_sql)
                conn.commit()
            except sqlite3.OperationalError:
                pass  # 列已存在

        # 为旧数据填充 file_size（如果文件存在）
        try:
            rows = conn.execute(
                "SELECT id, file_path FROM task_results WHERE file_size = 0 OR file_size IS NULL"
            ).fetchall()
            updated_count = 0
            for row in rows:
                file_path = Path(row["file_path"])
                if file_path.exists():
                    file_size = file_path.stat().st_size
                    conn.execute(
                        "UPDATE task_results SET file_size = ? WHERE id = ?",
                        (file_size, row["id"]),
                    )
                    updated_count += 1
            conn.commit()
            if updated_count > 0:
                logger.info("[TaskManager] 迁移完成：更新了 %s 条记录的 file_size", updated_count)
        except Exception as e:
            logger.warning("[TaskManager] 迁移 file_size 失败: %s", e)

    # ========== 任务生命周期 ==========

    def create_task(
        self,
        file_count: int,
        priority: str = "normal",
        callback_url: Optional[str] = None,
        api_key: Optional[str] = None,
    ) -> str:
        """创建新任务，返回 task_id"""
        task_id = f"task_{datetime.now().strftime('%Y%m%d')}_{uuid.uuid4().hex[:12]}"
        now = datetime.now().isoformat()

        conn = self._get_conn()
        conn.execute(
            """INSERT INTO tasks (id, status, file_count, priority, callback_url, created_at, api_key)
               VALUES (?, 'pending', ?, ?, ?, ?, ?)""",
            (task_id, file_count, priority, callback_url, now, api_key),
        )
        conn.commit()
        _masked_key = f"{api_key[:8]}..." if api_key else "None"
        logger.info("[TaskManager] 创建任务 | id=%s | files=%s | api_key=%s", task_id, file_count, _masked_key)
        return task_id

    def get_task(self, task_id: str, api_key: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """获取任务信息

        Args:
            api_key: 若提供则校验任务归属，归属不匹配返回 None（防止越权）
        """
        conn = self._get_conn()
        if api_key is not None:
            row = conn.execute(
                "SELECT * FROM tasks WHERE id = ? AND api_key = ?",
                (task_id, api_key),
            ).fetchone()
        else:
            row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if row:
            return dict(row)
        return None

    def mark_processing(self, task_id: str) -> bool:
        """标记任务为处理中

        Returns:
            True 表示成功更新，False 表示任务不在 pending 状态（可能已被取消）
        """
        now = datetime.now().isoformat()
        conn = self._get_conn()
        cursor = conn.execute(
            "UPDATE tasks SET status = 'processing', started_at = ? "
            "WHERE id = ? AND status = 'pending'",
            (now, task_id),
        )
        conn.commit()
        return cursor.rowcount > 0

    def mark_completed(self, task_id: str, total_time_ms: int = 0) -> bool:
        """标记任务为已完成

        Returns:
            True 表示成功更新，False 表示任务不在 processing 状态（已被取消/失败）
        """
        now = datetime.now().isoformat()
        conn = self._get_conn()
        cursor = conn.execute(
            "UPDATE tasks SET status = 'completed', completed_at = ?, total_time_ms = ? "
            "WHERE id = ? AND status = 'processing'",
            (now, total_time_ms, task_id),
        )
        conn.commit()
        success = cursor.rowcount > 0
        if success:
            logger.info("[TaskManager] 任务完成 | id=%s | 耗时=%sms", task_id, total_time_ms)
            # 清理取消标志，防止内存泄漏
            self._cancel_flags.pop(task_id, None)
        else:
            logger.info("[TaskManager] 任务完成跳过（状态已变更）| id=%s", task_id)
        return success

    def mark_cancelled(self, task_id: str, api_key: Optional[str] = None) -> bool:
        """标记任务为已取消

        Returns:
            True 表示成功取消，False 表示任务不存在或状态不允许取消
        """
        now = datetime.now().isoformat()
        conn = self._get_conn()
        # 使用 WHERE 子句确保原子性，避免 TOCTOU 竞态
        if api_key is not None:
            cursor = conn.execute(
                "UPDATE tasks SET status = 'cancelled', completed_at = ? "
                "WHERE id = ? AND api_key = ? AND status IN ('pending', 'processing')",
                (now, task_id, api_key),
            )
        else:
            cursor = conn.execute(
                "UPDATE tasks SET status = 'cancelled', completed_at = ? "
                "WHERE id = ? AND status IN ('pending', 'processing')",
                (now, task_id),
            )
        conn.commit()
        if cursor.rowcount > 0:
            self._cancel_flags[task_id] = True
            logger.info("[TaskManager] 任务已取消 | id=%s", task_id)
            return True
        return False

    def mark_failed(self, task_id: str, error_message: str) -> bool:
        """标记任务为失败

        Returns:
            True 表示成功更新，False 表示任务不在 processing 状态（已被取消/完成）
        """
        now = datetime.now().isoformat()
        conn = self._get_conn()
        cursor = conn.execute(
            "UPDATE tasks SET status = 'failed', completed_at = ?, error_message = ? "
            "WHERE id = ? AND status = 'processing'",
            (now, error_message, task_id),
        )
        conn.commit()
        success = cursor.rowcount > 0
        if success:
            logger.error("[TaskManager] 任务失败 | id=%s | error=%s", task_id, error_message)
            # 清理取消标志，防止内存泄漏
            self._cancel_flags.pop(task_id, None)
        else:
            logger.info("[TaskManager] 任务失败跳过（状态已变更）| id=%s", task_id)
        return success

    # ========== 文件结果管理 ==========

    def add_file_result(
        self,
        task_id: str,
        file_name: str,
        file_path: str,
    ):
        """添加文件记录（初始状态 pending）"""
        # 记录文件大小
        file_size = Path(file_path).stat().st_size if Path(file_path).exists() else 0

        conn = self._get_conn()
        conn.execute(
            """INSERT INTO task_results (task_id, file_name, file_path, file_size, status)
               VALUES (?, ?, ?, ?, 'pending')""",
            (task_id, file_name, file_path, file_size),
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

    def list_tasks(
        self,
        api_key: str,
        status_filter: Optional[str] = None,
        page: int = 1,
        size: int = 20,
    ) -> Dict[str, Any]:
        """列出任务（支持分页和状态过滤）

        Args:
            api_key: API Key（租户隔离）
            status_filter: 状态过滤（可选，如 "pending", "processing", "completed", "failed", "cancelled"）
            page: 页码（从 1 开始）
            size: 每页大小（默认 20）

        Returns:
            {
                "tasks": [...],  # 任务列表（不含详细结果）
                "total": 100,    # 总任务数
                "page": 1,       # 当前页码
                "size": 20,      # 每页大小
                "pages": 5       # 总页数
            }
        """
        conn = self._get_conn()

        # 构建 WHERE 子句
        where_clauses = ["api_key = ?"]
        params: List[Any] = [api_key]

        if status_filter:
            where_clauses.append("status = ?")
            params.append(status_filter)

        where_sql = " AND ".join(where_clauses)

        # 查询总数
        count_sql = f"SELECT COUNT(*) as cnt FROM tasks WHERE {where_sql}"
        total = conn.execute(count_sql, params).fetchone()["cnt"]

        # 计算分页
        offset = (page - 1) * size
        pages = (total + size - 1) // size if total > 0 else 0

        # 查询任务列表（按创建时间倒序）
        list_sql = f"""
            SELECT id, status, file_count, processed_count, priority,
                   callback_url, created_at, started_at, completed_at,
                   total_time_ms, error_message
            FROM tasks
            WHERE {where_sql}
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
        """
        rows = conn.execute(list_sql, params + [size, offset]).fetchall()

        tasks = []
        for row in rows:
            task = dict(row)
            # 计算进度百分比
            total_files = task["file_count"]
            processed = task["processed_count"]
            progress = int((processed / total_files * 100) if total_files > 0 else 0)

            tasks.append({
                "task_id": task["id"],
                "status": task["status"],
                "file_count": total_files,
                "processed_count": processed,
                "progress": progress,
                "priority": task["priority"],
                "created_at": task["created_at"],
                "started_at": task["started_at"],
                "completed_at": task["completed_at"],
                "total_time_ms": task["total_time_ms"],
                "error_message": task["error_message"],
            })

        return {
            "tasks": tasks,
            "total": total,
            "page": page,
            "size": size,
            "pages": pages,
        }

    def get_task_status(self, task_id: str, api_key: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """获取任务状态（含进度和结果）"""
        task = self.get_task(task_id, api_key=api_key)
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
            "error": task.get("error_message"),
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
        # 清理 7 天前的 api_usage（防表无限增长）
        cutoff = (datetime.now() - timedelta(days=7)).isoformat()
        conn.execute("DELETE FROM api_usage WHERE called_at < ?", (cutoff,))
        conn.commit()

    def get_quota(self, api_key: str) -> Dict[str, Any]:
        """获取 API Key 的配额使用情况"""
        conn = self._get_conn()

        # 统计本小时调用次数
        hour_start = datetime.now().replace(minute=0, second=0, microsecond=0)
        hour_start_str = hour_start.isoformat()
        reset_at = hour_start + timedelta(hours=1)  # 自动处理跨日/跨月/跨年（修复月末23点 replace(day+1) 越界崩溃）

        row = conn.execute(
            "SELECT COUNT(*) as cnt FROM api_usage WHERE api_key = ? AND called_at >= ?",
            (api_key, hour_start_str),
        ).fetchone()
        calls_used = row["cnt"] if row else 0
        calls_limit = 6000  # 默认每小时 6000 次（100次/分钟）

        # 统计该租户的异步任务数
        row = conn.execute(
            "SELECT COUNT(*) as cnt FROM tasks WHERE api_key = ? AND status IN ('pending', 'processing')",
            (api_key,),
        ).fetchone()
        pending_tasks = row["cnt"] if row else 0

        # 统计该租户的存储使用（从数据库查询，不扫描文件系统）
        row = conn.execute(
            """SELECT COALESCE(SUM(tr.file_size), 0) as total_size
               FROM task_results tr
               JOIN tasks t ON tr.task_id = t.id
               WHERE t.api_key = ?""",
            (api_key,),
        ).fetchone()
        storage_used = row["total_size"] if row else 0

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

        # 设置日志上下文（后续日志自动包含 task_id）
        set_log_context(task_id=task_id)

        total = len(files)
        logger.info("[Worker] 开始处理任务 | files=%d", total)

        # H15: 信号量限制并发任务数（max_concurrent）
        async with self._tm._semaphore:
            # 标记处理中（如果任务已被取消，则 status 不是 pending，返回 False）
            try:
                if not self._tm.mark_processing(task_id):
                    logger.info("[Worker] 任务状态非 pending，跳过处理")
                    self._tm._cancel_flags.pop(task_id, None)  # H19: 清理取消标志防泄漏
                    return
            except Exception as e:
                # mark_processing 异常（如 SQLite 锁）不应让任务静默卡在 pending
                logger.exception("[Worker] mark_processing 异常 | error=%s", e)
                self._tm._cancel_flags.pop(task_id, None)  # H19: 清理取消标志防泄漏
                return
            start_time = time.time()

            try:
                for idx, file_info in enumerate(files):
                    # 检查取消标志
                    if self._tm.is_cancelled(task_id):
                        logger.info("[Worker] 任务已取消 | progress=%d/%d", idx, total)
                        self._tm._cancel_flags.pop(task_id, None)  # H19: 清理取消标志防泄漏
                        return

                    file_name = file_info["file_name"]
                    file_path = file_info["file_path"]

                    file_start = time.time()
                    try:
                        # 调用 OCRService 处理单张图片（H18: 加超时，防 OCR 挂起致永久 processing）
                        try:
                            result = await asyncio.wait_for(
                                asyncio.to_thread(self._ocr.process_single, file_path),
                                timeout=300,  # 单文件 5 分钟超时
                            )
                        except asyncio.TimeoutError:
                            raise TimeoutError(f"OCR 处理超时（>300s）: {file_name}")

                        # 存储成功结果
                        result_json = json.dumps(result, ensure_ascii=False)
                        file_duration_ms = int((time.time() - file_start) * 1000)
                        self._tm.update_file_result(
                            task_id=task_id,
                            file_name=file_name,
                            status="success",
                            result_json=result_json,
                            timing_ms=file_duration_ms,
                        )
                        self._tm.increment_processed(task_id)
                        logger.info(
                            "[Worker] 文件处理成功 | file=%s | progress=%d/%d | duration_ms=%d",
                            file_name, idx + 1, total, file_duration_ms,
                        )

                    except Exception as e:
                        # 存储失败结果
                        file_duration_ms = int((time.time() - file_start) * 1000)
                        self._tm.update_file_result(
                            task_id=task_id,
                            file_name=file_name,
                            status="failed",
                            error_message=str(e),
                            timing_ms=file_duration_ms,
                        )
                        self._tm.increment_processed(task_id)
                        logger.error(
                            "[Worker] 文件处理失败 | file=%s | error=%s",
                            file_name, e,
                        )

                # 所有文件处理完成
                total_time_ms = int((time.time() - start_time) * 1000)
                # 标记完成（如果中途被取消，SQL WHERE 守卫会阻止覆盖，返回 False）
                if self._tm.mark_completed(task_id, total_time_ms):
                    logger.info(
                        "[Worker] 任务完成 | total_time_ms=%d", total_time_ms,
                    )
                else:
                    logger.info(
                        "[Worker] 任务未能标记完成（已被取消/失败）",
                    )

            except Exception as e:
                total_time_ms = int((time.time() - start_time) * 1000)
                self._tm.mark_failed(task_id, str(e))
                logger.error("[Worker] 任务异常 | error=%s", e)

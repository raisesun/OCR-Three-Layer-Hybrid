# H13 深度分析：VLMClient requests.Session 线程安全

- **分析日期**：2026-07-22
- **问题编号**：H13（审查报告 `docs/reviews/code_review_20260722.md`，🟠高）
- **状态**：未修复

---

## 1. 问题本质（一句话）

`VLMClient` 在 `__init__` 创建**单个 `requests.Session`**，而 `OCRService` 持有 `VLMClient` 单例，通过 `asyncio.to_thread` 在**线程池**中并发调用。`requests.Session` 官方不保证线程安全，多线程并发共享会导致**连接复用错误、响应串读**等偶发问题。

---

## 2. 事实链（代码层面，已逐行验证）

### 2.1 VLMClient 单 Session（external_services.py:55-57, 102）
```python
def __init__(self, config=None):
    self.config = config or VLMServiceConfig()
    self._session = self._create_session()   # ← 单个 Session 实例

def call(self, prompt, image_path, max_tokens=1024):
    ...
    # 用 self._session.post(...) 发请求（共享 Session）
```

### 2.2 OCRService 单例 + 线程池
- `service.py:96` `self._vlm_client = VLMClient(vlm_ocr_config)` -- **单例**
- API 层 `asyncio.to_thread(ocr_service.process_image, ...)`（`task_manager.py` TaskWorker.process_single）
- 多个请求并发 -> 多线程共享同一 `VLMClient` -> 共享同一 `self._session`

### 2.3 requests.Session 线程安全
- [requests 官方文档](https://docs.python-requests.org/en/latest/user/advanced/#session-objects)：**Session objects are not thread-safe**
- 并发使用同一 Session 可能：
  - 连接池竞争（同一连接被多线程复用）
  - 响应串读（A 的响应被 B 读到）
  - 偶发 `ConnectionError`/`ChunkedEncodingError`

---

## 3. 根因分析

### 3.1 为什么单 Session？
- 设计意图：复用连接池（性能），重试策略（Retry 配置在 Session 上）
- 单例 VLMClient + 单 Session = 连接池复用最大化

### 3.2 为什么不安全？
- `OCRService` 是单例（全局一个 VLMClient）
- API 层用 `asyncio.to_thread` 把同步 `process_image` 丢到线程池
- 线程池默认 ≤32 线程，多个请求并发 -> 多线程调 `VLMClient.call` -> 共享 `self._session`
- `requests.Session` 的连接池（urllib3）非线程安全

### 3.3 苏格拉底追问
- **Q：实际会并发吗？**
  -> 会。API 异步任务（`/api/v1/ocr/async`）多文件 + 多任务并发；每个文件 `process_single` 走 `asyncio.to_thread`。若启用 VLM 兜底，多线程并发调 `VLMClient.call`
- **Q：为什么没暴露？**
  -> VLM 调用相对低频（RULE 层优先，VLM 兜底才触发）；偶发错误被 `Retry` 重试掩盖；或单机测试并发少
- **Q：是 bug 还是设计？**
  -> 设计缺陷。单例 Session 适合单线程，不适合线程池并发

---

## 4. 批判性评估：严重性

agent 标 🟠高，**需分情况**：
- **触发条件**：多请求并发 + VLM 调用（VLM 兜底/UNKNOWN 提取）
- **实际概率**：取决于并发量 + VLM 调用频率。生产多用户并发时触发；单机测试少
- **影响**：偶发连接错误/响应串读 -> VLM 返回错误数据或失败。被 Retry 重试掩盖部分
- **隐蔽性**：偶发、难复现，可能表现为"VLM 偶尔返回错误"

**真实严重性**：🟡中（偶发 + Retry 部分掩盖 + VLM 低频）。但生产并发下风险升高。

---

## 5. 修复对整体系统的影响

### 5.1 正面影响
1. **消除并发不安全**：多线程并发 VLM 调用不再竞争 Session
2. **稳定性**：消除偶发连接错误/响应串读
3. **生产可靠**：多用户并发场景稳定

### 5.2 潜在风险
1. **连接池数量**：per-thread Session -> 每线程一个 Session（连接池）。线程池 ≤32 -> ≤32 Session。内存/连接数增加但可控
2. **重试策略**：每个 per-thread Session 需配置 Retry（复制 _create_session）
3. **close 时机**：per-thread Session 在线程结束时关闭？或复用？`threading.local` 线程局部
4. **测试**：`test_external_services.py` 需回归；并发测试难写（需多线程 mock）

### 5.3 影响范围
- **功能正确性**：消除偶发 VLM 错误（若触发）
- **性能**：per-thread Session 增加少量连接，但复用仍在（每线程内）
- **测试**：回归 `test_external_services.py`
- **部署**：无影响

---

## 6. 修复方案

### 方案 A：per-thread Session（threading.local）（推荐）
```python
import threading

class VLMClient:
    def __init__(self, config=None):
        self.config = config or VLMServiceConfig()
        self._local = threading.local()  # 线程局部

    def _get_session(self):
        """获取当前线程的 Session（延迟创建，每线程一个）"""
        session = getattr(self._local, "session", None)
        if session is None:
            session = self._create_session()
            self._local.session = session
        return session

    def call(self, prompt, image_path, max_tokens=1024):
        session = self._get_session()  # 用当前线程的 Session
        ...
        # response = session.post(...)
```
- 优点：每线程独立 Session，无竞争；复用 _create_session 逻辑
- 缺点：每线程一个 Session（连接数增加）；close 需处理

### 方案 B：加锁（Lock）
```python
self._lock = threading.Lock()
def call(self, ...):
    with self._lock:
        # session.post(...)
```
- 优点：简单、单 Session
- 缺点：串行化 VLM 调用（性能损失，VLM 慢，串行不可接受）

### 方案 C：每次 call 新建 Session
```python
def call(self, ...):
    with self._create_session() as session:
        session.post(...)
```
- 优点：无共享，最安全
- 缺点：无连接复用（性能损失）

---

## 7. 推荐方案

**方案 A（per-thread Session）**，理由：
1. **线程安全**：每线程独立 Session，无竞争
2. **保留复用**：每线程内连接复用（性能保留）
3. **复用 _create_session**：不重复重试策略配置
4. **性能可接受**：连接数增加但每线程复用；VLM 调用本身慢，Session 开销不显著

**实施要点**（external_services.py）：
- `__init__`：`self._local = threading.local()` 替代 `self._session`
- `_get_session()`：延迟创建 per-thread Session
- `call`：用 `self._get_session()` 替代 `self._session`
- `close`：需遍历清理（或依赖线程结束；per-thread Session 线程结束时由 GC 清理）

**注意**：`close()` 难清理所有 per-thread Session（threading.local 线程结束后 Session 被 GC）。可接受（连接池 finalize）。

---

## 8. 下一步行动

1. 按方案 A 修复（per-thread Session）
2. 回归 `test_external_services.py` + 加并发测试（多线程调 call，验证无竞争）
3. 可选：运行时验证（多请求并发，确认无偶发错误）

**优先级**：H13 是中优先级（偶发 + VLM 低频 + Retry 部分掩盖）。低于已修 26 项。生产并发场景值得修。

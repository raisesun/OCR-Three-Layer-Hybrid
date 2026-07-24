# H10 深度分析：UPLOAD_DIR 模块级 mkdtemp 资源泄漏

- **分析日期**：2026-07-22
- **问题编号**：H10（审查报告 `docs/reviews/code_review_20260722.md`，🟠高）
- **状态**：未修复

---

## 1. 问题本质（一句话）

`config.py` 模块级 `UPLOAD_DIR = Path(os.getenv("OCR_UPLOAD_DIR", tempfile.mkdtemp(...)))` 在**未设 `OCR_UPLOAD_DIR` 环境变量时，每次 import config 都创建一个新临时目录且永不清理**，导致 `/tmp` 下 `ocr_uploads_*` 目录堆积，磁盘资源泄漏。

---

## 2. 事实链（代码层面，已逐行验证）

### 2.1 问题代码（config.py:18-21）
```python
# 上传文件目录（统一常量）
# 优先使用环境变量 OCR_UPLOAD_DIR，否则使用临时目录
UPLOAD_DIR = Path(os.getenv("OCR_UPLOAD_DIR", tempfile.mkdtemp(prefix="ocr_uploads_")))
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
```

### 2.2 问题机制
- `tempfile.mkdtemp(prefix="ocr_uploads_")` 每次调用创建一个**新的唯一临时目录**（如 `/tmp/ocr_uploads_abc123`）
- `os.getenv("OCR_UPLOAD_DIR", <default>)`：未设环境变量时用 default = `mkdtemp()`，**每次 import 执行**
- 模块级代码：`import config` 时执行 line 20-21
- `mkdtemp` 创建的目录**永不自动清理**（需手动删）

### 2.3 触发场景
- **每次 Python 进程启动 import config**（未设 OCR_UPLOAD_DIR）-> 创建一个新 `ocr_uploads_*` 目录
- 应用重启、测试运行、脚本执行 -> 每次一个新目录
- 长期运行 -> `/tmp` 堆积大量 `ocr_uploads_*` 目录

---

## 3. 根因分析

### 3.1 为什么用 mkdtemp？
- 设计意图：未设 OCR_UPLOAD_DIR 时，用临时目录存上传文件，避免污染项目目录
- `mkdtemp` 创建唯一目录，避免并发冲突
- 但放在**模块级**（import 时执行），每次 import 都创建

### 3.2 为什么是问题？
1. **模块级副作用**：import config 触发 IO（创建目录），违反"导入无副作用"原则
2. **永不清理**：mkdtemp 创建的目录不自动删，进程退出后残留
3. **测试隔离**：每次测试 import config 创建不同目录，难以追踪上传文件
4. **磁盘泄漏**：长期运行堆积

### 3.3 苏格拉底追问
- **Q：为什么不清理？**
  -> mkdtemp 设计为"进程负责清理"，但 config 模块级创建后无清理逻辑
- **Q：为什么不用固定路径？**
  -> 可能担心并发冲突或权限。但固定路径 + exist_ok=True 已够（上传文件用 UUID 名）
- **Q：影响多大？**
  -> 每次启动一个目录（含上传文件）。高频重启/测试 -> 堆积。但单目录不大（上传文件），泄漏慢。属慢性资源泄漏
- **Q：是 bug 还是设计？**
  -> 设计缺陷。模块级 mkdtemp 不合适，应延迟初始化或用固定路径

---

## 4. 批判性评估：严重性

agent 标 🟠高，**我下调为 🟡中**：
- **磁盘泄漏**：每次启动一个目录，慢性泄漏（非爆发式）
- **功能影响**：无（上传功能正常，只是目录多）
- **测试影响**：隔离问题（测试难追踪），但现有测试用 tmp_upload_dir fixture 覆盖
- **生产影响**：长期运行堆积，但单目录小

属**中优先级**（慢性资源泄漏 + 模块级副作用），非紧急。但修复简单（1 行）。

---

## 5. 修复对整体系统的影响

### 5.1 正面影响
1. **消除磁盘泄漏**：固定路径，不再每次创建新目录
2. **消除模块级副作用**：import config 不触发 IO（用固定路径，mkdir 仍模块级但 exist_ok）
3. **测试一致性**：上传目录固定，可追踪
4. **符合原则**：导入无副作用

### 5.2 潜在风险
1. **并发冲突**：固定路径 + 多进程并发写上传文件？上传文件用 UUID 名（S5 修复后），不冲突
2. **权限**：`tempfile.gettempdir()` 通常是 `/tmp`，多用户系统权限？项目单机/容器，可接受
3. **环境变量覆盖**：保留 `OCR_UPLOAD_DIR` 环境变量（设了用环境变量，未设用固定 `/tmp/ocr_uploads`）
4. **测试**：`test_config.py` 可能引用 UPLOAD_DIR；现有 fixture `tmp_upload_dir` monkeypatch UPLOAD_DIR，不受影响

### 5.3 影响范围
- **功能正确性**：不变（上传目录仍可用）
- **资源**：消除磁盘泄漏
- **测试**：回归 `test_config.py`
- **部署**：上传目录从随机临时目录变为固定 `/tmp/ocr_uploads`（或 OCR_UPLOAD_DIR）

---

## 6. 修复方案

### 方案 A：固定路径（推荐）
```python
# 上传文件目录（统一常量）
# 优先环境变量 OCR_UPLOAD_DIR，否则用固定临时目录（避免每次 import mkdtemp 泄漏 H10）
UPLOAD_DIR = Path(os.getenv("OCR_UPLOAD_DIR", str(Path(tempfile.gettempdir()) / "ocr_uploads")))
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
```
- 优点：固定路径，无泄漏；保留环境变量覆盖
- 缺点：仍是模块级 mkdir（但 exist_ok，幂等）

### 方案 B：延迟初始化
```python
_UPLOAD_DIR = None
def get_upload_dir():
    global _UPLOAD_DIR
    if _UPLOAD_DIR is None:
        _UPLOAD_DIR = Path(os.getenv("OCR_UPLOAD_DIR", str(Path(tempfile.gettempdir()) / "ocr_uploads")))
        _UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    return _UPLOAD_DIR
```
- 优点：真正无模块级副作用
- 缺点：需改所有引用 UPLOAD_DIR 的地方为 get_upload_dir()，改动面大

### 方案 C：保留 mkdtemp + atexit 清理
- 缺点：清理逻辑复杂，进程崩溃仍残留

---

## 7. 推荐方案

**方案 A（固定路径）**，理由：
1. **最小改动**：1 行（mkdtemp -> 固定路径）
2. **消除泄漏**：固定 `/tmp/ocr_uploads`，不再每次新建
3. **保留覆盖**：OCR_UPLOAD_DIR 环境变量仍有效
4. **风险低**：上传文件用 UUID 名（S5），并发不冲突

**实施要点**（config.py:20）：
```python
UPLOAD_DIR = Path(os.getenv("OCR_UPLOAD_DIR", str(Path(tempfile.gettempdir()) / "ocr_uploads")))
```

**注意**：仍模块级 mkdir（exist_ok 幂等）。若要彻底无副作用，方案 B，但改动大。

---

## 8. 下一步行动

1. 按方案 A 修复（1 行）
2. 回归 `test_config.py`
3. 可选：加测试验证 UPLOAD_DIR 固定（多次 import 一致）

**优先级**：H10 是中优先级（慢性泄漏 + 副作用）。修复简单、低风险。可立即修。

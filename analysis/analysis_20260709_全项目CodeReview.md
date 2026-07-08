# 全项目 Code Review 记录

> **日期**: 2026-07-09
> **范围**: ~11,500 行 Python 代码，2 个包（`ocr_three_layer_hybrid` + `ocr_api`），28 个源文件
> **方法**: 3 个并行 reviewer — 核心库正确性 / API 安全与逻辑 / 代码质量与架构
> **状态**: 🔴 待修复 | 🟡 已修复

---

## 🔴 CRITICAL — 11 个

### #1 多页文档所有页复用首页分类
- **文件**: `src/ocr_three_layer_hybrid/service.py:545`
- **问题**: `_extract_multi_page_merge` 中所有页使用首页的 `doc_info`，户口本/结婚证等多页文档内容页全部按封面类型处理
- **影响**: 内容页返回空字段
- **修复状态**: 🔴 待修复

### #2 已取消任务被覆盖为 completed（竞态）
- **文件**: `src/ocr_api/common/task_manager.py:153,473`
- **问题**: `mark_completed()` 不检查当前状态，取消后 worker 完成时会覆盖为 completed
- **影响**: API 返回"已取消"但查询变"已完成"
- **修复状态**: 🔴 待修复

### #3 mark_failed() 丢弃 error_message
- **文件**: `src/ocr_api/common/task_manager.py:187-196`
- **问题**: 方法接收 `error_message` 参数但 SQL 未写入，tasks 表无此列
- **影响**: 所有失败任务 error 字段为 null
- **修复状态**: 🔴 待修复

### #4 PIL Image 文件句柄泄漏
- **文件**: `src/ocr_three_layer_hybrid/position_extractor.py:146`
- **问题**: `Image.open()` 无 `with` 或 `close()`
- **影响**: 批量处理数百张 → `OSError: [Errno 24] Too many open files`
- **修复状态**: 🔴 待修复

### #5 ThresholdsConfig 完全死代码
- **文件**: `src/ocr_three_layer_hybrid/config.py:64-87`
- **问题**: 定义了 10 个阈值但无任何代码读取，classifier 用硬编码常量
- **影响**: 修改配置无效果
- **修复状态**: 🔴 待修复

### #6 IMAGE_EXTENSIONS 两处定义不一致
- **文件**: `service.py:92`（无 .pdf） vs `routes/ocr.py:26`（有 .pdf）
- **问题**: core 和 API 各自定义，值不同
- **影响**: `process_directory()` 静默跳过 PDF
- **修复状态**: 🔴 待修复

### #7 ProcessingLayer.LLM 枚举残留
- **文件**: `src/ocr_three_layer_hybrid/interfaces.py:89`
- **问题**: LLM 层已移除但枚举值还在
- **影响**: 路由到 LLM 时静默无结果
- **修复状态**: 🔴 待修复

### #8 JSON 解析逻辑重复
- **文件**: `vlm_layer.py:822-893` + `vlm_fallback.py:200-233`
- **问题**: 两处各实现一遍 3 层 JSON fallback 解析
- **影响**: 修一处忘另一处导致行为不一致
- **修复状态**: 🔴 待修复

### #9 UI 元数据泄漏到 core 库
- **文件**: `src/ocr_three_layer_hybrid/service.py:33-89`
- **问题**: `PIPELINE_STAGES`/`LAYER_COLORS`/`ROUTE_NAMES` 是前端关注点，不应在纯 OCR 库中
- **影响**: core 库无法独立演进
- **修复状态**: 🔴 待修复

### #10 死代码
- **文件**: `text_preprocessor.py:234` (`FieldExtractorEnhancer`)、`classifier.py:991` (`_group_keywords`)、`vlm_health_checker.py`（全文件）
- **问题**: 从未被导入或调用
- **修复状态**: 🔴 待修复

### #11 硬编码 macOS 路径
- **文件**: `config.py:34,59`、`baseline_service.py:13`
- **问题**: `/Users/dongsun/Github/models-OCR/...` 只在一台机器可用
- **修复状态**: 🔴 待修复

---

## 🟠 HIGH — 16 个

### #12 CORS 全开
- **文件**: `src/ocr_api/ocr/server.py:101-106`
- **问题**: `allow_origins=["*"]`，任何网站可跨域调用
- **修复状态**: 🔴 待修复

### #13 TOCTOU 竞态 — cancel 端点
- **文件**: `src/ocr_api/ocr/routes/task.py:80-96`
- **问题**: 先查状态再更新，中间可被并发修改
- **修复状态**: 🔴 待修复

### #14 文件泄漏 — 批量上传校验失败
- **文件**: `src/ocr_api/ocr/routes/ocr.py:84-115`
- **问题**: 第 30 个文件校验失败，前 29 个已写文件不清理
- **修复状态**: 🔴 待修复

### #15 SQLite 连接永不关闭
- **文件**: `src/ocr_api/common/task_manager.py:58-65`
- **问题**: 线程本地连接无 close/shutdown hook
- **修复状态**: 🔴 待修复

### #16 get_quota() 跨租户泄漏
- **文件**: `src/ocr_api/common/task_manager.py:369`
- **问题**: pending 任务计数查询无 api_key 过滤
- **修复状态**: 🔴 待修复

### #17 调试路由路径遍历
- **文件**: `src/ocr_api/ocr/debug_routes.py:129-168`
- **问题**: 接受任意文件系统路径，无目录限制
- **修复状态**: 🔴 待修复

### #18 PaddleOCR 初始化非线程安全
- **文件**: `position_extractor.py:117` / `service.py:248`
- **问题**: check-then-act 竞态，可双重初始化
- **修复状态**: 🔴 待修复

### #19 VLMClient HTTP session 永不关闭
- **文件**: `src/ocr_three_layer_hybrid/external_services.py:46`
- **问题**: `requests.Session` 无 close/`__del__`/上下文管理器
- **修复状态**: 🔴 待修复

### #20 CJK Unicode 范围不一致
- **文件**: 多个 extractor
- **问题**: `[一-龥]`(U+4E00–U+9FA5) vs `[一-鿿]`(U+4E00–U+9FCF)
- **修复状态**: 🔴 待修复

### #21 ~500 行 prompt 内联在代码中
- **文件**: `src/ocr_three_layer_hybrid/vlm_layer.py:76-558`
- **问题**: 18 个 prompt 模板硬编码为类变量，调 prompt 要改代码
- **修复方案**: 方案 B — 提取到 `prompt_templates.py` + 公共后缀组合
  - 创建 `src/ocr_three_layer_hybrid/prompt_templates.py`
  - 提取 `COMMON_SUFFIX`（消除 18 处重复的注意事项）
  - 18 个 prompt 移到新文件，只保留「角色 + 字段 + 说明」
  - 创建 `build_prompt()` 组合 template + suffix
  - vlm_layer.py `_build_prompt()` 调用新函数
  - 预期效果：vlm_layer.py 从 893 行 → ~410 行
- **修复状态**: 🟡 已修复（2026-07-09）
  - 新建 `src/ocr_three_layer_hybrid/prompt_templates.py`（506 行）
  - `vlm_layer.py` 从 895 行降至 406 行
  - `COMMON_SUFFIX` 消除 18 处重复注意事项
  - `_build_prompt()` 使用 `build_prompt()` + `.name` 查找
  - 109 测试通过，无回归

### #22 ~250 行字段配置硬编码
- **文件**: `src/ocr_three_layer_hybrid/pipeline.py:41-338`
- **问题**: `DEFAULT_KEY_LISTS`  giant dict 硬编码
- **修复状态**: 🔴 待修复

### #23 classifier.py 1014 行，7 个重复 stage 方法
- **文件**: `src/ocr_three_layer_hybrid/classifier.py`
- **问题**: 7 个 `_check_*` 方法结构几乎相同，可数据驱动简化
- **修复状态**: 🔴 待修复

### #24 多页合并逻辑重复
- **文件**: `service.py:514-621` + `vlm_layer.py:646-739`
- **问题**: 两处各实现一遍 iterate→extract→merge
- **修复状态**: 🔴 待修复

### #25 签发机关/有效期限 regex 重复
- **文件**: `src/ocr_three_layer_hybrid/extractors/personal_id_extractor.py`
- **问题**: with_labels 和 without_labels 路径各写一遍相同逻辑
- **修复状态**: 🔴 待修复

### #26 日志 f-string 混用（47 处）
- **文件**: 多个文件
- **问题**: `logger.info(f"...")` 总是求值，应统一用 `%` 格式
- **修复状态**: 🔴 待修复

### #27 所有错误返回 HTTP 200
- **文件**: `routes/ocr.py`、`routes/task.py` 等
- **问题**: `APIResponse(code=400/404/500)` 但 HTTP 状态码始终 200
- **影响**: 监控/负载均衡器无法识别失败
- **修复状态**: 🔴 待修复

---

## 🟡 MEDIUM — 11 个

### #28 VLM JSON fallback regex 无法匹配嵌套对象
- **文件**: `src/ocr_three_layer_hybrid/vlm_layer.py:860`
- **问题**: `[^{}]*` 排除花括号，只能匹配扁平 JSON
- **修复状态**: 🔴 待修复

### #29 DOTALL regex 可跨越两个人边界
- **文件**: `src/ocr_three_layer_hybrid/extractors/personal_id_extractor.py:528`
- **问题**: `(?:.*?)?` 可跨行匹配到第二个人
- **修复状态**: 🔴 待修复

### #30 户口本空白页检查过于激进
- **文件**: `src/ocr_three_layer_hybrid/extractors/household_property_extractor.py:38`
- **问题**: 无身份证号就返回空 dict，丢弃其他已提取字段
- **修复状态**: 🔴 待修复

### #31 6 个模块零单元测试
- **文件**: `vlm_fallback.py`、`service.py`、`text_preprocessor.py`、`external_services.py`、`image_preprocessor.py`、`vlm_health_checker.py`
- **修复状态**: 🔴 待修复

### #32 _cancel_flags 字典无限增长
- **文件**: `src/ocr_api/common/task_manager.py:52`
- **问题**: 每个取消任务加一条，永不清理
- **修复状态**: 🔴 待修复

### #33 get_quota() 每次全量扫描文件系统
- **文件**: `src/ocr_api/common/task_manager.py:375`
- **问题**: 递归 `stat()` 所有上传文件，阻塞事件循环
- **修复状态**: 🔴 待修复

### #34 verify_api_key 每请求重建 authenticator
- **文件**: `src/ocr_api/common/auth.py:155-164`
- **问题**: FastAPI 依赖函数每次创建新实例
- **修复状态**: 🔴 待修复

### #35 模块级单例无法测试
- **文件**: `src/ocr_api/ocr/server.py:83-86`
- **问题**: import 时即创建 OCRService 等，无法注入 mock
- **修复状态**: 🔴 待修复

### #36 hasattr 做懒初始化
- **文件**: `src/ocr_three_layer_hybrid/service.py:248`
- **问题**: 属性首次调用前不存在，IDE/类型检查器无法追踪
- **修复状态**: 🔴 待修复

### #37 DEFAULT_SUPPORTED_TYPES 重复整个枚举
- **文件**: `src/ocr_three_layer_hybrid/vlm_layer.py:30-67`
- **问题**: 37 项列表重复 DocumentType 枚举
- **修复状态**: 🔴 待修复

### #38 UPLOAD_DIR 两处定义不同
- **文件**: `routes/ocr.py:22`（硬编码 `/tmp/ocr_uploads`）vs `server.py:89`（tempfile）
- **修复状态**: 🔴 待修复

---

## 修复记录

> 修复后将对应编号的状态从 🔴 改为 🟡，并记录修复日期和方式。

| 编号 | 修复日期 | 修复方式 | 备注 |
|------|----------|----------|------|
| #21 | 2026-07-09 | 方案 B：提取 prompt_templates.py + 公共后缀 | ✅ vlm_layer.py 895→406 行，109 测试通过 |
| — | — | — | 其他编号等待用户确认修复顺序 |

---

## 验证通过项（无问题）

- SQL 注入：所有查询使用参数化 `?` 占位 ✅
- Auth bypass：`OCR_API_KEYS` 为空时正确拒绝所有请求 ✅
- 文件名路径遍历：UUID 重命名防止此问题 ✅
- SQLite 线程安全：异步代码在事件循环线程执行，线程本地连接正确 ✅

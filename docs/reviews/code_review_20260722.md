# OCR 三层混合架构 - 全量代码审查报告

- **审查日期**：2026-07-22
- **审查范围**：整个项目（核心包 `src/ocr_three_layer_hybrid/` 7438 行 + API 服务 `src/ocr_api/` 2721 行 + 前端 2101 行，共约 12000 行）
- **审查维度**：全面审查（正确性 + 架构 + 安全 + 规范）
- **审查方法**：5 个审查 agent 分模块并行审查 → 主审对最严重发现逐行验证（标注 ✅ 已验证）
- **严重程度**：🔴严重（安全漏洞/崩溃/数据错误） 🟠高 🟡中 🟢低

## 总体评价

核心 OCR 逻辑（RULE+VLM 两层架构、字段级兜底、JSON 解析容错、prompt 集中管理）设计合理，工程质量中等偏上。但存在**多处严重安全漏洞**（集中在 `debug_routes.py` 与 `task_manager.py`）和**若干正确性/性能 bug**。最紧迫的是：API 层的 IDOR 越权、调试路由零鉴权暴露、路径遍历、API Key 日志泄露——这些在生产环境会导致数据泄露与服务被接管。

**问题统计**：🔴严重 9 项｜🟠高 21 项｜🟡中 30+ 项｜🟢低 20+ 项

---

## 🔴 严重问题（建议立即修复）

### S1. IDOR 越权：任意认证用户可查询/取消他人任务 ✅已验证
- **位置**：`src/ocr_api/ocr/routes/task.py:98,128,136`；根因 `src/ocr_api/common/task_manager.py:437,199`
- **问题**：`get_task_status` / `cancel_task` 路由虽调用 `authenticator.verify(request)` 拿到 `api_key`，但查询/取消时完全不校验任务归属：
  ```python
  # task.py:98
  status = task_manager.get_task_status(task_id)   # 不传 api_key
  # task_manager.py:437 def get_task_status(self, task_id)  # 无 api_key 参数
  # task_manager.py:199 SELECT * FROM tasks WHERE id = ?     # 无 api_key 过滤
  ```
  `list_tasks` 有 api_key 过滤，但单任务查询/取消没有。
- **影响**：租户 A 用枚举/泄露的 task_id 可读取租户 B 的全部 OCR 结果（含证件字段等敏感数据），或恶意取消他人任务。违反多租户隔离。
- **修复**：`get_task`/`get_task_status`/`mark_cancelled` 增加 `api_key` 参数，SQL 加 `WHERE id = ? AND api_key = ?`，归属不匹配返回 404（避免枚举探测）。

### S2. 调试路由零鉴权 + 绑定 0.0.0.0，可操纵任意生产任务 ✅已验证
- **位置**：`src/ocr_api/ocr/server.py:224`（`host="0.0.0.0"`）；`src/ocr_api/ocr/debug_routes.py` 全文
- **问题**：`DEBUG=true` 时加载的 `/api/debug/*`、`/api/upload`、`/api/process*`、`/api/baseline/*`、`/api/stats/*` 路由均无 `authenticator.verify(request)`。`debug_get_task`/`debug_cancel_task` 按 task_id 直接操作，**不区分 debug 任务与生产任务**。
- **影响**：生产环境若误开 `DEBUG=true`，未认证攻击者可：读取/取消任意生产任务、读取全部运行日志、上传任意文件、提交无限任务、触发全量基线处理。
- **修复**：(1) `server.py` 默认 `host="127.0.0.1"`；(2) debug 路由加 IP 白名单或独立鉴权；(3) `debug_get_task`/`debug_cancel_task` 校验 `task["api_key"] == "debug-demo-key"` 拒绝非 debug 任务；(4) 部署文档明确禁止生产 `DEBUG=true`。

### S3. 路径遍历：`startswith` 前缀校验可被绕过 ✅已验证
- **位置**：`src/ocr_api/ocr/debug_routes.py:94-97`（`_validate_path`）；同文件 `list_directories` 同理
- **问题**：
  ```python
  if not any(str(resolved).startswith(str(base)) for base in _allowed_bases):
      raise HTTPException(403, ...)
  ```
  `str.startswith` 不尊重路径边界。基目录 `/Users/dongsun/Github/sample-OCR`，则 `/Users/dongsun/Github/sample-OCR-backup/private.jpg`、`sample-OCR2`、`sample-OCR.evil` 均通过校验。
- **影响**：攻击者可读取/处理白名单目录同父级下任意同前缀目录的文件。
- **修复**：改用 `Path.relative_to()` / `is_relative_to()`（Python 3.9+）：
  ```python
  if not any(resolved.is_relative_to(base) for base in _allowed_bases):
      raise HTTPException(403, ...)
  ```

### S4. 完整 API Key 写入日志 + 明文存储 ✅已验证
- **位置**：`src/ocr_api/common/task_manager.py:196`
- **问题**：
  ```python
  logger.info("[TaskManager] 创建任务 | id=%s | files=%s | api_key=%s", task_id, file_count, api_key)
  ```
  路由层已脱敏（`f"{api_key[:8]}..."`），但 `create_task` 写完整 api_key。`record_api_call` 也明文存入 `api_usage` 表。日志经 `memory_log.py` 的 `MemoryLogHandler` 捕获，DEBUG 时 `/api/debug/logs` 无鉴权返回。
- **影响**：API Key 泄露 → 攻击者冒充任意租户调用正式 API。
- **修复**：`create_task` 内脱敏；`api_usage` 表存 SHA-256 哈希而非明文。

### S5. `/uploads` 静态挂载无鉴权 + 上传无校验 = 存储型 XSS + 隐私泄露 ✅已验证
- **位置**：`src/ocr_api/ocr/debug_routes.py:348-364`（upload）、`503`（StaticFiles 挂载）；`server.py:189`
- **问题**：上传不校验扩展名/大小，文件名 `upload_{timestamp}{suffix}` 高度可预测，且通过 `StaticFiles` 直接按扩展名设 Content-Type 服务。攻击者上传 `evil.html`（含 `<script>`），经 `/uploads/evil.html` 在站点 origin 下执行。
- **影响**：存储型 XSS（窃取日志中的 API Key、操作任务）；任何人可枚举时间戳访问他人上传的证件图片。
- **修复**：(1) 扩展名白名单 + 大小限制；(2) 文件名用 UUID；(3) StaticFiles 强制 `Content-Disposition: attachment` 或改用 API 接口读取；(4) `/uploads` 加鉴权。

### S6. `asyncio.create_task` 引用未保存，任务可被 GC 回收且异常静默丢失 ✅已验证
- **位置**：`src/ocr_api/ocr/routes/ocr.py:152`；`src/ocr_api/ocr/debug_routes.py:411`
- **问题**：
  ```python
  asyncio.create_task(worker.process(task_id, saved_files))  # 引用未保存
  ```
  事件循环对 task 仅持弱引用，GC 可能中途回收。更严重：`worker.process` 中 `mark_processing` 在 try 块外，若抛异常（如 SQLite 锁），task 永远停在 `pending`。
- **影响**：大批量任务可能中途消失；异常导致任务永久 `pending`，用户无限轮询。
- **修复**：维护 `self._background_tasks: set`，`task.add_done_callback(set.discard)`；`mark_processing` 移入 try 或加外层 try/except + `mark_failed` 兜底。

### S7. debug 异步上传无任何文件限制，磁盘/内存耗尽 DoS ✅已验证
- **位置**：`src/ocr_api/ocr/debug_routes.py:368-424`
- **问题**：不校验文件数量、单文件大小、扩展名，`content = await f.read()` 全量读入内存。对比正式路由 `routes/ocr.py` 有 500 文件/20MB/扩展名校验。
- **影响**：未认证用户上传任意数量/大小/类型文件，耗尽磁盘内存；可上传可执行脚本经 `/uploads` 访问。
- **修复**：复用 `submit_async_task` 的校验逻辑。

### S8. `text_det_limit_side_len=64` 疑似严重错误参数，破坏 OCR 检测 ✅已验证
- **位置**：`src/ocr_three_layer_hybrid/paddleocr_wrapper.py:435`
- **问题**：`PaddleOCREngine.__init__` 默认 `text_det_limit_side_len: int = 64`，传入 `_init_kwargs` 并最终传给 `PaddleOCR(...)`。PaddleOCR 标准值为 `960`（须为 32 的倍数）。设为 64 意味着检测前图像长边缩到 64 像素，文本几乎无法检出。该引擎是生产路径引擎（`service.py` `default_engine="ppocr"`）。
- **影响**：若参数实际生效，PP-OCRv6 文本检测几乎失效，所有依赖坐标的位置标注提取和规则提取返回空，被迫降级 VLM 兜底，整体性能与准确率严重下降。
- **修复**：改为 `960`（或 `768`），加注释说明。**需运行时验证 64 是否实际生效**（若系统当前识别正常，可能被 PaddleOCR 忽略或被别处覆盖，但 64 仍是必须修正的错误值）。

### S9. baseline/compare 与 stats/dashboard 无限流，CPU 耗尽型 DoS
- **位置**：`src/ocr_api/ocr/debug_routes.py:234-289`、`293-344`
- **问题**：两接口对全部基线图片跑完整 OCR+VLM pipeline（数十秒/次），无并发限制、无缓存、无速率限制。
- **影响**：并发调用占满 CPU，正常用户无法使用。
- **修复**：加结果缓存 + `asyncio.Semaphore(1)` + 请求频率限制。

---

## 🟠 高优先级问题

### H1. 多页处理每页 OCR 两次，性能浪费翻倍 ✅已验证
- **位置**：`src/ocr_three_layer_hybrid/service.py:378,519,587`
- **问题**：首页 line 378 OCR（分类）；后续页 line 519 OCR（分类）；**所有页** line 587 又 OCR（提取）。同一图被同引擎 OCR 两次，结果相同。
- **影响**：PP-OCRv6 约 41.5s/张，15 页文档浪费 600+ 秒，批量场景性能翻倍损失。
- **修复**：`extract_page` 闭包内每页只 OCR 一次，分类与提取共用文本；首页复用 line 378 结果。

### H2. 合同签章页误判：通用词导致内容页被跳过提取（数据丢失）
- **位置**：`src/ocr_three_layer_hybrid/classifier.py:434-459`
- **问题**：`_detect_contract_page_type` 中 `has_stamp_signals` 用 `"签字"`、`"盖章"`、`"签章"` 等极通用词，且 STAMP 优先级最高。合同内容页/首页常含"签字盖章"条款会被误判为签署页。
- **影响**：被误判为 STAMP 的内容页在 `rule_layer.py:205-212` 返回空字段，**字段丢失**。
- **修复**：收紧 STAMP 信号——要求"签字/盖章"+"合同签订日期/地址"等签署页独有特征同时命中，而非任一命中。

### H3. 单图路径 RULE 层异常不触发 VLM 字段级兜底 ✅已验证
- **位置**：`src/ocr_three_layer_hybrid/pipeline.py:253`
- **问题**：`if self.vlm_fallback_handler and result.success:` 仅 success=True 时触发兜底。但 `rule_layer.extract` 异常时返回 `success=False`，此时字段全空却不兜底。与多页路径（service.py:605 无论 success 都检查必填字段）不一致。
- **修复**：放宽为 `if self.vlm_fallback_handler:`，由 `get_failed_fields` 内部判断（_apply_vlm_fallback 已有类型白名单限制）。

### H4. 单图与多页使用两套不一致的 VLM 兜底实现 ✅已验证
- **位置**：`pipeline.py:282-324`（用 `vlm_fallback_handler.fallback_extract`，只提取失败字段）vs `service.py:698-721`（直接用 `vlm_layer.extract` 提取所有字段，且访问 `pipeline._get_layer` 私有方法）
- **影响**：同文档单图/多页模式 VLM 兜底行为、prompt、结果可能不同，难复现与回归。
- **修复**：统一为一条路径，多页也走 `pipeline._apply_vlm_fallback`，避免访问私有方法。

### H5. position_extractor 重复创建独立 PaddleOCR 实例
- **位置**：`src/ocr_three_layer_hybrid/position_extractor.py:127`
- **问题**：`HouseholdPositionExtractor._get_ocr` 直接 `PaddleOCR(lang="ch")`，用默认模型/参数；而 `paddleocr_wrapper.py` 用 PP-OCRv6_medium 自定义参数。系统同时加载两个实例，双倍内存，模型版本可能不同导致坐标不一致。
- **修复**：将 `PaddleOCREngine` 实例注入复用。

### H6. VLM 响应双重 JSON 解析 + 模糊匹配误分类
- **位置**：`src/ocr_three_layer_hybrid/vlm_layer.py:108-172`
- **问题**：(1) `extract()` 对同一 `vlm_response` 两次调用 `parse_json_from_response`；(2) line 169-172 `if vlm_doc_type_str in dt.value or dt.value in vlm_doc_type_str` 极宽松，VLM 返回 `"证"` 会匹配到第一个含"证"的类型。
- **修复**：解析结果复用；模糊匹配加最小长度约束并按匹配长度排序，或去掉 `in` 包含匹配。

### H7. HUKOU_KEY_MAPPINGS 在 UNKNOWN 嵌套格式路径下不生效
- **位置**：`src/ocr_three_layer_hybrid/vlm_layer.py:385-391`
- **问题**：检测到 `{"fields": {...}}` 嵌套格式时直接复制键值并 `return`，跳过 line 394-403 的键名映射。UNKNOWN 实为户口本时，`户主`→`户主姓名` 映射不执行，字段丢失。
- **修复**：嵌套路径也应用键名映射。

### H8. 多引擎对 PaddleOCR 结果 API 访问方式不一致 ✅已验证
- **位置**：`paddleocr_wrapper.py:631`（`res.get(...)` dict 方法）vs `:787`（`res.json` 对象属性）vs `position_extractor.py:155`（`r["rec_boxes"]` 下标）
- **问题**：三处访问方式不一致。若 PaddleOCR 3.x `predict()` 返回对象而非 dict，`res.get()` 抛 AttributeError。
- **修复**：统一访问方式（`res.json if hasattr(res,'json') else res`）。**需运行时确认各引擎返回类型**——两引擎用不同 pipeline，可能各自正确，但仍应统一防御式写法。

### H9. 字间空格移除逻辑可能合并同行多个字段
- **位置**：`src/ocr_three_layer_hybrid/text_preprocessor.py:100-141`
- **问题**：判定为"字间空格模式"后 `re.sub(r"\s+", "", line)` 移除所有空格。若同行多字段都呈字间空格模式（如 `合 同 编 号 ： 2 0 2 4 买 方 ： 张 三`），字段被错误合并。
- **修复**：只移除单字符部分间空格，多字符部分边界保留空格。

### H10. UPLOAD_DIR 模块级 `mkdtemp` 资源泄漏
- **位置**：`src/ocr_three_layer_hybrid/config.py:20-21`
- **问题**：未设 `OCR_UPLOAD_DIR` 时，每次 import 都 `tempfile.mkdtemp` 创建新目录且永不清理，模块级副作用。
- **修复**：延迟初始化或用固定路径 `Path(tempfile.gettempdir())/"ocr_uploads"`。

### H11. cv2.imwrite 返回值未检查 ✅
- **位置**：`image_preprocessor.py:404`
- **问题**：`cv2.imwrite` 返回 bool，失败不抛异常。当前不检查直接返回路径，磁盘满/权限不足时下游拿到不存在文件。
- **修复**：检查返回值，失败时返回原路径并记日志。

### H12. 临时文件命名冲突
- **位置**：`image_preprocessor.py:136,401`
- **问题**：`resized_{filename}` / `enhanced_{filename}` 仅用文件名，不同目录同名图片互相覆盖。
- **修复**：加 UUID/哈希前缀。

### H13. VLMClient 的 requests.Session 多线程不安全
- **位置**：`external_services.py:49-66`；使用方 `service.py:96`（单例）+ `asyncio.to_thread` 线程池共享
- **问题**：`requests.Session` 官方不保证线程安全，并发下可能出现连接复用错误、响应串读。
- **修复**：per-thread Session（`threading.local()`）或加锁。

### H14. 图像无 Decompression Bomb 防护
- **位置**：`image_preprocessor.py:58,118,380`；`external_services.py:30`
- **问题**：`Image.open`/`cv2.imread` 无大小预检查，`encode_image_base64` 全量读入内存。恶意超大图致 OOM。
- **修复**：入口校验文件大小，设 `Image.MAX_IMAGE_PIXELS` 上限并检查 `img.size`。

### H15. 并发信号量定义后从未使用，`max_concurrent` 形同虚设
- **位置**：`task_manager.py:53`
- **问题**：`self._semaphore = asyncio.Semaphore(max_concurrent)` 创建后从不 acquire/release，每个提交立即 `create_task`。
- **修复**：`TaskWorker.process` 开头 `async with self._tm._semaphore:`。

### H16. 正式异步上传无总大小限制，全部读入内存
- **位置**：`routes/ocr.py:82-101`
- **问题**：文档声明"总大小 ≤ 500MB"，但只校验单文件 20MB，500×20MB=10GB 全 `await f.read()` 入内存。
- **修复**：读取前用 `f.size` 预检总大小，或流式分块校验。

### H17. 同名文件结果互相覆盖
- **位置**：`task_manager.py:310-329`；`routes/ocr.py:115`
- **问题**：`file_name` 存原始名，`update_file_result` 的 `WHERE task_id=? AND file_name=?` 会覆盖所有同名行。
- **修复**：用自增序号或 `file_path`（唯一）作更新条件，或存生成的 `safe_name`。

### H18. 无任务超时机制，OCR 挂起致永久 processing
- **位置**：`task_manager.py:593-679`
- **问题**：`process_single` 经 `asyncio.to_thread` 无超时，OCR 卡死则任务永久 processing。
- **修复**：`asyncio.wait_for(..., timeout=300)`，超时标记该文件 failed。

### H19. `_cancel_flags` 内存泄漏
- **位置**：`task_manager.py:262,241,285`
- **问题**：`mark_cancelled` 设 flag，仅 `mark_completed`/`mark_failed` pop。pending 状态取消的任务永不清理。
- **修复**：`mark_cancelled` 成功后也 pop。

### H20. debug 路由任务跨租户：硬编码 `"debug-demo-key"` 无隔离
- **位置**：`debug_routes.py:394,435`
- **问题**：所有 debug 任务关联同一 api_key，`list_tasks` 按此 key 过滤；`debug_get_task`/`debug_cancel_task` 不检查归属。
- **修复**：生成临时会话 ID 隔离，或校验任务归属。

### H21. `get_quota` 月末 23 点必崩 ✅已验证
- **位置**：`task_manager.py:538-540`
- **问题**：`replace(day=reset_at.day + 1)` 月末越界，`datetime(2026,1,31,23).replace(day=32)` 抛 ValueError。每月最后一天 23:00-24:00 `/api/v1/quota` 必 500。
- **修复**：`reset_at = hour_start + timedelta(hours=1)`。

---

## 🟡 中优先级问题（简列）

**核心包-分类管道**
- `service.py:42-68` setup_logging 重复添加 handler（日志重复输出）
- `classifier.py:80-130` BACKUP_CERTIFICATE_SIGNALS/ADDITIONAL_BACKUP_SIGNALS 类属性是死代码（实际用函数内局部变量）
- `rule_layer.py:112-125 vs 146-157` STAMP 类型在跳过列表和提取分支重复（elif 死代码）
- `service.py:752-754` process_batch 附属页面 VLM 判断死代码（v2.1 已移除 VLM 分类）
- `pipeline.py:132-133` 浅拷贝致类属性 value 共享引用（暂只读，潜在污染）
- `rule_layer.py:127-135` 封面/盖章页 `success=True`+`error_message` 语义混乱
- `classifier.py:367-377` property certificate content_count 1-2 时返回 UNKNOWN（应返回 CONTENT）
- `classifier.py:194-201` `custom_rules` 参数被忽略（误导）
- `rule_layer.py:100-236` extract 方法 130+ 行 20+ 分支，圈复杂度过高

**核心包-VLM/OCR 引擎**
- `vlm_fallback.py:15,122` 默认配置指向 GLM-OCR(8080) 与文档(Qwen 8082)不符
- `vlm_fallback.py:124-125` 统计计数器非线程安全
- `paddleocr_wrapper.py:312-317` 图片预处理仅 PPStructureV3 引擎有，其他引擎缺大图防护
- `vlm_layer.py:86-192` extract() 圈复杂度过高，别名字典方法内重建
- `paddleocr_wrapper.py:831,980` 无 `__enter__`/`__exit__`，资源易泄漏
- `position_extractor.py:94-99` 硬编码坐标范围仅适配特定样本
- `paddleocr_wrapper.py:576-583` _group_texts_by_regions 排序 key 阅读顺序风险

**核心包-字段/基础设施**
- `external_services.py:122` VLM 硬编码 `image/jpeg` MIME，非 JPEG 图片可能解码异常
- `field_validator.py:100` "与户主关系"枚举过严（三子/养子/儿媳等合法值被拒，触发不必要 VLM 兜底）
- `config.py:46,71` api_key 字段死配置（VLMClient 从未用）
- `field_validator.py:264-271` 住址特殊校验硬编码在 validate()，违反开闭原则
- `field_validator.py:70` VALIDATION_RULES 类级可变 dict 实例间共享
- `interfaces.py:102-104` should_extract() 与 field_config skip=True 语义不一致（STAMP/ATTACHMENT）
- `field_config.py:40-46` FieldConfig 可变但有 __hash__，hash 契约风险
- `image_preprocessor.py:89` resize_image 对非 JPEG 忽略 quality 参数

**API 层**
- `debug_routes.py:71, baseline_service.py:13, app.js:242` 硬编码本机绝对路径（泄露目录结构+不可移植）
- `routes/ocr.py:46-47` enable_vlm/callback_url/priority 参数被接受但静默忽略
- `server.py:212` `app.dependency_overrides` 判断认证状态错误（始终打印"未配置"）
- `health.py:43` 健康检查 `pp_ocr="ok"` 硬编码，不实际检查引擎
- `task_manager.py:521-529` record_api_call 每请求一次 DB 写，api_usage 表无限增长
- `server.py:150-158` CORS 可经环境变量设为 `*`
- `auth.py:41-91` 无 API Key 暴力破解防护/限流
- `debug_routes.py:489-494` `/api/debug/logs/clear` POST 无鉴权无 token，CSRF 风险
- `debug_routes.py:126, routes/ocr.py:128` 异常 `str(e)` 直接返回客户端，泄露内部信息
- `routes/ocr.py:45,134` callback_url 无校验，未来实现回调则 SSRF
- `server.py:75, task_manager.py:48` SQLite 默认 `/tmp/ocr_tasks.db`，多用户系统可读

**前端**
- `app.js:242` buildBreadcrumb 硬编码 `/Users/dongsun/Github/sample-OCR`
- `charts.js:43,95` 通过 Alpine 内部属性 `__x` 读数据，版本脆弱
- `index.html:13-14` x-effect 切回 async Tab 重置分页到第 1 页
- `index.html:123,193,201` 数据不完整时显示 `NaN%`/`undefinedms`
- `app.js:122-131` handleFileSelect 不校验文件类型（与 handleDrop 不一致）
- `app.js:418-448` 异步任务无客户端文件数量/大小校验
- `type_gallery.html` 内联 onerror + 底部脚本与 `<a target=_blank>` 重复

---

## 🟢 低优先级问题（简列）

- `classifier.py:1043-1052` 中英文变量名混用 + `range(1,10)` 硬编码页数
- `service.py:713` 访问 pipeline 私有方法 `_get_layer`
- `vlm_layer.py:121` 重复 import `parse_json_from_response`
- `paddleocr_wrapper.py:110` OCRResult.rec_boxes 存储但 blocks 未用
- `prompt_templates.py:99-149` PURCHASE/STOCK_CONTRACT prompt 几乎完全重复
- `vlm_fallback.py:181-185` except Exception 吞没所有异常（含 KeyboardInterrupt）
- `position_extractor.py:243-244` _strip_label 硬编码 hack 脆弱
- `json_utils.py:106` `not escape_next` 死代码
- `__init__.py:25-28` 导入时加载全部重子模块（PaddleOCR/cv2）
- `schemas.py:21` APIResponse.request_id 定义但从未赋值
- `schemas.py:51-115` 多个响应模型未作 response_model 使用（死代码）
- `memory_log.py:39` get_logs 参数 `logger` 遮蔽
- `task_manager.py:603` LogContext worker 结束未清理
- `index.html:7-9` CDN 脚本无 SRI + 版本范围
- `server.py` 无 CSP/X-Content-Type-Options/X-Frame-Options 安全头
- 多处魔法数字散落（建议集中到 config）

---

## 修复优先级建议

### P0 - 立即修复（安全/数据泄露）
1. **S1 IDOR 越权** - task 查询/取消加 api_key 归属校验
2. **S2 debug 路由零鉴权** - server 默认 127.0.0.1 + debug 路由加鉴权/IP 白名单
3. **S3 路径遍历** - `_validate_path` 改 `is_relative_to`
4. **S4 API Key 日志泄露** - create_task 脱敏 + api_usage 存哈希
5. **S5 存储型 XSS** - 上传校验 + UUID 文件名 + Content-Disposition
6. **S6 asyncio.create_task GC** - 保存引用 + 异常兜底
7. **S7/S9 debug DoS** - 复用校验逻辑 + 限流

### P1 - 尽快修复（正确性/性能）
1. **S8 text_det_limit_side_len=64** - 改 960（先运行时验证）
2. **H1 多页 OCR 两次** - 性能翻倍损失
3. **H2 合同签章页误判** - 数据丢失
4. **H3/H4 VLM 兜底不一致** - 影响提取成功率
5. **H21 get_quota 月末崩溃** - 确定 500

### P2 - 计划修复（健壮性/可维护性）
H5-H20、中优先级各项

### P3 - 机会修复
低优先级各项

---

## 附录：最需主审复核的文件（问题密度排序）

1. `src/ocr_api/ocr/debug_routes.py` - 安全问题最密集（零鉴权、路径遍历、上传无校验、DoS）
2. `src/ocr_api/common/task_manager.py` - IDOR 根因、信号量未用、月末崩溃、内存泄漏、api_key 泄露
3. `src/ocr_three_layer_hybrid/service.py` - 多页 OCR 两次、两套 VLM 兜底、访问私有方法、死代码
4. `src/ocr_three_layer_hybrid/paddleocr_wrapper.py` - text_det_limit_side_len=64、多引擎 API 不一致
5. `src/ocr_three_layer_hybrid/classifier.py` - 签章页误判（数据丢失）、死代码
6. `src/ocr_api/ocr/server.py` - 0.0.0.0 绑定、CORS、安全头缺失、认证状态打印错误

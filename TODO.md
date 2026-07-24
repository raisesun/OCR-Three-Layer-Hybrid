# 项目待办事项

## 更新日期：2026-07-23

---

## 🔴 高优先级

### 全量代码审查修复（2026-07-22，分支 fix/security-s1-s9）
- [x] **S1-S9** 安全与正确性（IDOR/鉴权/路径遍历/密钥泄露/XSS/DoS/OCR参数）
- [x] **H1** 多页OCR重复（性能）/ **H2** 合同签章页误判（数据丢失）/ **H21** get_quota月末崩溃
- [x] **H3** VLM兜底缺失 / **H5** position_extractor双实例 / **H6** VLM双重解析+模糊匹配 / **H7** HUKOU键名映射嵌套 / **H8** PaddleOCR访问统一
- [x] **H4部分**（VLM封装/文档，prompt统一待VLM评估）
- [x] GLM-OCR配置调整（默认Qwen，基于评估报告 docs/evaluation_report_20260701.md）
- [x] 运行时验证：S8(64不退化)/H8(.get可用)/H9(0%触发)/H7(户主丢失已修)
- 报告：docs/reviews/code_review_20260722.md | 555测试通过 | 18项已修复

### Code Review 修复
- [x] 修复 #1-#38 所有 Code Review 项（CRITICAL/HIGH/MEDIUM）
- [x] 实现列出任务接口 GET /api/v1/tasks（分页+状态过滤）
- [x] 结构化日志模块（JSON 格式 + ContextVar 上下文传播）
- [x] 分类器测试覆盖补充（18 → 45 用例）
- [x] Demo UI 异步任务管理 Tab

### 待办事项
- [ ] OCR 技术调研
  - [ ] Unlimited OCR（无限画布 OCR）方案评估
  - [ ] DeepSeek OCR 方案评估
- [ ] 邮件告警（错误率、任务失败、配额超限等场景）
- [ ] 生产部署（Docker 镜像、K8s 部署、监控告警）

---

## 🟡 中优先级

### 分类器准确率持续改进
- [x] 不动产权证书专项优化（已修复到 100%，见 analysis/analysis_20260713_不动产权证书分类准确率根因.md）
- [ ] 结婚证/离婚证盖章页专项优化（当前 50%）
- [ ] 引入 OCR 质量预检（文本过短时提前走 VLM 兜底）
- [ ] 数据驱动配置外部化（关键词表移入 field_config.py 或 YAML）
- [ ] 统计分类路由分布（rule/vlm_fallback 比例监控）

### 取消的细分类型（无字段定义，已明确不提取）
- [x] 结婚证-封面（SKIP）
- [x] 离婚证-盖章页（SKIP）

### 待获取示例图片的细分类型
- [ ] 购房合同-首页（4 字段：合同编号、买受人、出卖人、签订日期）
- [ ] 公证书（3 字段：公证书编号、公证事项、公证日期）
- [ ] 委托书（4 字段：委托人、受托人、委托事项、委托日期）
- 示例图片主目录：`/Users/dongsun/Github/sample-OCR/`

### API 功能扩展
- [ ] 批量任务优先级调度（urgent 任务优先处理）
- [ ] 任务结果回调机制（callback_url 实现）
- [ ] API Key 管理界面（创建/吊销/配额调整）

---

## 🟢 低优先级

### 代码质量改进
- [ ] 拆分 rule_layer.py（按文档类型拆分为独立模块）
  - [ ] 创建 household_property_extractor.py
  - [ ] 创建 financial_extractor.py
  - [ ] 创建 agreement_extractor.py
- [ ] 重构 service.py（使用依赖注入）
- [ ] 消除重复代码（提取公共提取逻辑）

### 性能优化
- [ ] 评估 Qwen2.5-VL-3B 准确率（与 7B 对比）
- [ ] 批处理 VLM 请求
- [ ] 添加结果缓存机制
- [ ] 优化 Prompt（减少输入 token）

### 新增文档类型
- [ ] 驾驶证、行驶证、银行卡
- [ ] 空运提单、快递单

---

## ✅ 已完成

### 2026-07-13
- [x] 不动产权证书分类攻坚：分类准确率从伪指标 25% 修复到 100%
  - 澄清 25% 是 7-3 旧版分类器结果 + 测试基准标注错误（061e资金监管误标为property）
  - 方案A：3个字段组合信号（房产证/户口本/结婚证），整体分类准确率 92% → 100%
  - 方案C：多页协同，UNKNOWN 页从首页继承细分类型
  - 轻量修复：VLM 分类结果反馈（vlm_classified_type 字段）
  - 新增 8 个单元测试（分类器 3 个 + 多页协同 4 个 + VLM 反馈 1 个）
  - 详见 analysis/analysis_20260713_不动产权证书分类准确率根因.md

### 2026-07-09
- [x] Code Review #1-#38 全部修复
- [x] 列出任务接口实现（GET /api/v1/tasks）
- [x] 结构化日志模块（JSON 格式 + ContextVar）
- [x] 分类器测试覆盖（18 → 45 用例，覆盖所有阶段）
- [x] Demo UI 异步任务管理 Tab

### 2026-07-08
- [x] 集成测试通过（59 个测试用例）
- [x] 归档过期测试文件
- [x] 任务管理接口完善（取消任务、状态查询）

### 2026-07-05 及之前
- [x] OCR 两层混合架构（RULE + VLM）
- [x] 位置标注提取器
- [x] 字段校验器
- [x] VLM 兜底处理器
- [x] 50 样本全量测试

---

## 📝 技术债务清单

### 架构层面
- [ ] VLM 服务单点故障
- [ ] 扩展性差（新增文档类型复杂）
- [ ] 缺少服务监控

### 代码层面
- [ ] rule_layer.py 过于庞大（2189行，复杂度F级）
- [ ] classifier.py 复杂度高（已改善但仍需拆分）

---

## 📚 相关文档

- 架构 Review: analysis/analysis_20260705_架构Review.md
- API 实施计划: docs/OCR_API_实施计划.md
- 分类器优化: docs/optimization_20260703_classifier_optimization.md
- 扩展指南: docs/扩展指南_新增证件类型.md

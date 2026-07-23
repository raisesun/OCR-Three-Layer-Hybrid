# H3/H4 深度分析：VLM 兜底单图异常不触发 + 单图/多页两套不一致实现

- **分析日期**：2026-07-22
- **分析方法**：第一性原理 + 批判性思维 + 苏格拉底提问法
- **问题编号**：H3（单图 RULE 异常不触发 VLM 兜底）、H4（单图/多页两套不一致 VLM 兜底实现）
- **状态**：未修复

---

## 1. 问题本质（一句话）

VLM 字段级兜底在**单图路径**和**多页路径**用了**两套独立实现**（不同客户端/prompt/触发条件/范围/类型白名单），且单图路径的触发条件 `result.success` 导致 **RULE 层异常（success=False）时不兜底**，字段全空。

H3 是 H4 不一致的一个直接表现。

---

## 2. 事实链（代码层面，已逐行验证）

### 2.1 H3：单图 RULE 异常不触发兜底（pipeline.py:253）
```python
# Rule层字段级VLM重试（校验失败时触发）
if self.vlm_fallback_handler and result.success:   # ← 要求 success=True
    result = self._apply_vlm_fallback(image_path, result, doc_info)
```
- `rule_layer.extract` 异常时返回 `success=False`（字段全空）
- pipeline 要求 `result.success=True` 才兜底 -> **异常时不兜底，字段全空**
- 对比多页（service.py:611）：`if missing_required:` **无论 success** 都检查必填字段并触发 VLM

### 2.2 H4：两套不一致的实现

| 维度 | 单图（pipeline._apply_vlm_fallback） | 多页（service._vlm_fallback_for_page） |
|------|--------------------------------------|----------------------------------------|
| 位置 | pipeline.py:282-324 | service.py:704-727 |
| 客户端 | `vlm_fallback_handler`（VLMFieldRetryHandler） | `vlm_layer`（VLMExtractionLayer） |
| 方法 | `fallback_extract(image_path, failed_fields, doc_type)` | `vlm_layer.extract(doc_info, field_names)` |
| Prompt | `FALLBACK_PROMPTS`（vlm_fallback.py） | `prompt_templates.py` |
| 提取范围 | 只提取失败字段 | 提取所有字段，再取缺失的 |
| 失败字段判定 | `get_failed_fields`（校验失败） | `get_missing_required_fields`（必填缺失） |
| 类型白名单 | 有（HOUSEHOLD_REGISTER/MARRIAGE_CERTIFICATE/ID_CARD） | 无（任何类型有必填缺失都触发） |
| 触发条件 | `result.success`（H3 问题） | `missing_required` |
| 封装 | 走 pipeline 公共方法 | 访问 `pipeline._get_layer` **私有方法**（:719） |

### 2.3 调用链
```
单图: process_image -> pipeline.process -> line 253 (if success) -> _apply_vlm_fallback
                                                -> vlm_fallback_handler.fallback_extract
多页: process_multi_page -> _extract_multi_page_merge.extract_page
      -> line 611 (if missing_required) -> _vlm_fallback_for_page
                                          -> pipeline._get_layer(VLM).extract  # 私有访问
```

---

## 3. 根因追溯（苏格拉底自问自答）

**Q1：为什么有两套实现？**
-> 多页逻辑（v2.1 的 _extract_multi_page_merge）后加，当时直接用了 `vlm_layer.extract`（提取所有字段），而非复用 pipeline 已有的 `_apply_vlm_fallback`（用 vlm_fallback_handler 提取失败字段）。演变遗留。

**Q2：为什么单图要求 result.success？**
-> 设计意图：只在 RULE 层"成功但字段校验失败"时兜底。但忽略了 RULE 层**异常**（success=False、字段全空）也是"字段失败"的极端情况。条件过严。

**Q3：为什么多页访问 pipeline._get_layer 私有方法？**
-> 多页的 _vlm_fallback_for_page 在 service 层，要拿 vlm_layer 只能通过 pipeline._get_layer（私有）。因为 pipeline 没暴露公共的 vlm_layer 访问器。封装缺失。

**Q4：为什么没被发现？**
-> H3 需 RULE 层异常触发（特定 OCR 文本异常才出现）；H4 需对比单图/多页同文档结果才察觉。两者都是条件性/对比性问题，通用测试难覆盖。

**Q5：是设计缺陷还是演变遗留？**
-> 两者都有。H3 是条件设计过严；H4 是多页绕过 pipeline 封装独立实现，导致两套并存。

---

## 4. 批判性评估：严重性

agent 标 🟠高，**确认合理但需分情况**：
- **H3**：单图 RULE 异常时字段全空，本可 VLM 补救。**影响提取成功率**（特定异常场景）。但触发需 RULE 异常（不常见），且只影响白名单 3 类
- **H4**：同文档单图/多页 VLM 行为不同，**难复现/回归**，维护负担。但日常使用中用户通常只走一种路径（单图或多页），不一致不易察觉

**对比已修复项**：H3/H4 不如 H2（数据丢失）、H21（确定崩溃）紧迫，但比 H5（资源/维护）更影响功能。属**中等优先级**。

---

## 5. 修复后的影响分析

### 5.1 H3 修复（简单）：放宽触发条件
**改动**：pipeline.py:253 `if self.vlm_fallback_handler and result.success:` -> `if self.vlm_fallback_handler:`
- `_apply_vlm_fallback` 内部已有 `get_failed_fields` 判断（:301-303 `if not failed_fields: return result`），无失败字段时直接返回，不会误触发
- 类型白名单（:292-298）仍限 3 类，其他类型不受影响

**正面**：单图 RULE 异常时（3 类白名单文档）触发 VLM 兜底，字段可补救
**风险**：
- 异常时字段全空 -> `get_failed_fields` 可能返回所有字段 -> VLM 提取所有字段（开销大但正确）
- 仅影响 3 类白名单文档，范围可控
- 需确认 `get_failed_fields` 对全空字段的判定（应判为失败）

### 5.2 H4 修复（复杂）：统一两套实现
需先做架构决策--统一到哪套：

**选项 A：多页统一到单图路径（用 vlm_fallback_handler）**
- 多页 _vlm_fallback_for_page 改用 pipeline._apply_vlm_fallback
- 优点：复用封装、不访问私有方法、prompt 统一
- 缺点：单图有类型白名单（3类），多页统一后也受限（多页原本无白名单，所有类型可兜底）；失败字段判定从 `missing_required` 改为 `get_failed_fields`（语义变化）

**选项 B：单图统一到多页路径（用 vlm_layer）**
- 单图 _apply_vlm_fallback 改用 vlm_layer.extract
- 优点：无白名单限制、提取所有字段
- 缺点：放弃 vlm_fallback_handler 的 FALLBACK_PROMPTS 和统计；单图行为变化大

**选项 C：仅修 H3，H4 暂不统一（分步）**
- 先修 H3（简单、立即收益）
- H4 统一作为后续架构优化，需先评估两套 prompt 效果差异
- 优点：低风险、渐进
- 缺点：不一致仍在

### 5.3 影响范围
- **H3**：单图 3 类白名单文档 RULE 异常时的提取成功率提升
- **H4**：统一后行为一致，但需回归单图/多页所有文档类型的 VLM 兜底
- **测试**：需加单图 RULE 异常触发 VLM 的测试；H4 统一需回归现有 VLM 兜底测试
- **VLM 服务依赖**：VLM 兜底测试需 VLM 服务（localhost:8082），本机未启动，部分测试难验证

---

## 6. 方案对比

| 方案 | 改动 | H3 | H4 | 风险 |
|------|------|----|----|------|
| **C. 仅修 H3** | pipeline.py:253 去 success 条件 | ✅ 修 | ❌ 不统一 | 低 |
| A. 多页统一到单图 | + 多页改用 _apply_vlm_fallback | ✅ | ✅（但白名单/语义变化） | 中 |
| B. 单图统一到多页 | + 单图改用 vlm_layer | ✅ | ✅（但放弃 fallback_handler） | 中高 |

---

## 7. 推荐方案

**推荐分步：先修 H3（方案 C），H4 统一待评估**

**理由**：
1. **H3 修复简单、低风险、立即收益**：1 行改动，仅影响 3 类白名单文档的异常场景
2. **H4 统一需架构决策**：两套 prompt（FALLBACK_PROMPTS vs prompt_templates）的效果差异未评估，贸然统一可能影响提取准确率。需先用基线样本对比两套 prompt 效果
3. **H4 的危害性低于 H3**：H4 是"不一致"（维护性问题），H3 是"不兜底"（功能缺失）。先修功能

**H3 实施要点**（pipeline.py:253）：
```python
# 原
if self.vlm_fallback_handler and result.success:
# 改为（_apply_vlm_fallback 内部 get_failed_fields 会判断是否真有失败字段）
if self.vlm_fallback_handler:
```

**H4 后续**（待评估后决定 A 或 B）：
- 用基线样本对比 vlm_fallback_handler.fallback_extract vs vlm_layer.extract 的准确率
- 评估白名单策略（3类 vs 全类型）
- 统一后加单图/多页一致性测试

---

## 8. 下一步行动

1. **H3**：按方案 C 修复（1 行），加单图 RULE 异常触发 VLM 的测试（需 mock）
2. **H4**：暂不统一，用基线样本评估两套 prompt 效果后再决策
3. 回归 `test_pipeline.py`、`test_vlm_fallback.py`

**优先级**：H3 修复性价比高（简单+收益），可立即做。H4 是架构优化，建议评估后单独处理。

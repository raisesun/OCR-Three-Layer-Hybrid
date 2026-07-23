# H4 深度分析：VLM 兜底两套 prompt 统一评估

- **分析日期**：2026-07-22
- **问题编号**：H4（单图/多页两套不一致 VLM 兜底实现）
- **关联**：H3 已修复（单图异常不兜底）；本文档聚焦 H4 的 prompt 统一评估
- **状态**：未修复（待 VLM 服务 + 基线样本评估）

---

## 1. 问题本质

单图路径和多页路径的 VLM 兜底用了**两套不同的 prompt 策略**：单图用"精简失败字段"prompt（vlm_fallback.FALLBACK_PROMPTS），多页用"完整字段+规则"prompt（prompt_templates.PROMPT_TEMPLATES）。统一前需评估两套 prompt 的提取效果差异，避免贸然统一影响准确率。

---

## 2. 两套 prompt 详细对比

### 2.1 单图兜底 prompt（vlm_fallback.py:48-103）
```
角色 + "提取以下字段的值" + {fields}(失败字段名列表) + {json_template}({field:""}) + 注意事项
```
- **覆盖**：3 类（HOUSEHOLD_REGISTER/MARRIAGE_CERTIFICATE/ID_CARD）+ DEFAULT 通用
- **字段范围**：**只提取 failed_fields**（动态，RULE 失败的字段）
- **字段说明**：仅列字段名（如"- 户主姓名"），**无提取规则**
- **注意事项**：类型特定（户口本区分左右列、身份证18位）
- **token**：少（只失败字段 + 精简说明）

### 2.2 多页兜底 prompt（prompt_templates.py，vlm_layer._build_prompt 调用）
```
角色 + 详细字段说明(每字段的提取规则) + JSON模板(所有字段) + COMMON_SUFFIX
```
- **覆盖**：所有文档类型
- **字段范围**：**提取所有字段**（key_list）
- **字段说明**：**每字段有提取规则**（如"户别：户口类型，如家庭户、集体户"、"公民身份号码：从「公民身份证件编号」栏提取"）
- **注意事项**：COMMON_SUFFIX 通用 + 类型特定
- **token**：多（所有字段 + 详细规则）

### 2.3 对比表

| 维度 | 单图 fallback prompt | 多页 prompt_templates |
|------|---------------------|----------------------|
| 字段范围 | 只失败字段 | 所有字段 |
| 字段说明 | 仅字段名 | 每字段提取规则 |
| 详细度 | 精简 | 详细 |
| token 消耗 | 少 | 多 |
| 覆盖类型 | 3 类 + DEFAULT | 所有类型 |
| 适用场景 | RULE 已提取大部分，补救少数 | 完整 VLM 提取 |
| 准确率（推测） | 较低（无规则提示） | 较高（有规则提示） |

---

## 3. 统一的影响分析

### 3.1 方案 A：多页统一到单图（用 fallback prompt）
**正面**：
- token 省（只提取失败字段）
- 复用 vlm_fallback_handler 封装，不访问私有方法
- 单一 prompt 源

**负面**：
- **准确率可能降**：fallback prompt 无详细字段规则，多页原本用详细 prompt，统一后准确率可能下降
- 多页失败字段判定从 `missing_required` 改为 `get_failed_fields`（语义变化）
- 类型白名单：fallback 限 3 类，多页原本无白名单（统一后多页也受限）

### 3.2 方案 B：单图统一到多页（用 prompt_templates）
**正面**：
- 详细 prompt，准确率可能更高
- 无白名单限制（所有类型可兜底）
- 单一 prompt 源

**负面**：
- **token 多**：即使只缺少数字段也提取所有字段
- 放弃 vlm_fallback_handler 的统计/精简优势
- 单图行为变化大（原本精简补救 -> 完整提取）

### 3.3 方案 C：保持两套，文档化
- 接受不一致，明确各自适用场景
- 单图用 fallback（精简补救），多页用 prompt_templates（完整提取）
- 风险：维护负担，行为不一致

---

## 4. 统一前需评估的指标

无法凭理论判断 A/B 哪个更好，**必须实测**以下指标：

| 指标 | 评估方法 |
|------|----------|
| **提取准确率** | 同一样本，两套 prompt 分别调 VLM，对比字段准确率 |
| **token 消耗** | 记录两套 prompt 的输入/输出 token |
| **耗时** | 单次 VLM 调用耗时 |
| **失败字段覆盖率** | fallback 只提取失败字段是否够（vs 提取所有字段） |
| **边界场景** | RULE 全空时 fallback 提取所有失败字段 vs prompt_templates 提取所有字段 |

### 4.1 评估方案
1. **准备基线样本**：户口本/结婚证/身份证 各 10-20 张（3 类白名单）
2. **跑两套 prompt**：
   - fallback：`vlm_fallback_handler.fallback_extract(image, failed_fields, doc_type)`
   - prompt_templates：`vlm_layer.extract(doc_info, all_field_names)`
3. **对比**：每张图的字段准确率、token、耗时
4. **决策**：
   - 若 fallback 准确率 ≥ prompt_templates（95%置信）：方案 A（省 token）
   - 若 prompt_templates 明显更准（>3%）：方案 B（保准确率）
   - 若差异不显著：方案 A（省 token + 复用封装）

### 4.2 评估前提
- **VLM 服务**：需启动 Qwen2.5-VL（localhost:8082）。**本机当前未运行**（`test_real_extraction` 连接被拒）
- **基线样本**：需有标注的户口本/结婚证/身份证图片
- **VLM 客户端配置**：两套用不同客户端（vlm_fallback_handler.vlm_client vs vlm_layer._client），需确认配置一致（否则对比不公平）

---

## 5. 本机限制与现状

- **VLM 服务未运行**：localhost:8082 connection refused，无法立即评估
- **基线样本**：项目有 `baseline_service` 和 `scripts/regression_test_samples.py`，可能含合同/证书样本，但户口本/结婚证/身份证样本待确认
- **两套客户端配置**：vlm_fallback_handler 默认用 GLM-OCR（vlm_fallback.py:122 `VLMClient()` 默认），vlm_layer 用注入配置。**可能不是同一 VLM 模型**，对比前需统一

---

## 6. 推荐决策

### 6.1 短期（当前）：不统一 H4，保持两套
**理由**：
1. H3 已修复功能缺失（单图异常不兜底），H4 的"不一致"是维护性问题，非功能缺失
2. 统一需 VLM 服务 + 基线评估，本机无 VLM 环境
3. 贸然统一（无评估）可能影响准确率（方案 A 风险）或浪费 token（方案 B 风险）

### 6.2 中期（有 VLM 环境时）：评估后统一
1. 启动 VLM 服务
2. 按 4.1 跑两套 prompt 对比
3. 根据准确率/token 结果选 A 或 B
4. 统一后加单图/多页一致性测试

### 6.3 可立即做的优化（不依赖 VLM）
- **统一客户端配置**：确认 vlm_fallback_handler 和 vlm_layer 用同一 VLM 模型（避免配置漂移，vlm_fallback.py:122 默认 GLM-OCR vs 文档说 Qwen）
- **暴露公共访问器**：pipeline 加公共方法 `get_vlm_layer()` 替代 service 访问 `_get_layer` 私有方法（H4 的封装问题，不涉及 prompt）
- **文档化**：在 vlm_fallback.py 和 vlm_layer.py 注明两套 prompt 的适用场景

---

## 7. 下一步行动

1. **H4 暂不统一**（待 VLM 环境），记录于审查报告
2. **可立即做**（可选）：
   - 统一 VLM 客户端配置（vlm_fallback 默认配置对齐 vlm_layer）
   - pipeline 加 `get_vlm_layer()` 公共方法，service 改用（解决私有访问，不改 prompt）
3. **有 VLM 环境时**：按 4.1 评估，决策 A/B

**优先级**：H4 是优化项，不紧急。当前 13 项修复（S1-S9+H1+H2+H21+H3）已覆盖所有安全漏洞 + 数据丢失 + 崩溃 + 性能 + 兜底缺失。H4 统一可作为后续 VLM 优化的一部分。

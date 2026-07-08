# #21 VLM Prompt 模板外置 — 详细分析与修改方案

> **日期**: 2026-07-09
> **状态**: ✅ 已完成（2026-07-09）
> **关联**: `analysis_20260709_全项目CodeReview.md` #21

---

## 1. 问题描述

`src/ocr_three_layer_hybrid/vlm_layer.py` 共 893 行，其中第 76-558 行（483 行）全部是 `PROMPT_TEMPLATES` 字典——18 个 VLM prompt 模板硬编码为类变量。

### 1.1 问题影响

| 问题 | 影响 |
|------|------|
| 文件过长 | vlm_layer.py 893 行，难以 review 和理解 |
| 改 prompt 要改代码 | 调优 prompt 需要修改 Python 源码并重新部署 |
| 大量重复样板 | "重要注意事项"在 18 个 prompt 中重复 18 遍 |
| 代码与数据混合 | 业务数据（prompt）和业务逻辑（extract/parse）耦合 |

### 1.2 Prompt 结构分析

每个 prompt 由 4 部分组成：

```
┌─ 角色声明（1-2 句）           ← 每个 prompt 不同
├─ 输出 JSON 格式（字段列表）    ← 每个 prompt 不同
├─ 字段提取说明（编号列表）      ← 每个 prompt 不同
└─ 重要注意事项（3-5 条）       ← 几乎完全重复
```

**重复的样板文本**（在 18 个 prompt 中反复出现）：
- `"只输出纯JSON，不要包含markdown代码块标记"` → 出现 18 次
- `"不要输出任何其他解释文字"` → 出现 15 次
- `"如果某个字段不存在或无法识别，保留为空字符串"` → 出现 18 次

---

## 2. 方案对比

### 方案 A：外部 prompts/ 目录（.txt 文件）
- 每个文档类型一个 .txt 文件
- 优点：改 prompt 不改代码，非开发人员可编辑
- 缺点：18 个新文件，运行时 I/O，包分发复杂

### 方案 B：提取到 prompt_templates.py + 公共后缀组合 ✅ 选定
- 创建独立 `prompt_templates.py` 数据文件
- 提取公共注意事项为 `COMMON_SUFFIX`
- `build_prompt()` 函数组合 template + suffix
- 优点：改动最小、无 I/O、保持类型检查、消除重复
- 缺点：改 prompt 仍改代码

### 方案 C：Jinja2 模板继承
- 用 Jinja2 base template + YAML 数据
- 优点：最 DRY
- 缺点：引入 Jinja2 + PyYAML 依赖，当前 18 个 prompt 不值得

**选择方案 B 的理由**：性价比最高，vlm_layer.py 从 893 行降至 ~410 行，消除 18 处重复，且不引入新依赖。

---

## 3. 修改方案详细设计

### 3.1 新增文件：`src/ocr_three_layer_hybrid/prompt_templates.py`

```python
"""
VLM Prompt 模板定义

每个文档类型的 prompt 只定义「角色 + 字段格式 + 提取说明」。
公共注意事项由 COMMON_SUFFIX 统一管理。
"""

from typing import Dict, List, Optional

# ========== 公共后缀 ==========
# 所有 prompt 共用的注意事项（消除 18 处重复）
COMMON_SUFFIX = (
    "## 重要注意事项\n"
    "- 只输出纯JSON，不要包含markdown代码块标记（如```json）\n"
    "- 不要输出任何其他解释文字\n"
    "- 如果某个字段在图片中不存在或无法识别，该字段值保留为空字符串\n"
)

# ========== Prompt 模板 ==========
# key = DocumentType.value（字符串），便于外部配置覆盖
PROMPT_TEMPLATES: Dict[str, str] = {
    "HOUSEHOLD_REGISTER": (
        "你是一名专业的户口本页页信息提取专家。...\n\n"
        "## 输出JSON格式\n...\n\n"
        "## 字段提取说明\n..."
    ),
    # ... 其余 17 个
}

# ========== 构建函数 ==========
def build_prompt(doc_type_key: str, key_list: Optional[List[str]] = None) -> str:
    """根据文档类型构建完整 prompt（template + 公共后缀）"""
    template = PROMPT_TEMPLATES.get(doc_type_key)
    if template is None:
        if key_list:
            return f"请从图片中提取以下字段：{'、'.join(key_list)}，以JSON格式返回。"
        return "请从图片中提取所有可识别的信息，以JSON格式返回。"
    return template + "\n" + COMMON_SUFFIX
```

### 3.2 修改文件：`src/ocr_three_layer_hybrid/vlm_layer.py`

**删除**：第 76-558 行（PROMPT_TEMPLATES 字典，483 行）

**新增导入**：
```python
from ocr_three_layer_hybrid.prompt_templates import build_prompt
```

**修改 `_build_prompt` 方法**（第 747-769 行）：
```python
def _build_prompt(self, doc_info: DocumentInfo, key_list: List[str]) -> str:
    """构建Prompt（考虑文档类型和页面类型）"""
    # 优先使用精确类型的 Prompt
    prompt = build_prompt(doc_info.doc_type.value, key_list)

    # 如果精确类型无模板，回退到基础类型
    if prompt.endswith(COMMON_SUFFIX) and doc_info.doc_type.value not in PROMPT_TEMPLATES:
        base_type = self._get_base_doc_type(doc_info.doc_type)
        prompt = build_prompt(base_type.value, key_list)

    return prompt
```

### 3.3 修改文件：`src/ocr_three_layer_hybrid/__init__.py`

无需修改。prompt_templates 是内部模块。

---

## 4. 执行步骤

| 步骤 | 操作 | 验证 |
|------|------|------|
| 1 | 创建 `prompt_templates.py`，提取 COMMON_SUFFIX + 18 个 prompt | — |
| 2 | 在 `prompt_templates.py` 中实现 `build_prompt()` | 单元测试或手动验证 |
| 3 | 修改 `vlm_layer.py`：删除 PROMPT_TEMPLATES，导入新模块 | — |
| 4 | 修改 `_build_prompt()` 方法调用 `build_prompt()` | — |
| 5 | 运行现有测试确认无回归 | `pytest tests/` |
| 6 | 更新 CodeReview 文档标记为已修复 | — |

---

## 5. 预期效果

| 指标 | 修改前 | 修改后 |
|------|--------|--------|
| vlm_layer.py 行数 | 893 | ~410 |
| prompt_templates.py 行数 | 0 | ~500 |
| "重要注意事项"重复次数 | 18 | 1 |
| 改 prompt 是否改代码 | 是 | 是（但只改一个文件） |
| 新增外部依赖 | — | 无 |

---

## 6. 风险评估

| 风险 | 概率 | 缓解 |
|------|------|------|
| prompt 文本提取时遗漏字符 | 低 | 逐一对比原文，确保完全一致 |
| build_prompt 回退逻辑变化 | 低 | 保持与原版 _build_prompt 相同的回退链 |
| 已有测试覆盖不足 | 中 | 手动用测试图片验证提取效果 |

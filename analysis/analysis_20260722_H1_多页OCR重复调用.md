# H1 深度分析：多页处理每页 OCR 重复调用两次

- **分析日期**：2026-07-22
- **分析方法**：第一性原理 + 批判性思维 + 苏格拉底提问法
- **问题编号**：H1（审查报告 `docs/reviews/code_review_20260722.md`，🟠高）
- **状态**：未修复

---

## 1. 问题本质（一句话）

多页文档处理时，**每一页都被 PaddleOCR 识别两次**：一次用于分类、一次用于字段提取。两次调用对同一张图返回完全相同的结果，第二次是纯浪费，导致多页处理耗时**翻倍**。

---

## 2. 事实链（代码层面，已逐行验证）

### 2.1 OCR 调用统计

`run_ocr`（`service.py:172-239`）**无缓存**，每次调用都重新执行 `wrapper.run_ocr()`（若启用预处理还重新执行 `enhance_image`）。

`process_multi_page` + `_extract_multi_page_merge` 对每页的 OCR 调用：

| 页 | 调用点 | 用途 | 次数 |
|----|--------|------|------|
| 首页 | `service.py:378` `run_ocr(首页)` | 分类（`classify`） | 1 |
| 首页 | `service.py:587` `run_ocr(首页)` | 提取（`pipeline.process`） | 1 |
| 后续页 | `service.py:519` `run_ocr(页)` | 分类（`classify`） | 1 |
| 后续页 | `service.py:587` `run_ocr(页)` | 提取（`pipeline.process`） | 1 |

**每页共 2 次 OCR**。`extract_page` 闭包内 line 519（分类）和 line 587（提取）对同一 `img_path` 各调一次 `run_ocr`，结果相同。

### 2.2 调用链
```
process_multi_page (service.py:374)
├─ line 378: first_page_text = run_ocr(首页)          # 首页 OCR #1（分类）
├─ line 382: classify(首页, [first_page_text])
└─ line 397: _extract_multi_page_merge(pages, first_doc_info)
    └─ extract_page(img_path, page_idx) 闭包
        ├─ page_idx==0: 复用 first_page_doc_info（不再 OCR 分类）
        ├─ page_idx>0: line 519 run_ocr(页) -> classify  # 后续页 OCR #1（分类）
        ├─ line 587: run_ocr(img_path)                   # 所有页 OCR #2（提取）← 重复
        └─ line 590: pipeline.process(img_path, [ocr_text], doc_info)
```

### 2.3 性能影响量化
- PP-OCRv6 约 41.5s/张（CPU）
- 15 页文档：当前 30 次 OCR ≈ 1245s；修复后 15 次 ≈ 622s，**省 ~622s（约一半）**
- 若启用图像预处理，每次 OCR 还伴随 `enhance_image`，浪费翻倍

---

## 3. 根因追溯（苏格拉底自问自答）

**Q1：为什么会 OCR 两次？**
-> 分类需要 OCR 文本（`classify(img_path, ocr_texts)`），提取也需要 OCR 文本（`pipeline.process(img_path, ocr_texts, ...)`）。两处各自调用 `run_ocr`，没有共享结果。

**Q2：为什么没共享？**
-> `process_multi_page` 先 OCR 首页做分类（line 378），再把 `first_doc_info` 传给 `_extract_multi_page_merge`，但**没传首页 OCR 文本**。闭包内 line 587 为了提取又 OCR 一次。后续页更明显：同一闭包内 line 519（分类）和 line 587（提取）对同一图两次 `run_ocr`。

**Q3：为什么 run_ocr 不缓存？**
-> `run_ocr` 设计为无状态纯函数式调用。缓存会引入缓存失效/内存问题。无缓存本身没错，错在调用方重复调用。

**Q4：这是设计缺陷还是演变遗留？**
-> 演变遗留。`_extract_multi_page_merge` 的"逐页独立分类 + 提取"设计（v2.1）加入时，分类和提取在闭包内分两步，各自 OCR。首页分类在 `process_multi_page` 外层做（line 378），但结果没传进闭包，导致闭包内 line 587 重新 OCR。是**OCR 结果在函数边界未传递**的遗留。

**Q5：第二次 OCR 结果与第一次不同吗？**
-> 相同。同图、同引擎、同参数、`enhance_image` 确定性。所以第二次是纯冗余，无功能价值。

---

## 4. 批判性评估：严重性确认

agent 标 🟠高，**确认合理**：
- **性能**：多页文档耗时翻倍，15 页浪费 ~600s。批量场景（基线测试 50+ 张）影响显著。这是**真实的、确定的**性能损失，非理论。
- **正确性**：无影响（两次结果相同）
- **资源**：CPU/内存推理负担翻倍

**对比 H5**：H1 是确定的性能翻倍（高），H5 是资源/维护（中）。H1 更值得先修。

---

## 5. 修复后的影响分析（重点）

### 5.1 正面影响
1. **性能：多页处理耗时约减半**。每页 OCR 2->1 次，15 页省 ~600s。批量基线测试提速明显
2. **预处理减半**：若启用 `enable_image_preprocessing`，`enhance_image` 也从 2 次/页降到 1 次/页
3. **资源**：CPU 推理负担减半
4. **一致性**：分类与提取用**同一份** OCR 文本（当前两次虽结果相同，但共用消除任何潜在不一致）

### 5.2 潜在风险与负面影响

1. **正确性风险：极低**。同图同引擎 OCR 结果相同，合并后分类和提取用同一文本，行为不变。`classify` 和 `pipeline.process` 接口不变（都接收 `ocr_texts`）
2. **测试风险：低**。`test_service.py` 的多页测试（`TestMultiPageTypeInheritance`）mock `run_ocr` 返回固定值，**不断言调用次数**，断言的是 `_pipeline.process` 的 `doc_info` 继承逻辑。合并 OCR 不改变分类/提取流程，测试应继续通过
3. **签名变更：低**。`_extract_multi_page_merge` 需加 `first_page_ocr_text=None` 参数。测试直接调 `_extract_multi_page_merge(pages, first_doc)` 不传该参数，靠默认值 `None` 兼容（首页 fallback 到 `run_ocr`，测试 mock 仍工作）
4. **首页 OCR 传递**：`process_multi_page` 需把 line 378 的 `first_page_text` 传入 `_extract_multi_page_merge`。改动集中在 `service.py`，单文件
5. **继承逻辑不受影响**：UNKNOWN 页继承首页类型（line 531-561）基于 `page_doc_info`，与 OCR 文本来源无关
6. **VLM 兜底不受影响**：line 605-633 基于 `result.fields` 和 `missing_required`，与 OCR 次数无关

### 5.3 影响范围
- **功能正确性**：预期不变（同图同引擎结果相同）
- **性能**：多页处理显著提升
- **测试**：需回归 `test_service.py` 多页测试；预期通过（无 call_count 断言）
- **部署**：无影响（无配置/接口变化）
- **改动范围**：仅 `service.py` 单文件

---

## 6. 方案对比

| 方案 | 改动 | 优点 | 缺点 |
|------|------|------|------|
| **A. 闭包内合并 OCR + 首页复用** | `_extract_multi_page_merge` 加 `first_page_ocr_text` 参数；闭包内后续页 OCR 一次供分类+提取共用；首页用传入文本 | 最小改动、单文件、无副作用、根治 | 需透传首页 OCR 文本 |
| **B. run_ocr 加缓存** | `run_ocr` 内按 `image_path` 缓存结果 | 通用，调用方无需改 | 引入缓存状态/失效/内存问题；全局副作用；难清理 |
| **C. 提取层接收已 OCR 文本** | 重构 `pipeline.process` 必须接收 OCR 文本 | 架构清晰 | 改动面大，影响单图路径 |

---

## 7. 推荐方案

**方案 A（闭包内合并 OCR + 首页复用）**，理由：

1. **根治**：消除重复调用本身，而非用缓存掩盖
2. **最小改动**：仅 `service.py` 单文件，无新状态
3. **无副作用**：不引入缓存失效/内存问题
4. **测试友好**：加默认参数兼容现有测试

**实施要点**（service.py）：
```python
# process_multi_page（line 397）
result = self._extract_multi_page_merge(
    pages_to_process, first_doc_info, first_page_ocr_text=first_page_text
)

# _extract_multi_page_merge 签名加参数
def _extract_multi_page_merge(self, image_paths, first_page_doc_info, first_page_ocr_text=None):
    def extract_page(img_path, page_idx):
        if page_idx == 0:
            page_doc_info = first_page_doc_info
            # 复用首页 OCR 文本，避免重复 OCR（无传入时 fallback）
            ocr_text = first_page_ocr_text if first_page_ocr_text is not None else self.run_ocr(img_path)
        else:
            ocr_text = self.run_ocr(img_path)          # 后续页 OCR 一次
            ocr_texts_for_classify = [ocr_text] if ocr_text else []
            page_doc_info = self._classifier.classify(img_path, ocr_texts_for_classify)
            # ... 继承逻辑不变 ...
        # 提取：用同一 ocr_text，删除原 line 587 的重复 run_ocr
        ocr_texts = [ocr_text] if ocr_text else []
        result = self._pipeline.process(img_path, ocr_texts, doc_info=page_doc_info)
        # ... 后续 VLM 兜底不变 ...
```

**关键验证点**：
- 回归 `test_service.py::TestMultiPageTypeInheritance`（4 项）确认继承逻辑不变
- 回归 `test_service.py::TestMultiPageBasic` 确认空输入等不变
- 可选：加一个测试验证多页 run_ocr 调用次数 = 页数（而非 2×页数）

---

## 8. 下一步行动

1. 按方案 A 实施，改动仅 `service.py`
2. 回归 `test_service.py` 多页测试
3. 可选：加 `run_ocr` 调用次数断言测试，固化"每页只 OCR 一次"
4. 提交到 `fix/security-s1-s9` 分支或新分支

**与 H5 对比**：H1 是确定的性能翻倍（高优先级），H5 是资源/维护（中）。H1 改动更小（单文件）、风险更低、收益更直接。建议先修 H1。

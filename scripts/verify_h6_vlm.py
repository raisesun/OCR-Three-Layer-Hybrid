#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""验证 H6：VLM 返回的 doc_type 格式 + 模糊匹配触发

启动 GLM-OCR(8080)后，用 VLMExtractionLayer 对 UNKNOWN 文档跑 extract，
看 vlm_classified_type（H6 模糊匹配结果）+ VLM 返回的 doc_type 字符串。
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from ocr_three_layer_hybrid.vlm_layer import VLMExtractionLayer
from ocr_three_layer_hybrid.interfaces import DocumentInfo, DocumentType

# GLM-OCR 配置（port 8080）
vlm = VLMExtractionLayer(
    base_url="http://localhost:8080/v1",
    model_name="GLM-OCR-Q8_0.gguf",
    timeout=120,
)

# 构造 UNKNOWN 文档（触发 VLM 分类 + 提取）
img = "tests/fixtures/sample_property.jpg"
doc_info = DocumentInfo(
    image_path=img,
    doc_type=DocumentType.UNKNOWN,
    ocr_texts=[""],
)

print(f"对 {img} 跑 VLM extract（doc_type=UNKNOWN）...")
result = vlm.extract(doc_info, ["户主姓名", "户号", "住址"])

print(f"\n=== H6 验证结果 ===")
print(f"vlm_classified_type: {result.vlm_classified_type}")
print(f"vlm_classified_type.value: {result.vlm_classified_type.value if result.vlm_classified_type else None}")
print(f"fields: {result.fields}")
print(f"success: {result.success}")

# 分析：vlm_classified_type 是精确/别名/模糊匹配？
if result.vlm_classified_type:
    dt = result.vlm_classified_type
    print(f"\n分类路径分析:")
    if dt.value == "未知":
        print("  VLM 未分类（仍 UNKNOWN）")
    else:
        print(f"  VLM 分类为: {dt.value}（{dt.name}）")
        print(f"  -> 若 VLM 返回完整名'{dt.value}'，精确匹配命中，模糊匹配未触发")

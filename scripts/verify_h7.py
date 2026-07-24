#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""验证 H7：Qwen2.5-VL-7B 对 UNKNOWN 户口本的 VLM 响应格式 + 键名映射

看 VLM 返回的是嵌套 {"fields":{...}} 还是扁平，fields 键名是"户主"还是"户主姓名"，
确认 H7（嵌套跳过 HUKOU_KEY_MAPPINGS）是否触发。
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from ocr_three_layer_hybrid.vlm_layer import VLMExtractionLayer
from ocr_three_layer_hybrid.interfaces import DocumentInfo, DocumentType
from ocr_three_layer_hybrid.json_utils import parse_json_from_response

# Qwen2.5-VL-7B（默认 VLM，port 8082）
vlm = VLMExtractionLayer(
    base_url="http://localhost:8082/v1",
    model_name="qwen2.5-vl-7b",
    timeout=180,
)

img = "docs/images/户口本_首页.jpeg"
doc_info = DocumentInfo(
    image_path=img,
    doc_type=DocumentType.UNKNOWN,
    ocr_texts=[""],
)
key_list = ["户主", "户号", "住址", "户别"]  # HUKOU_KEY_MAPPINGS 的 key

print(f"对 {img} 跑 VLM extract（doc_type=UNKNOWN, key_list={key_list}）...")

# 先看 VLM 原始响应（确认嵌套格式 + 键名）
prompt = vlm._build_prompt(doc_info, key_list)
response = vlm._call_vlm(prompt, doc_info.image_path)
print(f"\n=== VLM 原始响应 ===")
print(repr(response)[:500])

# 解析看格式
parsed = parse_json_from_response(response) if isinstance(response, str) else response
print(f"\n=== 解析后 ===")
print(f"type: {type(parsed)}")
if isinstance(parsed, dict):
    print(f"keys: {list(parsed.keys())}")
    if "fields" in parsed:
        print(f"嵌套格式！fields keys: {list(parsed['fields'].keys()) if isinstance(parsed['fields'], dict) else 'N/A'}")
    else:
        print(f"扁平格式。字段键: {[k for k in parsed.keys() if k != 'doc_type']}")

# 跑 extract 看最终 fields（H7 触发则"户主"空）
result = vlm.extract(doc_info, key_list)
print(f"\n=== extract 结果 ===")
print(f"fields: {result.fields}")
print(f"vlm_classified_type: {result.vlm_classified_type}")
print(f"\n=== H7 分析 ===")
for k in key_list:
    val = result.fields.get(k, "")
    status = "✅有值" if val else "❌空（可能H7丢失）"
    print(f"  fields['{k}']: {status} {repr(val)[:50]}")

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""验证 S8(text_det_limit_side_len=960 真实效果) + H8(predict() 返回类型)

用 PaddleOCREngine 的配置(PP-OCRv6_medium + 960)跑一张图，确认：
- H8: predict() 返回的 res 是 dict 还是对象，.get/.json 可用性
- S8: text_det_limit_side_len=960 的 OCR 识别效果
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from paddleocr import PaddleOCR

det = os.path.expanduser("~/.paddlex/official_models/PP-OCRv6_medium_det")
rec = os.path.expanduser("~/.paddlex/official_models/PP-OCRv6_medium_rec")

det_side_len = int(sys.argv[1]) if len(sys.argv) > 1 else 960
print(f"初始化 PaddleOCR (text_det_limit_side_len={det_side_len}, PP-OCRv6_medium)...")
ocr = PaddleOCR(
    text_detection_model_dir=det,
    text_recognition_model_dir=rec,
    use_doc_orientation_classify=False,
    use_doc_unwarping=False,
    use_textline_orientation=False,
    text_det_limit_side_len=det_side_len,
    text_det_thresh=0.3,
    text_det_box_thresh=0.6,
    text_det_unclip_ratio=1.5,
)

img = "tests/fixtures/sample_property.jpg"
print(f"\n预测: {img}")
output = ocr.predict(img)
res = output[0]

print("\n" + "=" * 60)
print("H8: predict() 返回类型")
print("=" * 60)
print(f"type(res): {type(res)}")
print(f"hasattr(res, 'get'): {hasattr(res, 'get')}")
print(f"hasattr(res, 'json'): {hasattr(res, 'json')}")
print(f"hasattr(res, '__getitem__'): {hasattr(res, '__getitem__')}")

if hasattr(res, "json"):
    j = res.json
    print(f"\ntype(res.json): {type(j)}")
    if isinstance(j, dict):
        print(f"res.json keys: {list(j.keys())}")
        inner = j.get("res", j)
        if isinstance(inner, dict):
            print(f"inner (j['res']) keys: {list(inner.keys())}")

if hasattr(res, "get"):
    texts_get = res.get("rec_texts", [])
    boxes_get = res.get("rec_boxes", [])
    print(f"\nres.get('rec_texts') 前5: {list(texts_get[:5])}")
    print(f"res.get('rec_boxes') 数量: {len(boxes_get) if boxes_get is not None else 0}")

# 对比 .get 和 .json 返回结构是否一致（H8 关键）
print("\n--- H8 关键: .get 与 .json 返回结构对比 ---")
if hasattr(res, "get") and hasattr(res, "json"):
    j = res.json
    inner = j.get("res", j) if isinstance(j, dict) else {}
    get_texts = res.get("rec_texts", [])
    json_texts = inner.get("rec_texts", []) if isinstance(inner, dict) else []
    print(f"res.get('rec_texts') 数量: {len(get_texts)}")
    print(f"res.json['res']['rec_texts'] 数量: {len(json_texts)}")
    print(f"两者一致: {get_texts == json_texts}")
elif hasattr(res, "get"):
    print("res 支持 .get，不支持 .json -> PaddleOCREngine 当前写法正确")
elif hasattr(res, "json"):
    print("res 支持 .json，不支持 .get -> PaddleOCREngine res.get() 应崩溃（但系统在跑，矛盾）")

print("\n" + "=" * 60)
print("S8: OCR 识别效果（text_det_limit_side_len=960）")
print("=" * 60)
if hasattr(res, "get"):
    texts = res.get("rec_texts", [])
elif hasattr(res, "json"):
    j = res.json
    inner = j.get("res", j) if isinstance(j, dict) else {}
    texts = inner.get("rec_texts", []) if isinstance(inner, dict) else []
else:
    texts = []
print(f"识别到 {len(texts)} 条文本")
for i, t in enumerate(texts[:15]):
    print(f"  [{i}] {t}")

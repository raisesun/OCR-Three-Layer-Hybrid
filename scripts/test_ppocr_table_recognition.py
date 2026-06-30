#!/usr/bin/env python3
"""
PP-OCRv6 + PP-StructureV3 vs GLM-OCR 对比测试

测试目标：验证表格结构感知OCR能否修复4个已知错误
1. 户口本户主姓名：列错位 "王子龙 晨露" → "王晨露"
2. 户口本户号：数字错识别 0→9
3. 结婚证男方身份证号：漏识别 18→17位
4. 结婚证字号：形近字+漏识别 鄂→黔 + 340321→40321
"""

import json
import sys
import os
import time

# 错误图片路径
ERROR_IMAGES = {
    "户口本首页_列错位": "/Users/dongsun/Github/sample-OCR/存量房图片资料/BBJZ-2026-0107026/212a6c910a0b4e2da52ee77c496358a2.jpg",
    "户口本个人页": "/Users/dongsun/Github/sample-OCR/存量房图片资料/BBJZ-2026-0107026/b725d47c747d40ef9119190e63939bb1.jpg",
    "结婚证_多错误": "/Users/dongsun/Github/sample-OCR/存量房图片资料/BBJZ-2026-0112065/f8475c3cabff4dab823112bf1fd5e017.jpg",
}

# 期望值（ground truth）
EXPECTED = {
    "户口本首页_列错位": {
        "户主姓名": "王晨露",  # GLM-OCR输出: "王子龙" (列错位)
        "户号": "009119378",   # 另一个case的错误，此页无户号
    },
    "结婚证_多错误": {
        "男方身份证号": "403211199305078253",  # GLM-OCR输出: "" (17位→空)
        "结婚证字号": "鄂340321-2022-000122",  # GLM-OCR输出: "黔40321-2022-000122"
    },
}


def test_basic_ocr(image_path: str, label: str):
    """测试PaddleOCR基础OCR（PP-OCRv6）"""
    from paddleocr import PaddleOCR

    print(f"\n{'='*60}")
    print(f"[基础OCR] {label}")
    print(f"图片: {os.path.basename(image_path)}")
    print(f"{'='*60}")

    start = time.time()
    ocr = PaddleOCR(lang='ch')
    results = list(ocr.predict(input=image_path))
    elapsed = time.time() - start

    # 提取文本
    texts = []
    for result in results:
        if hasattr(result, 'res') and 'rec_texts' in result.res:
            texts.extend(result.res['rec_texts'])
        elif hasattr(result, 'rec_texts'):
            texts.extend(result.rec_texts)

    full_text = '\n'.join(texts)

    print(f"\n耗时: {elapsed:.2f}s")
    print(f"文本行数: {len(texts)}")
    print(f"\n--- OCR输出 ---")
    print(full_text[:2000])
    print(f"--- END ---")

    return full_text, texts


def test_structure_v3(image_path: str, label: str):
    """测试PP-StructureV3（带表格识别）"""
    from paddleocr import PPStructureV3

    print(f"\n{'='*60}")
    print(f"[PP-StructureV3] {label}")
    print(f"图片: {os.path.basename(image_path)}")
    print(f"{'='*60}")

    start = time.time()
    pp_structure = PPStructureV3()

    results = list(pp_structure.predict(
        input=image_path,
        use_table_recognition=True,
    ))
    elapsed = time.time() - start

    print(f"\n耗时: {elapsed:.2f}s")

    # 分析结果
    for i, result in enumerate(results):
        print(f"\n--- 结果 {i+1} ---")
        print(f"Result type: {type(result)}")
        print(f"Result attributes: {[a for a in dir(result) if not a.startswith('_')]}")

        # 获取res字典
        if hasattr(result, 'res'):
            res = result.res
            print(f"res keys: {list(res.keys())}")

            if 'markdown' in res:
                print(f"\nMarkdown:\n{res['markdown'][:2000]}")
            if 'tables' in res:
                print(f"\nTables count: {len(res['tables'])}")
                for j, table in enumerate(res['tables']):
                    print(f"  Table {j+1}: {str(table)[:500]}")

    return results


def test_structure_v3_detailed(image_path: str, label: str):
    """更详细的PP-StructureV3测试，输出原始结构化数据"""
    from paddleocr import PPStructureV3

    print(f"\n{'='*60}")
    print(f"[PP-StructureV3详细] {label}")
    print(f"图片: {os.path.basename(image_path)}")
    print(f"{'='*60}")

    start = time.time()
    pp_structure = PPStructureV3()

    results = list(pp_structure.predict(
        input=image_path,
        use_table_recognition=True,
    ))
    elapsed = time.time() - start

    print(f"\n耗时: {elapsed:.2f}s")

    # 保存详细结果
    output_dir = "/Users/dongsun/Github/OCR-Three-Layer-Hybrid/analysis"
    basename = os.path.splitext(os.path.basename(image_path))[0]

    for i, result in enumerate(results):
        if hasattr(result, 'res'):
            res = result.res
            output_file = os.path.join(output_dir, f"structure_{basename}_{i}.json")
            # Filter serializable data
            serializable = {}
            for k, v in res.items():
                try:
                    json.dumps(v)
                    serializable[k] = v
                except (TypeError, ValueError):
                    serializable[k] = str(v)
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(serializable, f, ensure_ascii=False, indent=2)
            print(f"详细结果已保存: {output_file}")

    return results


def compare_with_glm_ocr(label: str, ppocr_text: str):
    """与GLM-OCR已知错误对比"""
    print(f"\n--- 对比分析 [{label}] ---")

    if "户口本首页" in label:
        # 检查户主姓名
        if "王晨露" in ppocr_text:
            print("✅ 户主姓名 '王晨露' 正确识别")
        elif "王子龙" in ppocr_text:
            print("❌ 户主姓名仍然是 '王子龙' (列错位未修复)")
        else:
            # 搜索包含'王'的行
            for line in ppocr_text.split('\n'):
                if '王' in line and ('户主' in line or '姓名' in line):
                    print(f"⚠️ 包含'王'的行: {line.strip()}")

        # 检查其他内容
        for line in ppocr_text.split('\n'):
            if '户主' in line or '姓名' in line:
                print(f"  相关行: {line.strip()}")

    elif "结婚证" in label:
        # 检查身份证号
        import re
        id_match = re.search(r'(\d{17}[\dXx])', ppocr_text)
        if id_match:
            id_num = id_match.group(1)
            if id_num == "403211199305078253":
                print(f"✅ 身份证号正确: {id_num}")
            else:
                print(f"⚠️ 身份证号不匹配: {id_num} (期望: 403211199305078253)")
        else:
            # 搜索可能的身份证号
            all_nums = re.findall(r'\d{15,}', ppocr_text)
            print(f"❌ 未找到18位身份证号，附近数字: {all_nums}")

        # 检查结婚证字号
        if "鄂340321" in ppocr_text:
            print("✅ 结婚证字号 '鄂340321' 正确识别")
        elif "黔40321" in ppocr_text or "黔" in ppocr_text:
            print("❌ 结婚证字号仍然错误: '黔' (应为'鄂')")
        else:
            for line in ppocr_text.split('\n'):
                if '字号' in line or '鄂' in line or '黔' in line:
                    print(f"⚠️ 字号相关行: {line.strip()}")


def main():
    print("=" * 60)
    print("PP-OCRv6 + PP-StructureV3 vs GLM-OCR 对比测试")
    print("=" * 60)

    results = {}

    for label, image_path in ERROR_IMAGES.items():
        if not os.path.exists(image_path):
            print(f"\n❌ 图片不存在: {image_path}")
            continue

        # 测试1: 基础OCR
        try:
            ocr_text, ocr_lines = test_basic_ocr(image_path, label)
            compare_with_glm_ocr(label, ocr_text)
            results[label] = {
                "basic_ocr": ocr_text,
                "basic_ocr_lines": ocr_lines,
            }
        except Exception as e:
            print(f"基础OCR失败: {e}")
            results[label] = {"basic_ocr_error": str(e)}

        # 测试2: PP-StructureV3
        try:
            struct_results = test_structure_v3_detailed(image_path, label)
            results[label]["structure_v3"] = "completed"
        except Exception as e:
            print(f"PP-StructureV3失败: {e}")
            import traceback
            traceback.print_exc()
            results[label]["structure_v3_error"] = str(e)

    # 保存结果
    output_file = "/Users/dongsun/Github/OCR-Three-Layer-Hybrid/analysis/ppocr_vs_glm_comparison.json"

    # 清理不可序列化的内容
    save_data = {}
    for label, data in results.items():
        save_data[label] = {}
        for key, value in data.items():
            if isinstance(value, (str, list, dict, int, float, bool, type(None))):
                save_data[label][key] = value
            else:
                save_data[label][key] = str(value)

    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(save_data, f, ensure_ascii=False, indent=2)

    print(f"\n\n结果已保存: {output_file}")

    # 总结
    print(f"\n{'='*60}")
    print("测试总结")
    print(f"{'='*60}")
    print(f"测试图片数: {len(ERROR_IMAGES)}")
    print(f"成功数: {sum(1 for v in results.values() if 'basic_ocr' in v)}")


if __name__ == "__main__":
    main()

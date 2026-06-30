#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
字段级基线数据建设脚本

使用 doubao-seed-2.0-pro 云端大模型为基线图片提取字段值，
生成字段级 ground truth 供评估使用。

用法:
    python scripts/build_field_baseline.py                    # 全量运行
    python scripts/build_field_baseline.py --limit 5          # 前5张测试
    python scripts/build_field_baseline.py --case 202402190050  # 只处理指定Case
    python scripts/build_field_baseline.py --resume           # 从上次中断处继续
"""

import argparse
import base64
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests


# ========== 配置 ==========

DOUBAO_API_URL = "https://ark.cn-beijing.volces.com/api/plan/v3/chat/completions"
DOUBAO_API_KEY = "ark-1d99acf8-24c5-4359-b7f4-e0559112eb04-5b78d"
DOUBAO_MODEL = "doubao-seed-2.0-pro"

BASELINE_DIR = Path("/Users/dongsun/Github/sample-OCR/baseline_v3")
BASELINE_FILE = BASELINE_DIR / "baseline_8cases.json"
OUTPUT_FILE = BASELINE_DIR / "baseline_fields.json"

# 请求间隔（秒），避免触发限流
REQUEST_INTERVAL = 2.0
MAX_RETRIES = 3
TIMEOUT = 120.0


# ========== 文档类型 → 字段映射 ==========

DOC_TYPE_FIELDS: Dict[str, List[str]] = {
    "身份证": [
        "姓名", "性别", "民族", "出生", "住址",
        "公民身份号码", "签发机关", "有效期限",
    ],
    "户口本": [
        "户主姓名", "户号", "住址", "姓名",
        "与户主关系", "性别", "公民身份号码",
    ],
    "购房合同": [
        "合同编号", "买受人", "出卖人", "总价款",
        "签订日期", "房屋地址", "建筑面积",
    ],
    "存量房合同": [
        "合同编号", "买受人", "出卖人", "总价款",
        "签订日期", "房屋地址", "建筑面积",
    ],
    "发票": [
        "发票代码", "发票号码", "开票日期", "价税合计",
        "购买方名称", "购买方纳税人识别号",
        "销售方名称", "销售方纳税人识别号",
    ],
    "不动产权证书": [
        "证书号", "权利人", "共有情况", "不动产单元号",
        "房屋地址", "建筑面积", "用途",
    ],
    "结婚证": [
        "持证人", "登记日期", "结婚证字号",
        "男方姓名", "女方姓名",
        "男方身份证号", "女方身份证号",
    ],
    "离婚证": [
        "持证人", "登记日期", "离婚证字号",
    ],
    "资金监管协议": [
        "监管金额", "买方", "卖方", "监管机构",
    ],
    "离婚协议": [
        "男方姓名", "女方姓名", "离婚日期",
        "财产分割约定", "子女抚养",
    ],
}


# ========== 工具函数 ==========

def encode_image_base64(image_path: str) -> str:
    """将图片编码为base64字符串"""
    with open(image_path, 'rb') as f:
        return base64.b64encode(f.read()).decode('utf-8')


def build_extraction_prompt(doc_type: str, fields: List[str]) -> str:
    """构建字段提取Prompt"""
    fields_json = json.dumps({f: "" for f in fields}, ensure_ascii=False)
    return f"""请仔细阅读这张{doc_type}图片，提取以下字段值。

要求：
1. 以JSON格式返回，字段名必须与下面完全一致
2. 只提取图片中实际可见的、能确认的信息
3. 不可见或不确定的字段填空字符串 ""
4. 只返回JSON，不要添加任何其他文字说明

需要提取的字段：
{fields_json}"""


def call_doubao_api(image_path: str, doc_type: str, fields: List[str]) -> Dict[str, str]:
    """调用 doubao-seed-2.0-pro API 提取字段"""
    image_b64 = encode_image_base64(image_path)
    prompt = build_extraction_prompt(doc_type, fields)

    # 确定图片MIME类型
    suffix = Path(image_path).suffix.lower()
    mime_map = {'.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.png': 'image/png', '.bmp': 'image/bmp'}
    mime_type = mime_map.get(suffix, 'image/jpeg')

    payload = {
        "model": DOUBAO_MODEL,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{mime_type};base64,{image_b64}"
                        },
                    },
                ],
            }
        ],
        "temperature": 0.1,
        "max_tokens": 2048,
    }

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {DOUBAO_API_KEY}",
    }

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.post(
                DOUBAO_API_URL,
                headers=headers,
                json=payload,
                timeout=TIMEOUT,
            )
            resp.raise_for_status()
            data = resp.json()

            # 解析响应
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            return parse_fields_from_response(content, fields)

        except requests.exceptions.HTTPError as e:
            status_code = e.response.status_code if e.response else "N/A"
            print(f"  ⚠️  HTTP {status_code} (尝试 {attempt}/{MAX_RETRIES})")
            if status_code == 429:
                wait = 10 * attempt
                print(f"  ⏳ 限流，等待 {wait}s...")
                time.sleep(wait)
            elif attempt < MAX_RETRIES:
                time.sleep(3)
            else:
                print(f"  ❌ API调用失败: {e}")
                return {f: "" for f in fields}

        except Exception as e:
            print(f"  ⚠️  异常: {e} (尝试 {attempt}/{MAX_RETRIES})")
            if attempt < MAX_RETRIES:
                time.sleep(3)
            else:
                print(f"  ❌ 重试耗尽")
                return {f: "" for f in fields}

    return {f: "" for f in fields}


def parse_fields_from_response(content: str, fields: List[str]) -> Dict[str, str]:
    """从模型响应中解析字段JSON"""
    result = {f: "" for f in fields}

    # 尝试直接解析
    try:
        parsed = json.loads(content)
        if isinstance(parsed, dict):
            for f in fields:
                if f in parsed:
                    result[f] = str(parsed[f]).strip()
            return result
    except json.JSONDecodeError:
        pass

    # 尝试从markdown代码块中提取
    if "```json" in content:
        json_str = content.split("```json")[1].split("```")[0].strip()
        try:
            parsed = json.loads(json_str)
            if isinstance(parsed, dict):
                for f in fields:
                    if f in parsed:
                        result[f] = str(parsed[f]).strip()
                return result
        except json.JSONDecodeError:
            pass

    if "```" in content:
        json_str = content.split("```")[1].split("```")[0].strip()
        try:
            parsed = json.loads(json_str)
            if isinstance(parsed, dict):
                for f in fields:
                    if f in parsed:
                        result[f] = str(parsed[f]).strip()
                return result
        except json.JSONDecodeError:
            pass

    # 尝试找到第一个 { ... } 块
    start = content.find('{')
    end = content.rfind('}')
    if start >= 0 and end > start:
        try:
            parsed = json.loads(content[start:end + 1])
            if isinstance(parsed, dict):
                for f in fields:
                    if f in parsed:
                        result[f] = str(parsed[f]).strip()
                return result
        except json.JSONDecodeError:
            pass

    print(f"  ⚠️  无法解析响应为JSON: {content[:100]}...")
    return result


# ========== 主流程 ==========

def load_baseline() -> Dict:
    """加载基线数据"""
    with open(BASELINE_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)


def load_existing_output() -> Optional[Dict]:
    """加载已有输出（用于断点续传）"""
    if OUTPUT_FILE.exists():
        with open(OUTPUT_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return None


def get_doc_type_from_baseline(image_data: Dict) -> str:
    """从基线数据中获取图片的文档类型"""
    parsed = image_data.get("ocr_result", {}).get("parsed")
    if parsed is None:
        return "未知"
    return parsed.get("doc_type", "未知")


def save_output(output: Dict):
    """保存输出文件"""
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)


def build_field_baseline(
    limit: Optional[int] = None,
    case_filter: Optional[str] = None,
    resume: bool = False,
):
    """
    构建字段级基线数据

    Args:
        limit: 最多处理N张图片（调试用）
        case_filter: 只处理指定Case
        resume: 从上次中断处继续
    """
    print("=" * 60)
    print("字段级基线数据建设")
    print(f"模型: {DOUBAO_MODEL}")
    print(f"API: {DOUBAO_API_URL}")
    print(f"基线文件: {BASELINE_FILE}")
    print(f"输出文件: {OUTPUT_FILE}")
    print("=" * 60)

    # 加载基线
    baseline = load_baseline()
    cases = baseline.get("cases", [])

    # 加载已有输出（断点续传）
    existing = None
    if resume:
        existing = load_existing_output()
        if existing:
            print(f"\n📂 发现已有输出，将从中断处继续...")

    # 初始化输出
    output = {
        "created_at": existing.get("created_at", datetime.now().isoformat()) if existing else datetime.now().isoformat(),
        "model": DOUBAO_MODEL,
        "total_images": 0,
        "pending_review": True,
        "cases": [],
    }

    # 构建已有结果索引
    processed_keys = set()
    if existing:
        for case in existing.get("cases", []):
            for img in case.get("images", []):
                key = f"{case['case_id']}:{img['filename']}"
                processed_keys.add(key)
        output["cases"] = existing["cases"]

    # 统计
    total_count = 0
    processed_count = 0
    skipped_count = 0
    error_count = 0

    for case in cases:
        case_id = case.get("case_id", "")
        if case_filter and case_id != case_filter:
            continue

        images = case.get("images", [])
        print(f"\n📁 Case: {case_id} ({len(images)} 张图片)")

        case_output = None
        # 查找已有case输出
        if existing:
            for c in output["cases"]:
                if c.get("case_id") == case_id:
                    case_output = c
                    break

        if case_output is None:
            case_output = {"case_id": case_id, "images": []}
            output["cases"].append(case_output)

        for img_data in images:
            filename = img_data.get("filename", "")
            file_path = img_data.get("file_path", "")
            doc_type = get_doc_type_from_baseline(img_data)
            key = f"{case_id}:{filename}"

            total_count += 1

            # 跳过已处理（断点续传）
            if key in processed_keys:
                skipped_count += 1
                continue

            # 检查图片文件是否存在
            if not Path(file_path).exists():
                print(f"  ⏭️  {filename} — 文件不存在，跳过")
                case_output["images"].append({
                    "filename": filename,
                    "file_path": file_path,
                    "doc_type": doc_type,
                    "fields": {},
                    "error": "文件不存在",
                    "review_status": "skipped",
                })
                continue

            # 获取该类型需要的字段
            fields = DOC_TYPE_FIELDS.get(doc_type, [])
            if not fields:
                print(f"  ⏭️  {filename} — 未知文档类型({doc_type})，跳过")
                case_output["images"].append({
                    "filename": filename,
                    "file_path": file_path,
                    "doc_type": doc_type,
                    "fields": {},
                    "review_status": "skipped",
                    "reviewer_notes": f"文档类型 {doc_type} 无预定义字段",
                })
                continue

            # 调用API提取字段
            print(f"  🔄 [{total_count}] {filename} ({doc_type}) — 提取 {len(fields)} 个字段...")
            start_time = time.time()
            extracted_fields = call_doubao_api(file_path, doc_type, fields)
            elapsed = time.time() - start_time

            # 检查结果
            filled_count = sum(1 for v in extracted_fields.values() if v)
            print(f"  ✅ {elapsed:.1f}s — 提取 {filled_count}/{len(fields)} 个非空字段")

            if filled_count == 0:
                error_count += 1
                print(f"  ⚠️  所有字段为空！")

            # 保存结果
            case_output["images"].append({
                "filename": filename,
                "file_path": file_path,
                "doc_type": doc_type,
                "fields": extracted_fields,
                "review_status": "pending",
                "reviewer_notes": "",
            })
            processed_count += 1
            output["total_images"] += 1

            # 每张图片后保存（防止中断丢失）
            save_output(output)

            # 请求间隔
            if limit is None or processed_count < limit:
                time.sleep(REQUEST_INTERVAL)

            # 检查limit
            if limit and processed_count >= limit:
                print(f"\n⏹️  已处理 {processed_count} 张（达到限制）")
                save_output(output)
                return output

    # 最终保存
    save_output(output)

    # 打印统计
    print("\n" + "=" * 60)
    print("基线建设完成")
    print(f"  总计图片: {total_count}")
    print(f"  本次处理: {processed_count}")
    print(f"  跳过(已有): {skipped_count}")
    print(f"  提取失败: {error_count}")
    print(f"  输出文件: {OUTPUT_FILE}")
    print("=" * 60)

    return output


# ========== CLI ==========

def main():
    parser = argparse.ArgumentParser(description="字段级基线数据建设")
    parser.add_argument("--limit", type=int, help="最多处理N张图片")
    parser.add_argument("--case", type=str, help="只处理指定Case")
    parser.add_argument("--resume", action="store_true", help="从上次中断处继续")
    args = parser.parse_args()

    build_field_baseline(
        limit=args.limit,
        case_filter=args.case,
        resume=args.resume,
    )


if __name__ == "__main__":
    main()

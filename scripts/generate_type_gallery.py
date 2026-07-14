#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
生成文档类型分类预览 HTML

从回归测试结果 JSON 里每种文档类型取一张示例图片，生成可点击预览的 HTML。

用法:
    python3 scripts/generate_type_gallery.py
"""
import json
from collections import defaultdict
from pathlib import Path

# DocumentType 分类/细分分组（基础类型 → 细分类型列表）
TYPE_GROUPS = {
    "身份证": ["身份证-正面", "身份证-背面"],
    "户口本": ["户口本-首页", "户口本-个人页"],
    "结婚证": ["结婚证-内容页", "结婚证-盖章页"],
    "离婚证": ["离婚证-封面", "离婚证-内容页"],
    "不动产权证书": [
        "不动产权证书-首页",
        "不动产权证书-内容页",
        "不动产权证书-附图页",
    ],
    "发票": ["发票"],
    "购房合同": ["购房合同-内容页", "购房合同-签署页"],
    "存量房合同": ["存量房合同-首页", "存量房合同-内容页", "存量房合同-签署页"],
    "离婚协议书": ["离婚协议书"],
    "资金监管": [
        "资金监管协议-首页",
        "资金监管协议-信息页",
        "资金监管协议-签章页",
        "资金监管凭证",
    ],
    "其他": ["未知"],
}

SAMPLE_DIRS = [
    "/Users/dongsun/Github/sample-OCR/增量房图片资料/202406240010",
    "/Users/dongsun/Github/sample-OCR/增量房图片资料/202411070032",
    "/Users/dongsun/Github/sample-OCR/存量房图片资料/BBJZ-2026-0121076",
    "/Users/dongsun/Github/sample-OCR/存量房图片资料/BBJZ-2026-0129058",
]


def main():
    # 从回归测试结果找每种类型的示例图片
    result_file = Path("tests/results/regression_test_20260714.json")
    if not result_file.exists():
        print(f"错误: 找不到 {result_file}，请先跑回归测试")
        return

    d = json.load(open(result_file))

    # 按类型收集示例图片（每种类型只取第一张）
    type_to_image = {}
    for r in d["per_image"]:
        doc_type = r["doc_type"]
        if doc_type not in type_to_image:
            img_path = None
            for sample_dir in SAMPLE_DIRS:
                candidate = Path(sample_dir) / r["image"]
                if candidate.exists():
                    img_path = str(candidate)
                    break
            type_to_image[doc_type] = img_path

    # 复制图片到 docs/images/ 并用相对路径
    images_dir = Path("docs/images")
    images_dir.mkdir(parents=True, exist_ok=True)

    import shutil
    type_to_rel_path = {}
    for doc_type, abs_path in type_to_image.items():
        if abs_path:
            # 文件名：类型名_原文件名（避免重复）
            safe_name = doc_type.replace("-", "_").replace("/", "_")
            src = Path(abs_path)
            dst = images_dir / f"{safe_name}{src.suffix}"
            if not dst.exists():
                shutil.copy2(abs_path, dst)
            type_to_rel_path[doc_type] = f"images/{dst.name}"
        else:
            type_to_rel_path[doc_type] = None

    # 生成 HTML
    html = generate_html(type_to_rel_path)

    out_path = Path("docs/type_gallery.html")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html)
    print(f"✅ HTML 已生成: {out_path}")
    print(f"共 {len(type_to_image)} 种类型，覆盖 {sum(1 for v in type_to_image.values() if v)} 种有示例图片")
    print(f"图片已复制到: {images_dir}")
    print(f"\n查看方式: open {out_path} （相对路径，需从项目根目录打开）")


def generate_html(type_to_image):
    """生成 HTML 内容"""
    group_html = []
    for group_name, types in TYPE_GROUPS.items():
        cards = []
        for t in types:
            img_path = type_to_image.get(t)
            if img_path:
                # 用绝对路径（file:// 协议或 HTTP 相对路径）
                card = f"""
        <div class="card">
          <div class="type-name">{t}</div>
          <a href="{img_path}" target="_blank" rel="noopener">
            <img src="{img_path}" alt="{t}" loading="lazy" onerror="this.style.display='none';this.nextElementSibling.style.display='block';">
            <div class="fallback" style="display:none;">📄 点击查看</div>
          </a>
        </div>"""
            else:
                card = f"""
        <div class="card no-image">
          <div class="type-name">{t}</div>
          <div class="no-sample">（无示例）</div>
        </div>"""
            cards.append(card)

        group_html.append(f"""
    <section class="group">
      <h2>{group_name}</h2>
      <div class="cards">
        {''.join(cards)}
      </div>
    </section>""")

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>OCR 文档类型分类预览</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
    background: #f5f5f7;
    color: #1d1d1f;
    padding: 2rem;
    line-height: 1.6;
  }}
  h1 {{
    font-size: 2rem;
    margin-bottom: 0.5rem;
    color: #1d1d1f;
  }}
  .subtitle {{
    color: #86868b;
    margin-bottom: 2rem;
    font-size: 0.95rem;
  }}
  .group {{
    background: white;
    border-radius: 12px;
    padding: 1.5rem;
    margin-bottom: 1.5rem;
    box-shadow: 0 2px 8px rgba(0,0,0,0.04);
  }}
  .group h2 {{
    font-size: 1.25rem;
    margin-bottom: 1rem;
    color: #1d1d1f;
    border-left: 4px solid #0071e3;
    padding-left: 0.75rem;
  }}
  .cards {{
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
    gap: 1rem;
  }}
  .card {{
    border: 1px solid #e5e5ea;
    border-radius: 8px;
    overflow: hidden;
    transition: transform 0.2s, box-shadow 0.2s;
    background: #fafafa;
  }}
  .card:hover {{
    transform: translateY(-2px);
    box-shadow: 0 4px 12px rgba(0,0,0,0.1);
  }}
  .card.no-image {{
    opacity: 0.5;
  }}
  .type-name {{
    padding: 0.5rem 0.75rem;
    font-weight: 600;
    font-size: 0.9rem;
    background: #f5f5f7;
    border-bottom: 1px solid #e5e5ea;
  }}
  .card a {{
    display: block;
    text-decoration: none;
    color: inherit;
  }}
  .card img {{
    width: 100%;
    height: 180px;
    object-fit: cover;
    display: block;
    background: #e5e5ea;
  }}
  .fallback {{
    height: 180px;
    display: flex;
    align-items: center;
    justify-content: center;
    background: #f5f5f7;
    color: #86868b;
    font-size: 0.9rem;
  }}
  .no-sample {{
    height: 180px;
    display: flex;
    align-items: center;
    justify-content: center;
    color: #86868b;
    font-size: 0.85rem;
  }}
  .stats {{
    display: flex;
    gap: 2rem;
    margin-bottom: 2rem;
    flex-wrap: wrap;
  }}
  .stat {{
    background: white;
    padding: 1rem 1.5rem;
    border-radius: 8px;
    box-shadow: 0 2px 8px rgba(0,0,0,0.04);
  }}
  .stat-label {{
    font-size: 0.85rem;
    color: #86868b;
  }}
  .stat-value {{
    font-size: 1.5rem;
    font-weight: 600;
    color: #0071e3;
  }}
</style>
</head>
<body>
<h1>📚 OCR 文档类型分类预览</h1>
<p class="subtitle">基于回归测试结果（119 张业务样本）生成的分类/细分类型示例库</p>

<div class="stats">
  <div class="stat">
    <div class="stat-label">总类型数</div>
    <div class="stat-value">{len(type_to_image)}</div>
  </div>
  <div class="stat">
    <div class="stat-label">有示例图片</div>
    <div class="stat-value">{sum(1 for v in type_to_image.values() if v)}</div>
  </div>
  <div class="stat">
    <div class="stat-label">基础分类</div>
    <div class="stat-value">{len(TYPE_GROUPS)}</div>
  </div>
</div>

{''.join(group_html)}

<script>
  // 点击图片在新标签页打开（默认行为，保留备用）
  document.querySelectorAll('.card img').forEach(img => {{
    img.addEventListener('click', e => {{
      e.preventDefault();
      window.open(img.closest('a').href, '_blank');
    }});
  }});
</script>
</body>
</html>
"""


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
字段级基线数据核验工具 - GUI界面

用法: python3 scripts/field_baseline_reviewer.py

功能:
- 左侧显示图片，右侧显示doubao提取的字段值
- 对照图片修改字段值（修正提取错误、补充遗漏字段）
- 标记审核状态（通过/已修正/跳过）
- 支持键盘快捷键导航
- 保存修改后的 baseline_fields.json
"""

import json
import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path
from PIL import Image, ImageTk
import sys

# 数据文件路径
BASELINE_DIR = Path("/Users/dongsun/Github/sample-OCR/baseline_v3")
BASELINE_FILE = BASELINE_DIR / "baseline_8cases.json"
FIELDS_FILE = BASELINE_DIR / "baseline_fields.json"

# 审核状态选项
REVIEW_STATUSES = {
    "pending": "⏳ 待审核",
    "approved": "✅ 已通过",
    "corrected": "🔧 已修正",
    "skipped": "⏭️ 跳过",
}

# 状态颜色
STATUS_COLORS = {
    "pending": "#f59e0b",
    "approved": "#10b981",
    "corrected": "#3b82f6",
    "skipped": "#6b7280",
}


class FieldBaselineReviewer:
    def __init__(self, root):
        self.root = root
        self.root.title("字段级基线数据核验工具")
        self.root.geometry("1600x950")

        # 加载数据
        self.fields_data = self.load_json(FIELDS_FILE)
        self.baseline_data = self.load_json(BASELINE_FILE)

        # 建立基线索引（file_path → parsed info）
        self.baseline_index = {}
        for case in self.baseline_data.get("cases", []):
            for img in case.get("images", []):
                fp = img.get("file_path", "")
                self.baseline_index[fp] = img

        # 扁平化所有字段数据中的图片
        self.all_images = []
        for case in self.fields_data.get("cases", []):
            for img in case.get("images", []):
                self.all_images.append({
                    "case_id": case["case_id"],
                    "filename": img.get("filename", ""),
                    "file_path": img.get("file_path", ""),
                    "doc_type": img.get("doc_type", "未知"),
                    "fields": img.get("fields", {}),
                    "review_status": img.get("review_status", "pending"),
                    "reviewer_notes": img.get("reviewer_notes", ""),
                    "error": img.get("error", ""),
                })

        self.current_idx = 0
        self.modified = False
        self.field_entries = {}  # 字段名 → Entry widget

        # 缩放状态
        self.zoom_level = 1.0
        self.original_image = None  # 缓存原始 PIL Image

        self.setup_ui()
        self.root.update_idletasks()  # 确保 canvas 尺寸已计算
        self.show_current_image()

    def load_json(self, path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def save_data(self):
        """保存字段基线数据"""
        # 将当前编辑的字段写回
        self.sync_current_fields()

        with open(FIELDS_FILE, "w", encoding="utf-8") as f:
            json.dump(self.fields_data, f, ensure_ascii=False, indent=2)
        self.modified = False
        messagebox.showinfo("保存成功", f"已保存到:\n{FIELDS_FILE}")

    def sync_current_fields(self):
        """将当前图片的UI字段值同步回数据"""
        if not self.all_images:
            return
        item = self.all_images[self.current_idx]

        # 同步字段值
        for field_name, entry in self.field_entries.items():
            value = entry.get().strip()
            item["fields"][field_name] = value

        # 同步审核状态
        status_key = self.status_var.get()
        item["review_status"] = status_key

        # 同步备注
        item["reviewer_notes"] = self.notes_var.get().strip()

        # 更新fields_data中对应的条目
        for case in self.fields_data.get("cases", []):
            if case["case_id"] == item["case_id"]:
                for img in case.get("images", []):
                    if img.get("filename") == item["filename"]:
                        img["fields"] = item["fields"]
                        img["review_status"] = item["review_status"]
                        img["reviewer_notes"] = item["reviewer_notes"]
                        break
                break

    def setup_ui(self):
        """设置界面"""
        # ===== 顶部控制栏 =====
        control_frame = ttk.Frame(self.root)
        control_frame.pack(fill=tk.X, padx=10, pady=5)

        ttk.Button(control_frame, text="⬅ 上一张", command=self.prev_image).pack(side=tk.LEFT, padx=3)
        ttk.Button(control_frame, text="下一张 ➡", command=self.next_image).pack(side=tk.LEFT, padx=3)

        # 跳转到
        ttk.Label(control_frame, text="跳转:").pack(side=tk.LEFT, padx=(15, 3))
        self.jump_var = tk.StringVar()
        jump_entry = ttk.Entry(control_frame, textvariable=self.jump_var, width=6)
        jump_entry.pack(side=tk.LEFT, padx=3)
        jump_entry.bind("<Return>", self.jump_to)

        self.position_label = ttk.Label(control_frame, text="", font=("Arial", 12, "bold"))
        self.position_label.pack(side=tk.LEFT, padx=15)

        # 审核统计
        self.stats_label = ttk.Label(control_frame, text="", font=("Arial", 10))
        self.stats_label.pack(side=tk.LEFT, padx=10)

        ttk.Button(control_frame, text="💾 保存 (Ctrl+S)", command=self.save_data).pack(side=tk.RIGHT, padx=5)

        # 缩放控制
        ttk.Separator(control_frame, orient=tk.VERTICAL).pack(side=tk.RIGHT, fill=tk.Y, padx=8)
        ttk.Button(control_frame, text="🔍+", command=self.zoom_in, width=4).pack(side=tk.RIGHT, padx=2)
        ttk.Button(control_frame, text="🔍−", command=self.zoom_out, width=4).pack(side=tk.RIGHT, padx=2)
        ttk.Button(control_frame, text="↺", command=self.zoom_reset, width=3).pack(side=tk.RIGHT, padx=2)
        self.zoom_label = ttk.Label(control_frame, text="100%", font=("Arial", 10))
        self.zoom_label.pack(side=tk.RIGHT, padx=5)

        # 筛选
        ttk.Label(control_frame, text="筛选:").pack(side=tk.RIGHT, padx=(10, 3))
        self.filter_var = tk.StringVar(value="all")
        filter_combo = ttk.Combobox(control_frame, textvariable=self.filter_var,
                                     values=["all", "pending", "approved", "corrected", "skipped"],
                                     state="readonly", width=10)
        filter_combo.pack(side=tk.RIGHT, padx=3)
        filter_combo.bind("<<ComboboxSelected>>", lambda e: self.apply_filter())

        # ===== 主内容区域 =====
        main_frame = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        # ----- 左侧：图片 -----
        left_frame = ttk.LabelFrame(main_frame, text="图片预览")
        main_frame.add(left_frame, weight=1)

        self.image_canvas = tk.Canvas(left_frame, bg="#f0f0f0")
        self.image_canvas.pack(fill=tk.BOTH, expand=True)

        # ----- 右侧：字段编辑 -----
        right_frame = ttk.Frame(main_frame)
        main_frame.add(right_frame, weight=1)

        # 业务信息
        info_frame = ttk.LabelFrame(right_frame, text="图片信息")
        info_frame.pack(fill=tk.X, padx=5, pady=3)

        self.info_label = ttk.Label(info_frame, text="", font=("Arial", 10), wraplength=500)
        self.info_label.pack(anchor=tk.W, padx=10, pady=5)

        # 审核状态
        status_frame = ttk.LabelFrame(right_frame, text="审核状态")
        status_frame.pack(fill=tk.X, padx=5, pady=3)

        status_inner = ttk.Frame(status_frame)
        status_inner.pack(fill=tk.X, padx=10, pady=5)

        self.status_var = tk.StringVar()
        for key, label in REVIEW_STATUSES.items():
            rb = ttk.Radiobutton(status_inner, text=label, variable=self.status_var,
                                  value=key, command=self.on_status_change)
            rb.pack(side=tk.LEFT, padx=8)

        # 备注
        notes_frame = ttk.LabelFrame(right_frame, text="备注")
        notes_frame.pack(fill=tk.X, padx=5, pady=3)

        self.notes_var = tk.StringVar()
        notes_entry = ttk.Entry(notes_frame, textvariable=self.notes_var, font=("Arial", 10))
        notes_entry.pack(fill=tk.X, padx=10, pady=5)
        notes_entry.bind("<KeyRelease>", lambda e: self.mark_modified())

        # 字段编辑区域（可滚动）
        fields_outer = ttk.LabelFrame(right_frame, text="提取字段（对照图片修改）")
        fields_outer.pack(fill=tk.BOTH, expand=True, padx=5, pady=3)

        # Canvas + Scrollbar for scrollable fields
        canvas_frame = ttk.Frame(fields_outer)
        canvas_frame.pack(fill=tk.BOTH, expand=True)

        self.fields_canvas = tk.Canvas(canvas_frame)
        scrollbar = ttk.Scrollbar(canvas_frame, orient=tk.VERTICAL, command=self.fields_canvas.yview)
        self.fields_inner = ttk.Frame(self.fields_canvas)
        self.canvas_window_id = self.fields_canvas.create_window(
            (0, 0), window=self.fields_inner, anchor="nw"
        )
        self._bind_fields_configure()
        self.fields_canvas.configure(yscrollcommand=scrollbar.set)

        self.fields_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # 鼠标滚轮绑定
        self.fields_canvas.bind_all("<MouseWheel>", self._on_mousewheel)

        # 文件路径
        path_frame = ttk.LabelFrame(right_frame, text="文件路径")
        path_frame.pack(fill=tk.X, padx=5, pady=3)

        self.path_label = ttk.Label(path_frame, text="", foreground="blue", font=("Arial", 9))
        self.path_label.pack(anchor=tk.W, padx=10, pady=3)

    def _bind_fields_configure(self):
        """绑定 fields_inner 的 <Configure> 事件以更新 scrollregion"""
        self.fields_inner.bind(
            "<Configure>",
            lambda e: self.fields_canvas.configure(scrollregion=self.fields_canvas.bbox("all"))
        )

    def _on_mousewheel(self, event):
        """滚轮：Ctrl+滚轮=缩放，普通滚轮=字段区滚动"""
        if event.state & 0x4:  # Ctrl 按下
            if event.delta > 0:
                self.zoom_in()
            else:
                self.zoom_out()
            return "break"
        self.fields_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def zoom_in(self):
        self.zoom_to(self.zoom_level * 1.25)

    def zoom_out(self):
        self.zoom_to(self.zoom_level / 1.25)

    def zoom_reset(self):
        self.zoom_to(1.0)

    def zoom_to(self, level):
        self.zoom_level = max(0.1, min(5.0, level))
        self.zoom_label.config(text=f"{int(self.zoom_level * 100)}%")
        if self.original_image is not None:
            self.display_image(self._current_image_path)

    def show_current_image(self):
        """显示当前图片及其字段"""
        if not self.all_images:
            return

        item = self.all_images[self.current_idx]

        # 更新位置
        self.position_label.config(text=f"{self.current_idx + 1} / {len(self.all_images)}")

        # 更新跳转框
        self.jump_var.set(str(self.current_idx + 1))

        # 更新统计
        self.update_stats()

        # 更新图片信息
        baseline_info = self.baseline_index.get(item["file_path"], {})
        parsed = baseline_info.get("ocr_result", {}).get("parsed") or {}
        page_status = parsed.get("page_status", "")
        info_text = f"业务: {item['case_id']}  |  类型: {item['doc_type']}  |  页面: {page_status}"
        if item.get("error"):
            info_text += f"  |  ❗ {item['error']}"
        self.info_label.config(text=info_text)

        # 更新审核状态
        self.status_var.set(item.get("review_status", "pending"))

        # 更新备注
        self.notes_var.set(item.get("reviewer_notes", ""))

        # 更新文件路径
        self.path_label.config(text=item["file_path"])

        # 清空并重建字段编辑区（彻底清除旧字段和 Canvas 窗口）
        self.fields_canvas.delete(self.canvas_window_id)
        self.fields_inner.destroy()
        self.field_entries.clear()

        # 重建 fields_inner 和 Canvas 窗口
        self.fields_inner = ttk.Frame(self.fields_canvas)
        self.canvas_window_id = self.fields_canvas.create_window(
            (0, 0), window=self.fields_inner, anchor="nw"
        )
        self._bind_fields_configure()
        self.fields_canvas.yview_moveto(0)  # 重置滚动位置
        self.fields_canvas.update_idletasks()

        # 创建字段输入行
        fields = item.get("fields", {})
        if not fields:
            ttk.Label(self.fields_inner, text="(无字段数据 — 可能为未知类型或提取失败)",
                       foreground="gray").pack(padx=10, pady=20)
        else:
            for field_name, field_value in fields.items():
                row = ttk.Frame(self.fields_inner)
                row.pack(fill=tk.X, padx=10, pady=3)

                # 字段名标签
                name_label = ttk.Label(row, text=f"{field_name}:", width=16,
                                        font=("Arial", 10, "bold"), anchor=tk.E)
                name_label.pack(side=tk.LEFT, padx=(0, 8))

                # 字段值输入框
                entry = ttk.Entry(row, font=("Arial", 10))
                entry.insert(0, field_value if field_value else "")
                entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
                entry.bind("<KeyRelease>", lambda e: self.mark_modified())

                # 清空按钮
                clear_btn = ttk.Button(row, text="✕", width=3,
                                        command=lambda e=entry: (e.delete(0, tk.END), self.mark_modified()))
                clear_btn.pack(side=tk.RIGHT)

                self.field_entries[field_name] = entry

        # 高亮当前状态
        self.root.configure(bg=STATUS_COLORS.get(item.get("review_status", "pending"), "#f0f0f0"))

        # 切换图片时重置缩放缓存
        self.original_image = None
        self._current_image_path = None

        # 显示图片
        self.display_image(item["file_path"])

    def display_image(self, image_path):
        """在canvas中显示图片（支持缩放）"""
        try:
            # 首次加载或切换图片时，读取原始图片
            if self.original_image is None or getattr(self, '_current_image_path', None) != image_path:
                self.original_image = Image.open(image_path)
                self._current_image_path = image_path

            canvas_width = self.image_canvas.winfo_width()
            canvas_height = self.image_canvas.winfo_height()

            if canvas_width < 100:
                canvas_width = 700
            if canvas_height < 100:
                canvas_height = 800

            # 按原始比例适配 canvas
            img_ratio = self.original_image.width / self.original_image.height
            canvas_ratio = canvas_width / canvas_height

            if img_ratio > canvas_ratio:
                new_width = canvas_width
                new_height = int(canvas_width / img_ratio)
            else:
                new_height = canvas_height
                new_width = int(canvas_height * img_ratio)

            # 应用缩放
            zoom_w = max(1, int(new_width * self.zoom_level))
            zoom_h = max(1, int(new_height * self.zoom_level))
            img = self.original_image.resize((zoom_w, zoom_h), Image.Resampling.LANCZOS)
            self.photo = ImageTk.PhotoImage(img)

            self.image_canvas.delete("all")
            self.image_canvas.create_image(
                canvas_width // 2, canvas_height // 2,
                image=self.photo, anchor=tk.CENTER
            )
        except Exception as e:
            self.image_canvas.delete("all")
            self.image_canvas.create_text(
                350, 400,
                text=f"无法加载图片:\n{e}",
                font=("Arial", 12), fill="red"
            )

    def _sync_and_update_index(self, new_idx):
        """先同步当前图片的字段值到数据，再更新索引"""
        if self.field_entries:
            self.sync_current_fields()
        self.current_idx = new_idx
        self.show_current_image()

    def prev_image(self):
        if self.current_idx > 0:
            self._sync_and_update_index(self.current_idx - 1)

    def next_image(self):
        if self.current_idx < len(self.all_images) - 1:
            self._sync_and_update_index(self.current_idx + 1)

    def jump_to(self, event=None):
        try:
            idx = int(self.jump_var.get()) - 1
            if 0 <= idx < len(self.all_images) and idx != self.current_idx:
                self._sync_and_update_index(idx)
        except ValueError:
            pass

    def mark_modified(self):
        self.modified = True

    def on_status_change(self):
        self.mark_modified()

    def update_stats(self):
        """更新审核统计"""
        counts = {"pending": 0, "approved": 0, "corrected": 0, "skipped": 0}
        for item in self.all_images:
            s = item.get("review_status", "pending")
            if s in counts:
                counts[s] += 1
        total = len(self.all_images)
        done = counts["approved"] + counts["corrected"] + counts["skipped"]
        self.stats_label.config(
            text=f"已审核: {done}/{total}  |  ✅{counts['approved']} 🔧{counts['corrected']} ⏭️{counts['skipped']} ⏳{counts['pending']}"
        )

    def apply_filter(self):
        """暂时不支持筛选，保留接口"""
        pass

    def on_closing(self):
        if self.modified:
            if messagebox.askyesno("未保存的修改", "有未保存的修改，是否保存？"):
                self.save_data()
        self.root.destroy()


def main():
    if not FIELDS_FILE.exists():
        print(f"错误: 字段基线文件不存在: {FIELDS_FILE}")
        print("请先运行: python3 scripts/build_field_baseline.py")
        sys.exit(1)

    if not BASELINE_FILE.exists():
        print(f"错误: 基线文件不存在: {BASELINE_FILE}")
        sys.exit(1)

    root = tk.Tk()
    app = FieldBaselineReviewer(root)
    root.protocol("WM_DELETE_WINDOW", app.on_closing)

    # 键盘快捷键
    root.bind("<Left>", lambda e: app.prev_image())
    root.bind("<Right>", lambda e: app.next_image())
    root.bind("<Control-s>", lambda e: app.save_data())
    root.bind("<Control-S>", lambda e: app.save_data())
    root.bind("<Control-plus>", lambda e: app.zoom_in())
    root.bind("<Control-equal>", lambda e: app.zoom_in())
    root.bind("<Control-minus>", lambda e: app.zoom_out())
    root.bind("<Control-0>", lambda e: app.zoom_reset())

    root.mainloop()


if __name__ == "__main__":
    main()

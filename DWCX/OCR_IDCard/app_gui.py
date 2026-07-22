import os
import tkinter as tk
from tkinter import filedialog, messagebox
from PIL import Image
import customtkinter as ctk
from tkinterdnd2 import DND_FILES, TkinterDnD

from rapidocr import RapidOCR
from database import *
from id_card_parser import parse_id_card_info

engine = RapidOCR()

class IDCardOCRApp(TkinterDnD.Tk):
    def __init__(self):
        super().__init__()

        self.title("身份证OCR管理系统")
        self.geometry("1180x760")
        self.minsize(1100, 700)

        ctk.set_appearance_mode("light")
        ctk.set_default_color_theme("blue")

        self.bg_color = "#F5F7FB"
        self.card_color = "#FFFFFF"
        self.border_color = "#E3E8F0"
        self.primary_color = "#2563EB"
        self.primary_hover = "#1D4ED8"
        self.text_color = "#1F2937"
        self.sub_text_color = "#6B7280"
        self.danger_color = "#EF4444"

        self.configure(bg=self.bg_color)

        self.selected_image_path = tk.StringVar(value="")
        self.current_page = "upload"
        self.selected_record = None

        self.current_page_num = 1
        self.page_size = 20
        self.total_pages = 1
        self.total_count = 0
        
        self.search_current_page = 1
        self.search_total_pages = 1
        self.search_total_count = 0

        self.db_ok = init_db()

        self.build_layout()

        self.drop_target_register(DND_FILES)
        self.dnd_bind('<<Drop>>', self.on_drop)

    def build_layout(self):
        self.build_title_bar()
        self.build_nav_bar()

        self.main_area = ctk.CTkFrame(
            self,
            fg_color=self.bg_color,
            corner_radius=0
        )
        self.main_area.pack(fill="both", expand=True, padx=28, pady=22)

        self.show_upload_page()

    def build_title_bar(self):
        title_bar = ctk.CTkFrame(
            self,
            height=58,
            fg_color="#FFFFFF",
            corner_radius=0
        )
        title_bar.pack(fill="x", side="top")

        logo = ctk.CTkLabel(
            title_bar,
            text="◎",
            font=("Microsoft YaHei UI", 24, "bold"),
            text_color=self.primary_color
        )
        logo.pack(side="left", padx=(26, 8))

        title = ctk.CTkLabel(
            title_bar,
            text="身份证OCR管理系统",
            font=("Microsoft YaHei UI", 18, "bold"),
            text_color=self.text_color
        )
        title.pack(side="left")

    def build_nav_bar(self):
        self.nav_bar = ctk.CTkFrame(
            self,
            height=64,
            fg_color="#FFFFFF",
            corner_radius=0
        )
        self.nav_bar.pack(fill="x", side="top")

        self.nav_buttons = {}

        nav_items = [
            ("upload", "上传身份证", "📄"),
            ("list", "记录列表", "▤"),
            ("search", "搜索记录", "🔍"),
        ]

        for key, text, icon in nav_items:
            btn = ctk.CTkButton(
                self.nav_bar,
                text=f"{icon}  {text}",
                width=160,
                height=46,
                fg_color="transparent",
                hover_color="#EEF4FF",
                text_color=self.sub_text_color,
                font=("Microsoft YaHei UI", 15),
                corner_radius=0,
                command=lambda k=key: self.switch_page(k)
            )
            btn.pack(side="left", padx=(18 if key == "upload" else 4, 4), pady=(10, 0))
            self.nav_buttons[key] = btn

    def update_nav_state(self, active_key):
        for key, btn in self.nav_buttons.items():
            if key == active_key:
                btn.configure(
                    text_color=self.primary_color,
                    fg_color="#EEF4FF",
                    font=("Microsoft YaHei UI", 15, "bold")
                )
            else:
                btn.configure(
                    text_color=self.sub_text_color,
                    fg_color="transparent",
                    font=("Microsoft YaHei UI", 15)
                )

    def switch_page(self, key):
        self.current_page = key

        if key == "upload":
            self.show_upload_page()
        elif key == "list":
            self.show_list_page()
        elif key == "search":
            self.show_search_page()

    def clear_main_area(self):
        for widget in self.main_area.winfo_children():
            widget.destroy()

    def create_main_card(self):
        card = ctk.CTkFrame(
            self.main_area,
            fg_color=self.card_color,
            corner_radius=14,
            border_width=1,
            border_color=self.border_color
        )
        card.pack(fill="both", expand=True)
        return card

    def show_upload_page(self):
        self.clear_main_area()
        self.update_nav_state("upload")

        card = self.create_main_card()

        header = ctk.CTkFrame(card, fg_color="transparent")
        header.pack(fill="x", padx=34, pady=(30, 10))

        title = ctk.CTkLabel(
            header,
            text="上传并识别身份证",
            font=("Microsoft YaHei UI", 24, "bold"),
            text_color=self.text_color
        )
        title.pack(anchor="w")

        subtitle = ctk.CTkLabel(
            header,
            text="上传身份证正反面图片，系统将自动识别并提取信息。",
            font=("Microsoft YaHei UI", 14),
            text_color=self.sub_text_color
        )
        subtitle.pack(anchor="w", pady=(8, 0))

        input_area = ctk.CTkFrame(card, fg_color="transparent")
        input_area.pack(fill="x", padx=34, pady=(20, 8))

        label = ctk.CTkLabel(
            input_area,
            text="身份证图片路径",
            font=("Microsoft YaHei UI", 14, "bold"),
            text_color=self.text_color
        )
        label.pack(anchor="w", pady=(0, 8))

        path_row = ctk.CTkFrame(input_area, fg_color="transparent")
        path_row.pack(fill="x")

        path_entry = ctk.CTkEntry(
            path_row,
            textvariable=self.selected_image_path,
            height=44,
            corner_radius=8,
            border_width=1,
            border_color="#CBD5E1",
            fg_color="#FFFFFF",
            placeholder_text="请选择身份证图片文件（支持 JPG / PNG / JPEG 格式）",
            font=("Microsoft YaHei UI", 14)
        )
        path_entry.pack(side="left", fill="x", expand=True)

        browse_btn = ctk.CTkButton(
            path_row,
            text="📁  浏览",
            width=120,
            height=44,
            corner_radius=8,
            fg_color="#FFFFFF",
            hover_color="#F1F5F9",
            border_width=1,
            border_color="#CBD5E1",
            text_color=self.text_color,
            font=("Microsoft YaHei UI", 14),
            command=self.browse_image
        )
        browse_btn.pack(side="left", padx=(16, 0))

        btn_frame = ctk.CTkFrame(card, fg_color="transparent")
        btn_frame.pack(pady=(18, 24))

        upload_btn = ctk.CTkButton(
            btn_frame,
            text="↑  上传并解析",
            width=170,
            height=48,
            corner_radius=9,
            fg_color=self.primary_color,
            hover_color=self.primary_hover,
            font=("Microsoft YaHei UI", 15, "bold"),
            command=self.parse_image
        )
        upload_btn.pack(side="left", padx=(0, 12))

        save_btn = ctk.CTkButton(
            btn_frame,
            text="💾  保存到数据库",
            width=170,
            height=48,
            corner_radius=9,
            fg_color="#059669",
            hover_color="#047857",
            font=("Microsoft YaHei UI", 15, "bold"),
            command=self.save_to_db
        )
        save_btn.pack(side="left", padx=(0, 12))

        batch_btn = ctk.CTkButton(
            btn_frame,
            text="📦  批量上传",
            width=170,
            height=48,
            corner_radius=9,
            fg_color="#7C3AED",
            hover_color="#6D28D9",
            font=("Microsoft YaHei UI", 15, "bold"),
            command=self.batch_upload
        )
        batch_btn.pack(side="left")

        content = ctk.CTkFrame(card, fg_color="transparent")
        content.pack(fill="both", expand=True, padx=34, pady=(0, 26))

        left = ctk.CTkFrame(
            content,
            fg_color="#FFFFFF",
            corner_radius=12,
            border_width=1,
            border_color=self.border_color
        )
        left.pack(side="left", fill="both", expand=True, padx=(0, 10))

        right = ctk.CTkFrame(
            content,
            fg_color="#FFFFFF",
            corner_radius=12,
            border_width=1,
            border_color=self.border_color
        )
        right.pack(side="left", fill="both", expand=True, padx=(10, 0))

        self.build_preview_panel(left)
        self.build_result_panel(right)

        footer = ctk.CTkFrame(card, height=48, fg_color="#F8FAFC", corner_radius=0)
        footer.pack(fill="x", side="bottom")

        footer_text = ctk.CTkLabel(
            footer,
            text="🛡  为保障数据安全，图片仅在本地处理，不会上传到服务器。",
            font=("Microsoft YaHei UI", 13),
            text_color="#64748B"
        )
        footer_text.pack(pady=13)

    def build_preview_panel(self, parent):
        title = ctk.CTkLabel(
            parent,
            text="身份证图片预览",
            font=("Microsoft YaHei UI", 16, "bold"),
            text_color=self.text_color
        )
        title.pack(anchor="w", padx=24, pady=(22, 12))

        self.preview_box = ctk.CTkFrame(
            parent,
            fg_color="#F8FAFC",
            corner_radius=12,
            border_width=1,
            border_color="#CBD5E1"
        )
        self.preview_box.pack(fill="both", expand=True, padx=24, pady=(0, 24))

        self.preview_label = ctk.CTkLabel(
            self.preview_box,
            text="＋\n\n拖拽图片到此处\n或点击上方“浏览”按钮选择文件\n\n支持 JPG / PNG / JPEG 格式，大小不超过 10MB",
            font=("Microsoft YaHei UI", 15),
            text_color="#64748B",
            justify="center"
        )
        self.preview_label.pack(expand=True)

    def build_result_panel(self, parent):
        top = ctk.CTkFrame(parent, fg_color="transparent")
        top.pack(fill="x", padx=24, pady=(22, 12))

        title = ctk.CTkLabel(
            top,
            text="识别结果（自动提取，可编辑）",
            font=("Microsoft YaHei UI", 16, "bold"),
            text_color=self.text_color
        )
        title.pack(side="left")

        self.status_badge = ctk.CTkLabel(
            top,
            text="● 待上传图片",
            width=110,
            height=28,
            fg_color="#F1F5F9",
            corner_radius=14,
            text_color="#64748B",
            font=("Microsoft YaHei UI", 12)
        )
        self.status_badge.pack(side="right")

        result_card = ctk.CTkFrame(
            parent,
            fg_color="#FFFFFF",
            corner_radius=10,
            border_width=1,
            border_color="#E2E8F0"
        )
        result_card.pack(fill="both", expand=True, padx=24, pady=(0, 24))

        self.result_vars = {
            "姓名": tk.StringVar(value=""),
            "身份证号": tk.StringVar(value=""),
            "签发机关": tk.StringVar(value=""),
            "有效期限": tk.StringVar(value=""),
            "有效期类型": tk.StringVar(value="")
        }

        self.result_entries = {}

        icons = {
            "姓名": "👤",
            "身份证号": "▣",
            "签发机关": "🏛",
            "有效期限": "📅",
            "有效期类型": "🏷"
        }

        for idx, key in enumerate(self.result_vars.keys()):
            row = ctk.CTkFrame(result_card, fg_color="transparent")
            row.pack(fill="x", padx=22, pady=(22 if idx == 0 else 10, 8))

            icon = ctk.CTkLabel(
                row,
                text=icons[key],
                width=32,
                font=("Microsoft YaHei UI", 18),
                text_color="#334155"
            )
            icon.pack(side="left")

            name = ctk.CTkLabel(
                row,
                text=key,
                width=90,
                anchor="w",
                font=("Microsoft YaHei UI", 14),
                text_color="#475569"
            )
            name.pack(side="left", padx=(8, 0))

            entry = ctk.CTkEntry(
                row,
                textvariable=self.result_vars[key],
                height=34,
                fg_color="#F8FAFC",
                border_color="#E2E8F0",
                corner_radius=6,
                font=("Microsoft YaHei UI", 14),
                placeholder_text="请输入" + key
            )
            entry.pack(side="left", fill="x", expand=True)
            self.result_entries[key] = entry

    def browse_image(self):
        file_path = filedialog.askopenfilename(
            title="选择身份证图片",
            filetypes=[
                ("图片文件", "*.jpg *.jpeg *.png"),
                ("所有文件", "*.*")
            ]
        )

        if not file_path:
            return

        self.selected_image_path.set(file_path)
        self.show_preview_image(file_path)

    def show_preview_image(self, file_path):
        try:
            image = Image.open(file_path)
            image.thumbnail((460, 300))

            ctk_image = ctk.CTkImage(
                light_image=image,
                dark_image=image,
                size=image.size
            )

            self.preview_label.configure(
                image=ctk_image,
                text=""
            )
            self.preview_label.image = ctk_image

        except Exception as e:
            messagebox.showerror("图片预览失败", str(e))

    def on_drop(self, event):
        if self.current_page != "upload":
            return
        
        file_path = event.data
        file_path = file_path.strip('{}')
        
        if file_path and os.path.isfile(file_path):
            ext = os.path.splitext(file_path)[1].lower()
            if ext in ('.jpg', '.jpeg', '.png'):
                self.selected_image_path.set(file_path)
                self.show_preview_image(file_path)
            else:
                messagebox.showwarning("提示", "请拖拽图片文件（支持 JPG / PNG / JPEG 格式）")

    def parse_image(self):
        if not self.selected_image_path.get():
            messagebox.showwarning("提示", "请先选择身份证图片。")
            return

        try:
            img_path = self.selected_image_path.get()
            
            result = engine(img_path)
            info = parse_id_card_info(result.txts)

            self.result_vars["姓名"].set(info['name'] or "")
            self.result_vars["身份证号"].set(info['id_number'] or "")
            self.result_vars["签发机关"].set(info['issue_authority'] or "")
            self.result_vars["有效期限"].set(info['valid_period'] or "")
            self.result_vars["有效期类型"].set(info['valid_type'] or "")

            self.parsed_info = info
            self.parsed_image_path = img_path
            
            self.status_badge.configure(
                text="● 识别完成",
                fg_color="#ECFDF5",
                text_color="#059669"
            )
            messagebox.showinfo("提示", "识别完成！请检查并修改识别结果，然后点击保存按钮保存到数据库。")
            
        except Exception as e:
            messagebox.showerror("识别失败", str(e))

    def save_to_db(self):
        if not self.parsed_image_path:
            messagebox.showwarning("提示", "请先识别身份证图片。")
            return

        if not self.db_ok:
            messagebox.showerror("错误", "数据库连接失败，无法保存记录！")
            return

        try:
            with open(self.parsed_image_path, 'rb') as f:
                image_data = f.read()
            
            image_name = os.path.basename(self.parsed_image_path)
            
            name = self.result_vars["姓名"].get().strip()
            id_number = self.result_vars["身份证号"].get().strip()
            issue_authority = self.result_vars["签发机关"].get().strip()
            valid_period = self.result_vars["有效期限"].get().strip()
            valid_type = self.result_vars["有效期类型"].get().strip()
            
            result = add_id_card(
                image_data, image_name, name, id_number,
                self.parsed_info.get('gender', ''),
                self.parsed_info.get('nationality', ''),
                self.parsed_info.get('address', ''),
                issue_authority, valid_period, valid_type
            )

            if result:
                if result.get('duplicate'):
                    self.status_badge.configure(
                        text="● 重复数据",
                        fg_color="#FEF3C7",
                        text_color="#D97706"
                    )
                    messagebox.showwarning("提示", f"该记录已存在！\n签发机关: {issue_authority}\n有效期限: {valid_period}")
                else:
                    self.status_badge.configure(
                        text="● 已保存",
                        fg_color="#ECFDF5",
                        text_color="#059669"
                    )
                    messagebox.showinfo("成功", f"保存成功！\n序号: {result['id']}\n唯一ID: {result['uid']}")
            else:
                self.status_badge.configure(
                    text="● 识别完成",
                    fg_color="#FEF3C7",
                    text_color="#D97706"
                )
                messagebox.showwarning("提示", "识别完成，但保存到数据库失败。")

        except Exception as e:
            messagebox.showerror("保存失败", str(e))

    def batch_upload(self):
        if not self.db_ok:
            messagebox.showerror("错误", "数据库连接失败！")
            return

        file_paths = filedialog.askopenfilenames(
            title="选择多张身份证图片",
            filetypes=[
                ("图片文件", "*.jpg *.jpeg *.png"),
                ("所有文件", "*.*")
            ]
        )

        if not file_paths:
            return

        total = len(file_paths)
        success_count = 0
        failed_count = 0
        failed_files = []

        progress_dialog = ctk.CTkToplevel(self)
        progress_dialog.title("批量上传进度")
        progress_dialog.geometry("400x180")
        progress_dialog.resizable(False, False)
        progress_dialog.grab_set()

        progress_label = ctk.CTkLabel(
            progress_dialog,
            text=f"正在处理第 0/{total} 张图片...",
            font=("Microsoft YaHei UI", 14)
        )
        progress_label.pack(pady=(20, 10))

        progress_bar = ctk.CTkProgressBar(
            progress_dialog,
            width=320,
            height=20
        )
        progress_bar.pack(pady=(0, 20))
        progress_bar.set(0)

        status_label = ctk.CTkLabel(
            progress_dialog,
            text="",
            font=("Microsoft YaHei UI", 13)
        )
        status_label.pack()

        self.update()

        for idx, img_path in enumerate(file_paths, 1):
            try:
                progress_label.configure(text=f"正在处理第 {idx}/{total} 张图片...")
                status_label.configure(text=f"正在识别: {os.path.basename(img_path)}")
                progress_bar.set(idx / total)
                self.update()

                with open(img_path, 'rb') as f:
                    image_data = f.read()

                image_name = os.path.basename(img_path)

                result = engine(img_path)
                info = parse_id_card_info(result.txts)

                name = info['name'] or ""
                id_number = info['id_number'] or ""
                issue_authority = info['issue_authority'] or ""
                valid_period = info['valid_period'] or ""
                valid_type = info['valid_type'] or "10年"

                db_result = add_id_card(
                    image_data, image_name, name, id_number,
                    info.get('gender', ''),
                    info.get('nationality', ''),
                    info.get('address', ''),
                    issue_authority, valid_period, valid_type
                )

                if db_result:
                    if db_result.get('duplicate'):
                        failed_count += 1
                        failed_files.append(f"{image_name} - 重复数据")
                    else:
                        success_count += 1
                else:
                    failed_count += 1
                    failed_files.append(image_name)

            except Exception as e:
                failed_count += 1
                failed_files.append(f"{os.path.basename(img_path)} - {str(e)}")

            self.update()

        progress_dialog.destroy()

        msg = f"批量上传完成！\n成功: {success_count} 张\n失败: {failed_count} 张"
        if failed_files:
            msg += "\n\n失败的文件:\n" + "\n".join(failed_files)

        messagebox.showinfo("批量上传结果", msg)

    def show_list_page(self):
        self.clear_main_area()
        self.update_nav_state("list")

        card = self.create_main_card()

        header = ctk.CTkFrame(card, fg_color="transparent")
        header.pack(fill="x", padx=34, pady=(30, 20))

        title_box = ctk.CTkFrame(header, fg_color="transparent")
        title_box.pack(side="left")

        title = ctk.CTkLabel(
            title_box,
            text="识别记录列表",
            font=("Microsoft YaHei UI", 24, "bold"),
            text_color=self.text_color
        )
        title.pack(anchor="w")

        subtitle = ctk.CTkLabel(
            title_box,
            text="展示所有身份证识别记录，支持查看详情、下载图片与删除记录。",
            font=("Microsoft YaHei UI", 14),
            text_color=self.sub_text_color
        )
        subtitle.pack(anchor="w", pady=(8, 0))

        btn_box = ctk.CTkFrame(header, fg_color="transparent")
        btn_box.pack(side="right")

        refresh_btn = self.create_outline_button(btn_box, "⟳  刷新列表", self.refresh_records)
        refresh_btn.pack(side="left", padx=(0, 12))

        export_btn = self.create_outline_button(btn_box, "↓  导出记录", self.export_records)
        export_btn.pack(side="left")

        self.build_record_table(card, self.get_records_from_db())
        self.build_pagination(card)

        pass

    def get_records_from_db(self):
        if not self.db_ok:
            return []
        
        self.total_count = get_total_count()
        self.total_pages = (self.total_count + self.page_size - 1) // self.page_size
        
        cards = get_all_id_cards(page=self.current_page_num, page_size=self.page_size)
        records = []
        for card in cards:
            records.append({
                "id": str(card[0]),
                "uid": card[1] or "",
                "name": card[3] or "",
                "id_number": card[4] or "",
                "authority": card[8] or "",
                "valid_period": card[9] or "",
                "valid_type": card[10] or "",
                "gender": card[5] or "",
                "nation": card[6] or "",
                "birthday": "",
                "address": card[7] or "",
                "image_path": ""
            })
        return records

    def build_record_table(self, parent, records):
        scrollable_frame = ctk.CTkScrollableFrame(
            parent,
            fg_color="#FFFFFF",
            corner_radius=12,
            border_width=1,
            border_color=self.border_color,
            height=400
        )
        scrollable_frame.pack(fill="both", expand=True, padx=34, pady=(0, 0))

        table = ctk.CTkFrame(scrollable_frame, fg_color="transparent")
        table.pack(fill="both", expand=True)
        
        table.grid_columnconfigure(0, weight=0, minsize=60)
        table.grid_columnconfigure(1, weight=0, minsize=80)
        table.grid_columnconfigure(2, weight=1, minsize=150)
        table.grid_columnconfigure(3, weight=2, minsize=200)
        table.grid_columnconfigure(4, weight=1, minsize=150)
        table.grid_columnconfigure(5, weight=0, minsize=80)
        table.grid_columnconfigure(6, weight=0, minsize=80)

        columns = ["ID", "姓名", "身份证号", "签发机关", "有效期限", "有效期类型", "操作"]

        header_frame = ctk.CTkFrame(table, fg_color="#F8FAFC")
        header_frame.grid(row=0, column=0, columnspan=7, sticky="nsew")
        
        for i, col in enumerate(columns):
            label = ctk.CTkLabel(
                header_frame,
                text=col,
                anchor="center",
                font=("Microsoft YaHei UI", 14, "bold"),
                text_color=self.text_color,
                padx=8
            )
            label.grid(row=0, column=i, sticky="nsew")

        if not records:
            empty = ctk.CTkLabel(
                table,
                text="暂无识别记录",
                font=("Microsoft YaHei UI", 15),
                text_color=self.sub_text_color
            )
            empty.grid(row=1, column=0, columnspan=7, pady=80)
            return

        for row_idx, record in enumerate(records, start=1):
            values = [
                str(record["id"]),
                record["name"],
                record["id_number"],
                record["authority"],
                record["valid_period"],
                record["valid_type"]
            ]

            for col_idx, value in enumerate(values):
                label = ctk.CTkLabel(
                    table,
                    text=value if value else "-",
                    anchor="center",
                    font=("Microsoft YaHei UI", 13),
                    text_color="#334155",
                    padx=4,
                    pady=10
                )
                label.grid(row=row_idx, column=col_idx, sticky="nsew")

            view_btn = ctk.CTkButton(
                table,
                text="👁 查看",
                width=70,
                height=30,
                fg_color="transparent",
                hover_color="#EFF6FF",
                text_color=self.primary_color,
                font=("Microsoft YaHei UI", 12),
                command=lambda r=record: self.open_detail_window(r)
            )
            view_btn.grid(row=row_idx, column=6, padx=(0, 8), pady=5)

        return scrollable_frame

    def build_pagination(self, parent):
        if self.total_count <= self.page_size:
            return

        pagination = ctk.CTkFrame(parent, fg_color="#FFFFFF", border_width=1, border_color=self.border_color, corner_radius=12)
        pagination.pack(fill="x", padx=34, pady=(0, 16))

        inner = ctk.CTkFrame(pagination, fg_color="transparent")
        inner.pack(fill="x", padx=16, pady=12)

        prev_btn = ctk.CTkButton(
            inner,
            text="上一页",
            width=80,
            height=34,
            fg_color="transparent",
            hover_color="#EFF6FF",
            text_color=self.primary_color,
            font=("Microsoft YaHei UI", 13),
            state="disabled" if self.current_page_num <= 1 else "normal",
            command=self.prev_page
        )
        prev_btn.pack(side="left", padx=(0, 8))

        page_info = ctk.CTkLabel(
            inner,
            text=f"第 {self.current_page_num} / {self.total_pages} 页，共 {self.total_count} 条",
            font=("Microsoft YaHei UI", 13),
            text_color=self.sub_text_color
        )
        page_info.pack(side="left", padx=16)

        next_btn = ctk.CTkButton(
            inner,
            text="下一页",
            width=80,
            height=34,
            fg_color="transparent",
            hover_color="#EFF6FF",
            text_color=self.primary_color,
            font=("Microsoft YaHei UI", 13),
            state="disabled" if self.current_page_num >= self.total_pages else "normal",
            command=self.next_page
        )
        next_btn.pack(side="right", padx=(8, 0))

    def prev_page(self):
        if self.current_page_num > 1:
            self.current_page_num -= 1
            self.show_list_page()

    def next_page(self):
        if self.current_page_num < self.total_pages:
            self.current_page_num += 1
            self.show_list_page()

    def build_detail_panel(self, parent):
        title = ctk.CTkLabel(
            parent,
            text="记录详情（当前选中，可编辑）",
            font=("Microsoft YaHei UI", 16, "bold"),
            text_color=self.text_color
        )
        title.pack(anchor="w", padx=24, pady=(18, 8))

        body = ctk.CTkFrame(parent, fg_color="transparent")
        body.pack(fill="x", padx=24, pady=(0, 18))

        img_box = ctk.CTkFrame(
            body,
            width=260,
            height=145,
            fg_color="#F8FAFC",
            corner_radius=10,
            border_width=1,
            border_color="#CBD5E1"
        )
        img_box.pack(side="left", padx=(0, 28))
        img_box.pack_propagate(False)

        img_label = ctk.CTkLabel(
            img_box,
            text="身份证图片预览",
            font=("Microsoft YaHei UI", 14),
            text_color=self.sub_text_color
        )
        img_label.pack(expand=True)

        info = ctk.CTkFrame(body, fg_color="transparent")
        info.pack(side="left", fill="both", expand=True)

        if self.selected_record:
            record = self.selected_record
        else:
            records = self.get_records_from_db()
            record = records[0] if records else {}

        if not hasattr(self, 'edit_vars'):
            self.edit_vars = {}

        fields = [
            ("姓名", "name"),
            ("性别", "gender"),
            ("民族", "nation"),
            ("身份证号", "id_number"),
            ("住址", "address"),
            ("签发机关", "authority"),
            ("有效期限", "valid_period"),
            ("有效期类型", "valid_type")
        ]

        for i, (label_text, key) in enumerate(fields):
            row = ctk.CTkFrame(info, fg_color="transparent")
            row.pack(fill="x", pady=8)

            label = ctk.CTkLabel(
                row,
                text=f"{label_text}：",
                width=70,
                font=("Microsoft YaHei UI", 14),
                text_color="#64748B"
            )
            label.pack(side="left")

            if key in self.edit_vars:
                self.edit_vars[key].set(record.get(key, ""))
            else:
                var = tk.StringVar(value=record.get(key, ""))
                self.edit_vars[key] = var

            entry = ctk.CTkEntry(
                row,
                textvariable=self.edit_vars[key],
                height=32,
                fg_color="#F8FAFC",
                border_color="#E2E8F0",
                corner_radius=6,
                font=("Microsoft YaHei UI", 14)
            )
            entry.pack(side="left", fill="x", expand=True)

            if key == "valid_type":
                entry.configure(width=80)

    def show_search_page(self):
        self.clear_main_area()
        self.update_nav_state("search")

        card = self.create_main_card()

        header = ctk.CTkFrame(card, fg_color="transparent")
        header.pack(fill="x", padx=34, pady=(30, 20))

        title = ctk.CTkLabel(
            header,
            text="搜索识别记录",
            font=("Microsoft YaHei UI", 24, "bold"),
            text_color=self.text_color
        )
        title.pack(anchor="w")

        subtitle = ctk.CTkLabel(
            header,
            text="根据签发机关和有效期类型筛选历史识别记录，支持下载身份证原图。",
            font=("Microsoft YaHei UI", 14),
            text_color=self.sub_text_color
        )
        subtitle.pack(anchor="w", pady=(8, 0))

        filter_card = ctk.CTkFrame(
            card,
            fg_color="#FFFFFF",
            corner_radius=12,
            border_width=1,
            border_color=self.border_color
        )
        filter_card.pack(fill="x", padx=34, pady=(0, 22))

        filter_inner = ctk.CTkFrame(filter_card, fg_color="transparent")
        filter_inner.pack(fill="x", padx=24, pady=22)

        authority_box = ctk.CTkFrame(filter_inner, fg_color="transparent")
        authority_box.pack(side="left", fill="x", expand=True, padx=(0, 16))

        ctk.CTkLabel(
            authority_box,
            text="签发机关",
            font=("Microsoft YaHei UI", 14, "bold"),
            text_color=self.text_color
        ).pack(anchor="w", pady=(0, 8))

        self.search_authority = ctk.CTkEntry(
            authority_box,
            height=44,
            corner_radius=8,
            border_color="#CBD5E1",
            placeholder_text="请输入签发机关",
            font=("Microsoft YaHei UI", 14)
        )
        self.search_authority.pack(fill="x")

        type_box = ctk.CTkFrame(filter_inner, fg_color="transparent")
        type_box.pack(side="left", fill="x", expand=True, padx=(0, 16))

        ctk.CTkLabel(
            type_box,
            text="有效期类型",
            font=("Microsoft YaHei UI", 14, "bold"),
            text_color=self.text_color
        ).pack(anchor="w", pady=(0, 8))

        self.search_type = ctk.CTkOptionMenu(
            type_box,
            height=44,
            values=["全部", "5年", "10年", "20年", "长期"],
            fg_color="#FFFFFF",
            button_color="#FFFFFF",
            button_hover_color="#F1F5F9",
            dropdown_fg_color="#FFFFFF",
            text_color=self.text_color,
            corner_radius=8,
            font=("Microsoft YaHei UI", 14)
        )
        self.search_type.set("全部")
        self.search_type.pack(fill="x")

        search_btn = ctk.CTkButton(
            filter_inner,
            text="🔍  搜索",
            width=150,
            height=44,
            fg_color=self.primary_color,
            hover_color=self.primary_hover,
            corner_radius=8,
            font=("Microsoft YaHei UI", 14, "bold"),
            command=self.search_records
        )
        search_btn.pack(side="left", pady=(27, 0), padx=(0, 12))

        reset_btn = self.create_outline_button(filter_inner, "⟳  重置", self.reset_search)
        reset_btn.pack(side="left", pady=(27, 0))

        self.search_result_frame = ctk.CTkFrame(card, fg_color="transparent")
        self.search_result_frame.pack(fill="both", expand=True)

        self.search_pagination_frame = ctk.CTkFrame(card, fg_color="transparent")
        self.search_pagination_frame.pack(fill="x", padx=34, pady=(0, 16))

        self.perform_search()

        bottom = ctk.CTkFrame(card, fg_color="transparent")
        bottom.pack(fill="x", padx=34, pady=(0, 24))

        download_btn = ctk.CTkButton(
            bottom,
            text="↓  下载图片",
            width=220,
            height=42,
            fg_color="#FFFFFF",
            hover_color="#EFF6FF",
            text_color=self.primary_color,
            border_width=1,
            border_color="#93C5FD",
            corner_radius=8,
            font=("Microsoft YaHei UI", 14),
            command=self.download_image
        )
        download_btn.pack()

    def create_outline_button(self, parent, text, command):
        return ctk.CTkButton(
            parent,
            text=text,
            width=130,
            height=42,
            fg_color="#FFFFFF",
            hover_color="#F1F5F9",
            text_color=self.text_color,
            border_width=1,
            border_color="#CBD5E1",
            corner_radius=8,
            font=("Microsoft YaHei UI", 14),
            command=command
        )

    def refresh_records(self):
        self.show_list_page()
        messagebox.showinfo("提示", "记录列表已刷新。")

    def export_records(self):
        messagebox.showinfo("提示", "导出功能后续可接入 Excel / CSV。")

    def select_record(self, record):
        DetailWindow(self, record)
    
    def open_detail_window(self, record):
        DetailWindow(self, record)

    def delete_record(self):
        if not self.selected_record:
            messagebox.showwarning("提示", "请先选择一条记录。")
            return

        if messagebox.askyesno("确认删除", f"确定要删除 {self.selected_record['name']} 的记录吗？"):
            if delete_id_card(int(self.selected_record['id'])):
                messagebox.showinfo("成功", "删除成功！")
                self.selected_record = None
                self.show_list_page()
            else:
                messagebox.showerror("错误", "删除失败！")

    def update_record(self):
        if not self.selected_record:
            messagebox.showwarning("提示", "请先选择一条记录。")
            return

        if not hasattr(self, 'edit_vars') or not self.edit_vars:
            messagebox.showwarning("提示", "请先选择一条记录查看详情。")
            return

        name = self.edit_vars["name"].get().strip()
        gender = self.edit_vars["gender"].get().strip()
        nation = self.edit_vars["nation"].get().strip()
        id_number = self.edit_vars["id_number"].get().strip()
        address = self.edit_vars["address"].get().strip()
        authority = self.edit_vars["authority"].get().strip()
        valid_period = self.edit_vars["valid_period"].get().strip()
        valid_type = self.edit_vars["valid_type"].get().strip()

        if not authority:
            messagebox.showwarning("提示", "签发机关不能为空！")
            return

        if not valid_period:
            messagebox.showwarning("提示", "有效期限不能为空！")
            return

        if messagebox.askyesno("确认修改", "确定要修改这条记录吗？"):
            if update_id_card(
                int(self.selected_record['id']),
                name, id_number, gender, nation, address,
                authority, valid_period, valid_type
            ):
                messagebox.showinfo("成功", "修改成功！")
                self.show_list_page()
            else:
                messagebox.showerror("错误", "修改失败！")

    def download_image(self):
        if not self.selected_record:
            messagebox.showwarning("提示", "请先选择一条记录。")
            return

        save_path = filedialog.asksaveasfilename(
            defaultextension=".jpg",
            initialfile=f"身份证_{self.selected_record['name']}.jpg",
            filetypes=[("JPEG图片", "*.jpg"), ("PNG图片", "*.png"), ("所有文件", "*.*")]
        )

        if save_path:
            if download_image(int(self.selected_record['id']), save_path):
                messagebox.showinfo("成功", f"图片已保存到：\n{save_path}")
            else:
                messagebox.showerror("错误", "下载失败！")

    def search_records(self):
        self.search_current_page = 1
        self.perform_search()

    def perform_search(self):
        authority = self.search_authority.get().strip()
        valid_type = self.search_type.get()

        if valid_type == "全部":
            valid_type = None

        self.search_total_count = search_cards_count(authority, valid_type)
        self.search_total_pages = (self.search_total_count + self.page_size - 1) // self.page_size

        cards = search_cards(authority, valid_type, page=self.search_current_page, page_size=self.page_size)
        records = []
        for card in cards:
            records.append({
                "id": str(card[0]),
                "uid": card[1] or "",
                "name": card[3] or "",
                "id_number": card[4] or "",
                "authority": card[8] or "",
                "valid_period": card[9] or "",
                "valid_type": card[10] or "",
                "gender": card[5] or "",
                "nation": card[6] or "",
                "birthday": "",
                "address": card[7] or "",
                "image_path": ""
            })

        for widget in self.search_result_frame.winfo_children():
            widget.destroy()

        self.build_record_table(self.search_result_frame, records)
        self.build_search_pagination()

    def build_search_pagination(self):
        for widget in self.search_pagination_frame.winfo_children():
            widget.destroy()

        if self.search_total_count <= self.page_size:
            return

        inner = ctk.CTkFrame(self.search_pagination_frame, fg_color="#FFFFFF", border_width=1, border_color=self.border_color, corner_radius=12)
        inner.pack(fill="x")

        prev_btn = ctk.CTkButton(
            inner,
            text="上一页",
            width=80,
            height=34,
            fg_color="transparent",
            hover_color="#EFF6FF",
            text_color=self.primary_color,
            font=("Microsoft YaHei UI", 13),
            state="disabled" if self.search_current_page <= 1 else "normal",
            command=self.search_prev_page
        )
        prev_btn.pack(side="left", padx=(16, 8))

        page_info = ctk.CTkLabel(
            inner,
            text=f"第 {self.search_current_page} / {self.search_total_pages} 页，共 {self.search_total_count} 条",
            font=("Microsoft YaHei UI", 13),
            text_color=self.text_color
        )
        page_info.pack(side="left", padx=12)

        next_btn = ctk.CTkButton(
            inner,
            text="下一页",
            width=80,
            height=34,
            fg_color="transparent",
            hover_color="#EFF6FF",
            text_color=self.primary_color,
            font=("Microsoft YaHei UI", 13),
            state="disabled" if self.search_current_page >= self.search_total_pages else "normal",
            command=self.search_next_page
        )
        next_btn.pack(side="right", padx=(8, 16))

    def search_prev_page(self):
        if self.search_current_page > 1:
            self.search_current_page -= 1
            self.perform_search()

    def search_next_page(self):
        if self.search_current_page < self.search_total_pages:
            self.search_current_page += 1
            self.perform_search()

    def reset_search(self):
        self.search_authority.delete(0, "end")
        self.search_type.set("全部")

        for widget in self.search_result_frame.winfo_children():
            widget.destroy()

        self.build_record_table(self.search_result_frame, self.get_records_from_db())


class DetailWindow(ctk.CTkToplevel):
    def __init__(self, parent, record):
        super().__init__(parent)
        self.parent = parent
        self.record = record
        self.original_values = {k: v for k, v in record.items()}
        self.has_changes = False
        
        self.title(f"记录详情 - ID: {record['id']}")
        self.geometry("850x700")
        self.resizable(True, True)
        
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)
        
        self.build_ui()
        
        self.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        self.transient(parent)
        self.grab_set()
    
    def build_ui(self):
        main_frame = ctk.CTkFrame(self, fg_color="#FFFFFF", corner_radius=12, border_width=1, border_color="#E2E8F0")
        main_frame.pack(fill="both", expand=True, padx=20, pady=20)
        main_frame.grid_columnconfigure(0, weight=1)
        
        title = ctk.CTkLabel(
            main_frame,
            text="身份证信息详情",
            font=("Microsoft YaHei UI", 18, "bold"),
            text_color="#1E293B"
        )
        title.pack(anchor="w", padx=24, pady=(20, 8))
        
        content_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        content_frame.pack(fill="both", expand=True, padx=24, pady=12)
        content_frame.grid_columnconfigure(0, weight=0)
        content_frame.grid_columnconfigure(1, weight=1)
        content_frame.grid_rowconfigure(0, weight=1)
        
        image_frame = ctk.CTkFrame(
            content_frame,
            fg_color="#F8FAFC",
            corner_radius=10,
            border_width=1,
            border_color="#E2E8F0",
            width=260,
            height=160
        )
        image_frame.grid(row=0, column=0, padx=(0, 24), sticky="n")
        image_frame.pack_propagate(False)
        
        image_data = get_image_data(int(self.record['id']))
        if image_data:
            try:
                from io import BytesIO
                img = Image.open(BytesIO(image_data))
                img = img.resize((240, 140), Image.Resampling.LANCZOS)
                self.photo = ctk.CTkImage(light_image=img, size=(240, 140))
                image_label = ctk.CTkLabel(image_frame, image=self.photo, text="")
                image_label.pack(expand=True)
            except Exception as e:
                print(f"图片加载失败: {str(e)}")
                image_label = ctk.CTkLabel(
                    image_frame,
                    text="图片加载失败",
                    font=("Microsoft YaHei UI", 14),
                    text_color="#94A3B8"
                )
                image_label.pack(expand=True)
        else:
            image_label = ctk.CTkLabel(
                image_frame,
                text="暂无图片",
                font=("Microsoft YaHei UI", 14),
                text_color="#94A3B8"
            )
            image_label.pack(expand=True)
        
        info_frame = ctk.CTkFrame(content_frame, fg_color="transparent")
        info_frame.grid(row=0, column=1, sticky="nsew")
        
        fields = [
            ("序号", "id"),
            ("姓名", "name"),
            ("性别", "gender"),
            ("民族", "nation"),
            ("身份证号", "id_number"),
            ("住址", "address"),
            ("签发机关", "authority"),
            ("有效期限", "valid_period"),
            ("有效期类型", "valid_type")
        ]
        
        self.edit_vars = {}
        
        for label_text, key in fields:
            row = ctk.CTkFrame(info_frame, fg_color="transparent")
            row.pack(fill="x", pady=8)
            
            label = ctk.CTkLabel(
                row,
                text=f"{label_text}：",
                width=80,
                font=("Microsoft YaHei UI", 14),
                text_color="#64748B"
            )
            label.pack(side="left")
            
            var = tk.StringVar(value=self.record.get(key, ""))
            self.edit_vars[key] = var
            
            if key == "id":
                entry = ctk.CTkLabel(
                    row,
                    textvariable=var,
                    font=("Microsoft YaHei UI", 14),
                    text_color="#1E293B"
                )
            else:
                entry = ctk.CTkEntry(
                    row,
                    textvariable=var,
                    height=36,
                    fg_color="#F8FAFC",
                    border_color="#E2E8F0",
                    corner_radius=6,
                    font=("Microsoft YaHei UI", 14),
                    width=400
                )
                var.trace_add("write", lambda *args, k=key: self.on_value_change(k))
            entry.pack(side="left", fill="x", expand=True)
        
        button_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        button_frame.pack(fill="x", padx=24, pady=(20, 20))
        
        download_btn = ctk.CTkButton(
            button_frame,
            text="↓ 下载图片",
            width=120,
            height=36,
            fg_color="#FFFFFF",
            hover_color="#EFF6FF",
            text_color="#3B82F6",
            border_width=1,
            border_color="#93C5FD",
            corner_radius=8,
            font=("Microsoft YaHei UI", 12),
            command=self.download_image
        )
        download_btn.pack(side="left", padx=(0, 12))
        
        delete_btn = ctk.CTkButton(
            button_frame,
            text="🗑 删除记录",
            width=120,
            height=36,
            fg_color="#FFFFFF",
            hover_color="#FEF2F2",
            text_color="#EF4444",
            border_width=1,
            border_color="#FCA5A5",
            corner_radius=8,
            font=("Microsoft YaHei UI", 12),
            command=self.delete_record
        )
        delete_btn.pack(side="left", padx=(0, 12))
        
        cancel_btn = ctk.CTkButton(
            button_frame,
            text="✖ 取消",
            width=100,
            height=36,
            fg_color="#FFFFFF",
            hover_color="#F1F5F9",
            text_color="#64748B",
            border_width=1,
            border_color="#E2E8F0",
            corner_radius=8,
            font=("Microsoft YaHei UI", 12),
            command=self.cancel_changes
        )
        cancel_btn.pack(side="right", padx=(0, 12))
        
        save_btn = ctk.CTkButton(
            button_frame,
            text="💾 保存修改",
            width=140,
            height=36,
            fg_color="#3B82F6",
            hover_color="#2563EB",
            corner_radius=8,
            font=("Microsoft YaHei UI", 12, "bold"),
            command=self.save_changes
        )
        save_btn.pack(side="right")
    
    def on_value_change(self, key):
        self.has_changes = True
    
    def cancel_changes(self):
        if self.has_changes:
            if messagebox.askyesno("提示", "您有未保存的修改，确定要取消吗？"):
                self.destroy()
        else:
            self.destroy()
    
    def on_closing(self):
        self.cancel_changes()
    
    def save_changes(self):
        name = self.edit_vars["name"].get().strip()
        gender = self.edit_vars["gender"].get().strip()
        nation = self.edit_vars["nation"].get().strip()
        id_number = self.edit_vars["id_number"].get().strip()
        address = self.edit_vars["address"].get().strip()
        authority = self.edit_vars["authority"].get().strip()
        valid_period = self.edit_vars["valid_period"].get().strip()
        valid_type = self.edit_vars["valid_type"].get().strip()
        
        if not authority:
            messagebox.showwarning("提示", "签发机关不能为空！")
            return
        
        if not valid_period:
            messagebox.showwarning("提示", "有效期限不能为空！")
            return
        
        if messagebox.askyesno("确认修改", "确定要修改这条记录吗？"):
            if update_id_card(
                int(self.record['id']),
                name, id_number, gender, nation, address,
                authority, valid_period, valid_type
            ):
                messagebox.showinfo("成功", "修改成功！")
                self.parent.show_list_page()
                self.destroy()
            else:
                messagebox.showerror("错误", "修改失败！")
    
    def delete_record(self):
        if messagebox.askyesno("确认删除", f"确定要删除这条记录吗？"):
            if delete_id_card(int(self.record['id'])):
                messagebox.showinfo("成功", "删除成功！")
                self.parent.show_list_page()
                self.destroy()
            else:
                messagebox.showerror("错误", "删除失败！")
    
    def download_image(self):
        save_path = filedialog.asksaveasfilename(
            defaultextension=".jpg",
            filetypes=[("JPEG图片", "*.jpg"), ("PNG图片", "*.png")],
            initialfile=f"id_card_{self.record['id']}.jpg"
        )
        
        if save_path:
            if download_image(int(self.record['id']), save_path):
                messagebox.showinfo("成功", f"图片已保存到：\n{save_path}")
            else:
                messagebox.showerror("错误", "下载失败！")

if __name__ == "__main__":
    app = IDCardOCRApp()
    app.mainloop()
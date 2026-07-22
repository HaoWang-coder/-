from __future__ import annotations

import contextlib
import importlib.util
import io
import math
import os
import queue
import socket
import subprocess
import sys
import threading
import traceback
import zipfile
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk


APP_ROOT = Path(__file__).resolve().parent
OCR_DIR = APP_ROOT / "OCR_IDCard"
DISCOUNT_DIR = APP_ROOT / "优惠计算"
DAILY_DIR = APP_ROOT / "日常总结"
WEEKLY_DIR = APP_ROOT / "周末总结"
FEE_DIR = APP_ROOT / "月初手续费结算"
HISTORY_DIR = APP_ROOT / "历史数据"

COLORS = {
    "nav": "#111111",
    "nav_hover": "#242424",
    "nav_active": "#FFFFFF",
    "bg": "#F5F5F7",
    "card": "#FFFFFF",
    "text": "#1D1D1F",
    "muted": "#86868B",
    "border": "#D2D2D7",
    "field": "#F5F5F7",
    "primary": "#1D1D1F",
    "success": "#248A3D",
    "warning": "#B25000",
    "accent": "#2563EB",
    "accent_soft": "#EFF6FF",
}


@dataclass(frozen=True)
class AppConfig:
    root: Path = APP_ROOT
    db_host: str = os.getenv("DWCX_DB_HOST", "localhost")
    db_port: int = int(os.getenv("DWCX_DB_PORT", "3306"))
    db_user: str = os.getenv("DWCX_DB_USER", "root")
    db_password: str = os.getenv("DWCX_DB_PASSWORD", "123456")
    db_name: str = os.getenv("DWCX_DB_NAME", "id_card")


CONFIG = AppConfig()


class BackendService:
    """集中管理模块加载、数据库访问和子进程，避免页面各自重复实现。"""

    def __init__(self, config: AppConfig):
        self.config = config
        self._modules: dict[str, object] = {}
        self._processes: dict[str, subprocess.Popen] = {}

    def module(self, key: str, path: Path):
        if key not in self._modules:
            self._modules[key] = load_module(path, f"dwcx_{key}")
        return self._modules[key]

    def run_command(self, command: list[str], cwd: Path) -> str:
        result = subprocess.run(command, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace")
        output = result.stdout + ("\n" + result.stderr if result.stderr else "")
        if result.returncode:
            raise RuntimeError(output.strip() or f"进程返回 {result.returncode}")
        return output

    def launch_once(self, key: str, command: list[str], cwd: Path) -> tuple[subprocess.Popen, bool]:
        running = self._processes.get(key)
        if running and running.poll() is None:
            return running, False
        process = subprocess.Popen(command, cwd=cwd)
        self._processes[key] = process
        return process, True

    def database_count(self) -> int:
        import pymysql

        conn = pymysql.connect(
            host=self.config.db_host,
            port=self.config.db_port,
            user=self.config.db_user,
            password=self.config.db_password,
            database=self.config.db_name,
            connect_timeout=5,
        )
        try:
            with conn.cursor() as cursor:
                cursor.execute("SELECT COUNT(*) FROM id_cards")
                return int(cursor.fetchone()[0])
        finally:
            conn.close()

    def validate_layout(self) -> list[str]:
        required = [APP_ROOT / "data_analysis.py", OCR_DIR / "app_gui.py", DISCOUNT_DIR / "car_insurance_discount_calculator.py", DAILY_DIR / "process_excel.py", WEEKLY_DIR / "weekend_summary.py", FEE_DIR / "generate_fee_settlement_1.py"]
        return [str(path) for path in required if not path.is_file()]


def open_path(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True) if path.suffix == "" else None
    if os.name == "nt":
        os.startfile(str(path))  # type: ignore[attr-defined]
    else:
        subprocess.Popen(["xdg-open", str(path)])


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载模块：{path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(name, None)
        raise
    return module


class LoadingOverlay(tk.Frame):
    """覆盖内容区的统一加载层，集中展示长任务的运行状态。"""

    def __init__(self, parent):
        super().__init__(parent, bg=COLORS["bg"])
        card = tk.Frame(self, bg="#FFFFFF", highlightbackground="#DCE3EC", highlightthickness=1)
        card.place(relx=0.5, rely=0.46, anchor="center", width=300, height=150)
        self.spinner = tk.Canvas(card, width=48, height=48, bg="#FFFFFF", highlightthickness=0)
        self.spinner.pack(pady=(22, 6))
        self.message = tk.Label(card, text="正在处理，请稍候…", bg="#FFFFFF", fg="#334155", font=("Microsoft YaHei UI", 10, "bold"))
        self.message.pack()
        self.hint = tk.Label(card, text="请勿关闭程序", bg="#FFFFFF", fg="#94A3B8", font=("Microsoft YaHei UI", 8))
        self.hint.pack(pady=(4, 0))
        self._running = False
        self._phase = 0
        self._animation_id = None

    def show(self, message="正在处理，请稍候…", hint="请勿关闭程序"):
        self.message.configure(text=message)
        self.hint.configure(text=hint)
        self.place(relx=0, rely=0, relwidth=1, relheight=1)
        self.tkraise()
        self._running = True
        self._draw_spinner()

    def hide(self):
        self._running = False
        if self._animation_id is not None:
            self.after_cancel(self._animation_id)
            self._animation_id = None
        self.place_forget()

    def _draw_spinner(self):
        if not self._running:
            return
        self.spinner.delete("all")
        center = 24
        for index in range(10):
            angle = math.radians((index * 36 + self._phase) % 360)
            x = center + math.cos(angle) * 15
            y = center + math.sin(angle) * 15
            distance = (index - self._phase // 36) % 10
            color = COLORS["accent"] if distance < 3 else "#BFDBFE" if distance < 6 else "#E2E8F0"
            radius = 3 if distance < 3 else 2.5
            self.spinner.create_oval(x - radius, y - radius, x + radius, y + radius, fill=color, outline="")
        self._phase = (self._phase + 36) % 360
        self._animation_id = self.after(75, self._draw_spinner)


class AsyncPage(ttk.Frame):
    def __init__(self, parent, app: "DWCXApp"):
        super().__init__(parent, style="Page.TFrame")
        self.app = app
        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self.running = False

    def run_task(self, task, on_success=None, loading_text="正在处理，请稍候…") -> None:
        if self.running:
            messagebox.showinfo("任务正在运行", "请等待当前任务完成。")
            return
        self.running = True
        self.app.show_loading(loading_text)
        self.app.set_status("任务运行中…", COLORS["warning"])

        def worker():
            try:
                self.events.put(("success", task()))
            except Exception:
                self.events.put(("error", traceback.format_exc()))

        threading.Thread(target=worker, daemon=True).start()

        def poll():
            try:
                kind, payload = self.events.get_nowait()
            except queue.Empty:
                self.after(120, poll)
                return
            self.running = False
            self.app.hide_loading()
            if kind == "error":
                self.app.set_status("任务失败", "#DC2626")
                self.write_log(str(payload))
                on_failure = getattr(self, "on_task_failure", None)
                if callable(on_failure):
                    on_failure()
                messagebox.showerror("运行失败", str(payload).splitlines()[-1])
            else:
                self.app.set_status("任务完成", COLORS["success"])
                if on_success:
                    on_success(payload)

        self.after(120, poll)

    def write_log(self, text: str) -> None:
        widget = getattr(self, "log", None)
        if widget:
            widget.configure(state="normal")
            widget.insert("end", text.rstrip() + "\n")
            widget.see("end")
            widget.configure(state="disabled")


class HomePage(ttk.Frame):
    def __init__(self, parent, app: "DWCXApp"):
        super().__init__(parent, style="Page.TFrame")
        self.app = app
        self.canvas = tk.Canvas(self, bg=COLORS["bg"], highlightthickness=0, bd=0)
        scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)

        self.body = ttk.Frame(self.canvas, style="Page.TFrame")
        self.body_window = self.canvas.create_window((0, 0), window=self.body, anchor="nw")
        self.body.bind("<Configure>", self._update_scroll_region)
        self.canvas.bind("<Configure>", self._resize_content)

        title(self.body, "工作台", "统一管理报价、日报、结算、OCR 与历史资料")
        self.cards = ttk.Frame(self.body, style="Page.TFrame")
        self.cards.pack(fill="x", padx=28, pady=6)
        items = [
            ("数据分析", "上传报价/保单表生成多维分析报告", "analysis"),
            ("身份证 OCR", "识别身份证并保存到本地数据库", "ocr"),
            ("优惠计算", "按车型、用途和 OC 分数计算优惠", "discount"),
            ("日常总结", "生成在线文档并匹配报价记录", "daily"),
            ("周末总结", "汇总询单、生效保单并生成周报", "weekly"),
            ("手续费结算", "选择手续费数据与模板生成结算单", "fee"),
            ("历史数据", "查看历史数据压缩档案", "history"),
        ]
        self.card_widgets = []
        self.description_labels = []
        for index, (name, desc, key) in enumerate(items):
            card = tk.Frame(self.cards, bg=COLORS["card"], highlightbackground=COLORS["border"], highlightthickness=1)
            card.columnconfigure(0, weight=1)
            card.rowconfigure(2, weight=1)
            tk.Label(card, text=f"{index + 1:02d}", bg=COLORS["card"], fg=COLORS["muted"], font=("Segoe UI", 9, "bold")).grid(row=0, column=0, sticky="w", padx=20, pady=(18, 4))
            tk.Label(card, text=name, bg=COLORS["card"], fg=COLORS["text"], font=("Microsoft YaHei UI", 15, "bold")).grid(row=1, column=0, sticky="w", padx=20, pady=(0, 5))
            description = tk.Label(card, text=desc, bg=COLORS["card"], fg=COLORS["muted"], font=("Microsoft YaHei UI", 10), justify="left", anchor="nw")
            description.grid(row=2, column=0, sticky="nsew", padx=20)
            ttk.Button(card, text="打开  →", style="Link.TButton", command=lambda k=key: app.show_page(k)).grid(row=3, column=0, sticky="e", padx=14, pady=14)
            self.card_widgets.append(card)
            self.description_labels.append(description)

        status_card = ttk.LabelFrame(self.body, text="环境状态", padding=16, style="Card.TLabelframe")
        status_card.pack(fill="x", padx=36, pady=12)
        self.db_status = ttk.Label(status_card, text="正在检查数据库…")
        self.db_status.pack(side="left")
        ttk.Button(status_card, text="重新检查", command=lambda: self.check_database(show_loading=True)).pack(side="right")
        self._column_count = 0
        self._reflow_cards(1)
        self._bind_mousewheel(self)
        self.check_database()

    def _update_scroll_region(self, _event=None):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _resize_content(self, event):
        self.canvas.itemconfigure(self.body_window, width=event.width)
        columns = 1 if event.width < 620 else 2 if event.width < 1020 else 3
        self._reflow_cards(columns, event.width)

    def _reflow_cards(self, columns: int, available_width: int | None = None):
        if columns != self._column_count:
            for card in self.card_widgets:
                card.grid_forget()
            for column in range(3):
                self.cards.columnconfigure(column, weight=1 if column < columns else 0, uniform="home_cards" if column < columns else "")
            for index, card in enumerate(self.card_widgets):
                card.grid(row=index // columns, column=index % columns, sticky="nsew", padx=8, pady=8)
            self._column_count = columns

        width = available_width or self.canvas.winfo_width()
        wrap_length = max(160, int((width - 56) / columns) - 58)
        for label in self.description_labels:
            label.configure(wraplength=wrap_length)
        self.after_idle(self._update_scroll_region)

    def _bind_mousewheel(self, widget):
        widget.bind("<MouseWheel>", self._on_mousewheel, add="+")
        widget.bind("<Button-4>", self._on_mousewheel, add="+")
        widget.bind("<Button-5>", self._on_mousewheel, add="+")
        for child in widget.winfo_children():
            self._bind_mousewheel(child)

    def _on_mousewheel(self, event):
        if getattr(event, "num", None) == 4:
            steps = -1
        elif getattr(event, "num", None) == 5:
            steps = 1
        elif event.delta:
            steps = -int(event.delta / 120)
            if steps == 0:
                steps = -1 if event.delta > 0 else 1
        else:
            return
        self.canvas.yview_scroll(steps, "units")
        return "break"

    def check_database(self, show_loading=False):
        if show_loading:
            self.app.show_loading("正在检查数据库连接…")
            self.after(80, lambda: self._check_database(hide_loading=True))
            return
        self._check_database()

    def _check_database(self, hide_loading=False):
        try:
            with socket.create_connection((CONFIG.db_host, CONFIG.db_port), timeout=1.5):
                self.db_status.configure(text="● MariaDB 3306 端口可用", foreground=COLORS["success"])
        except OSError:
            self.db_status.configure(text="● MariaDB 未连接", foreground="#DC2626")
        finally:
            if hide_loading:
                self.app.hide_loading()


class DiscountPage(ttk.Frame):
    def __init__(self, parent, app: "DWCXApp"):
        super().__init__(parent, style="Page.TFrame")
        self.app = app
        title(self, "车险优惠计算", "直接使用原模块中的 RULES 与计算公式")
        self.module = app.backend.module("discount", DISCOUNT_DIR / "car_insurance_discount_calculator.py")
        form = ttk.LabelFrame(self, text="计算参数", padding=18, style="Card.TLabelframe")
        form.pack(fill="x", padx=36, pady=12)
        self.vars = {
            "car": tk.StringVar(), "noncar": tk.StringVar(), "jq": tk.StringVar(), "score": tk.StringVar(),
            "vehicle": tk.StringVar(value="燃油（含损）"), "use": tk.StringVar(value="家庭自用"),
            "floor": tk.BooleanVar(value=False),
        }
        fields = [("车险保费", "car"), ("非车险保费", "noncar"), ("交强险保费", "jq"), ("OC 分数", "score")]
        for i, (label, key) in enumerate(fields):
            ttk.Label(form, text=label + "：").grid(row=i // 2, column=(i % 2) * 2, sticky="e", padx=8, pady=8)
            ttk.Entry(form, textvariable=self.vars[key]).grid(row=i // 2, column=(i % 2) * 2 + 1, sticky="ew", padx=8, pady=8)
        ttk.Label(form, text="车型：").grid(row=2, column=0, sticky="e", padx=8, pady=8)
        ttk.Combobox(form, textvariable=self.vars["vehicle"], state="readonly", values=["燃油（含损）", "燃油（不含损）", "新能源"]).grid(row=2, column=1, sticky="ew", padx=8)
        ttk.Label(form, text="车辆性质：").grid(row=2, column=2, sticky="e", padx=8, pady=8)
        ttk.Combobox(form, textvariable=self.vars["use"], state="readonly", values=["家庭自用", "非营业企业客车"]).grid(row=2, column=3, sticky="ew", padx=8)
        ttk.Checkbutton(form, text="最终优惠金额不低于 0 元", variable=self.vars["floor"]).grid(row=3, column=1, columnspan=2, sticky="w", padx=8, pady=8)
        for col in (1, 3):
            form.columnconfigure(col, weight=1)
        action = ttk.Frame(self, style="Page.TFrame")
        action.pack(fill="x", padx=36)
        ttk.Button(action, text="计算优惠", style="Primary.TButton", command=self.calculate).pack(side="left")
        ttk.Button(action, text="清空", command=self.clear).pack(side="left", padx=10)
        self.result = tk.Text(self, height=15, bg="white", fg=COLORS["text"], relief="solid", bd=1, font=("Microsoft YaHei UI", 11), padx=14, pady=12)
        self.result.pack(fill="both", expand=True, padx=36, pady=14)

    def calculate(self):
        self.app.show_loading("正在计算优惠金额…", "正在匹配车型、用途和 OC 规则")
        self.after(80, self._calculate_with_loading)

    def _calculate_with_loading(self):
        try:
            self._perform_calculation()
        finally:
            self.app.hide_loading()

    def _perform_calculation(self):
        try:
            car = self.module.parse_money(self.vars["car"].get(), "车险保费")
            noncar = self.module.parse_money(self.vars["noncar"].get(), "非车险保费")
            jq = self.module.parse_money(self.vars["jq"].get(), "交强险保费")
            score = self.module.parse_score(self.vars["score"].get())
            self.module.validate_control_limit(self.vars["vehicle"].get(), score)
        except ValueError as exc:
            self.app.hide_loading()
            self.result.delete("1.0", "end")
            messagebox.showerror("输入错误", str(exc)); return
        rule = self.module.match_rule(self.vars["vehicle"].get(), self.vars["use"].get(), score)
        rate = rule["rate"] if rule else 0.0
        commercial, noncar_discount, jq_discount, final = self.module.calculate_discount(car, noncar, jq, rate)
        if self.vars["floor"].get():
            final = max(final, 0.0)
        output = (
            f"匹配规则：{rule['desc'] if rule else '未匹配到规则，按 0% 处理'}\n\n"
            f"商业车险优惠：{commercial:,.2f} 元（{rate:.0%}）\n"
            f"交强险优惠：{jq_discount:,.2f} 元（{self.module.JQ_RATE:.0%}）\n"
            f"非车险优惠：{noncar_discount:,.2f} 元（{self.module.NON_CAR_RATE:.0%}）\n{'─' * 34}\n"
            f"最终优惠金额：{final:,.2f} 元\n"
            f"原始合计保费：{car + noncar + jq:,.2f} 元\n"
            f"优惠后测算金额：{car + noncar + jq - final:,.2f} 元"
        )
        self.result.delete("1.0", "end"); self.result.insert("1.0", output)

    def clear(self):
        for key in ("car", "noncar", "jq", "score"):
            self.vars[key].set("")
        self.result.delete("1.0", "end")


class DailyPage(AsyncPage):
    def __init__(self, parent, app: "DWCXApp"):
        super().__init__(parent, app)
        title(self, "日常总结", "上传当日报价表和报价记录表，按车牌匹配后生成在线文档")
        source_card = tk.Frame(self, bg=COLORS["card"], highlightbackground="#E5E7EB", highlightthickness=1)
        source_card.pack(fill="x", padx=36, pady=(0, 12))

        card_header = tk.Frame(source_card, bg=COLORS["card"])
        card_header.pack(fill="x", padx=20, pady=(15, 8))
        tk.Label(card_header, text="生成所需文件", bg=COLORS["card"], fg=COLORS["text"], font=("Microsoft YaHei UI", 11, "bold")).pack(side="left")
        tk.Label(card_header, text="2 个 Excel 文件", bg=COLORS["accent_soft"], fg=COLORS["accent"], font=("Microsoft YaHei UI", 8), padx=8, pady=3).pack(side="right")

        form = tk.Frame(source_card, bg=COLORS["card"])
        form.pack(fill="x", padx=14, pady=(0, 15))
        self.daily_quote_path = tk.StringVar()
        self.quote_record_path = tk.StringVar()
        self.date = tk.StringVar(value=datetime.now().strftime("%m%d"))

        self._add_file_row(form, 0, "01", "当日报价表", "用于筛选目标日期内的报价业务", self.daily_quote_path, "daily_quote")
        self._add_file_row(form, 1, "02", "当日报价记录表", "用于按车牌号补充自主定价系数和核保信息", self.quote_record_path, "quote_record")

        separator = tk.Frame(form, bg="#E5E7EB", height=1)
        separator.grid(row=2, column=0, columnspan=4, sticky="ew", padx=6, pady=(8, 10))
        tk.Label(form, text="日期", bg=COLORS["card"], fg=COLORS["muted"], font=("Microsoft YaHei UI", 9, "bold")).grid(row=3, column=1, sticky="w", padx=(8, 12), pady=5)
        ttk.Entry(form, textvariable=self.date, width=16).grid(row=3, column=2, sticky="w", padx=6, pady=5)
        tk.Label(form, text="MMDD 格式，例如 0716", bg=COLORS["card"], fg="#94A3B8", font=("Microsoft YaHei UI", 8)).grid(row=3, column=3, sticky="w", padx=8)
        form.columnconfigure(2, weight=1)

        actions = ttk.Frame(self, style="Page.TFrame"); actions.pack(fill="x", padx=36, pady=(0, 4))
        self.generate_button = ttk.Button(actions, text="开始生成  →", style="Primary.TButton", command=self.start)
        self.generate_button.pack(side="left")
        ttk.Button(actions, text="打开日常总结目录", command=lambda: open_path(DAILY_DIR)).pack(side="left", padx=10)
        ttk.Label(actions, text="输出文件将保存在当日报价表所在目录", foreground=COLORS["muted"], background=COLORS["bg"]).pack(side="right")
        self.log = log_widget(self)

    def _add_file_row(self, parent, row, number, name, description, variable, kind):
        tk.Label(parent, text=number, bg="#F1F5F9", fg="#64748B", font=("Segoe UI", 8, "bold"), width=3, pady=5).grid(row=row, column=0, padx=(6, 8), pady=6)
        label_box = tk.Frame(parent, bg=COLORS["card"])
        label_box.grid(row=row, column=1, sticky="w", padx=(0, 12), pady=6)
        tk.Label(label_box, text=name + "  *", bg=COLORS["card"], fg=COLORS["text"], font=("Microsoft YaHei UI", 9, "bold")).pack(anchor="w")
        tk.Label(label_box, text=description, bg=COLORS["card"], fg="#94A3B8", font=("Microsoft YaHei UI", 8)).pack(anchor="w", pady=(2, 0))
        ttk.Entry(parent, textvariable=variable).grid(row=row, column=2, sticky="ew", padx=6, pady=6)
        ttk.Button(parent, text="选择 Excel", command=lambda: self.choose(kind)).grid(row=row, column=3, padx=8, pady=6)

    def choose(self, kind):
        path = filedialog.askopenfilename(initialdir=DAILY_DIR, title="选择当日报价表" if kind == "daily_quote" else "选择当日报价记录表", filetypes=[("Excel 文件", "*.xlsx *.xls")])
        if path:
            (self.daily_quote_path if kind == "daily_quote" else self.quote_record_path).set(path)

    def start(self):
        source = Path(self.daily_quote_path.get().strip())
        quote_record = Path(self.quote_record_path.get().strip())
        if not source.is_file(): messagebox.showerror("缺少当日报价表", "请选择有效的当日报价表 Excel 文件。"); return
        if not quote_record.is_file(): messagebox.showerror("缺少报价记录表", "请选择有效的当日报价记录表 Excel 文件。"); return
        date_text = self.date.get().strip()

        def task():
            module = self.app.backend.module("daily", DAILY_DIR / "process_excel.py")
            target_date = module.parse_mmdd_date(date_text) if date_text else module.infer_target_date(str(source))
            stream = io.StringIO()
            with contextlib.redirect_stdout(stream):
                module.process_excel(str(source), target_date=target_date, quote_file=str(quote_record))
            return stream.getvalue()

        self.generate_button.configure(state="disabled", text="生成中…")
        self.write_log(f"[{datetime.now():%H:%M:%S}] 当日报价表：{source.name}")
        self.write_log(f"[{datetime.now():%H:%M:%S}] 报价记录表：{quote_record.name}")
        self.run_task(task, self._generation_complete, "正在生成日常总结…")

    def _generation_complete(self, output):
        self.generate_button.configure(state="normal", text="开始生成  →")
        self.write_log(str(output))
        messagebox.showinfo("处理完成", "日常总结和车牌匹配结果已生成。")

    def on_task_failure(self):
        self.generate_button.configure(state="normal", text="重新生成  →")


class FeePage(AsyncPage):
    def __init__(self, parent, app: "DWCXApp"):
        super().__init__(parent, app)
        title(self, "月初手续费结算", "上传手续费数据和结算模板，生成对应业务类型的结算单")

        source_card = tk.Frame(self, bg=COLORS["card"], highlightbackground="#E5E7EB", highlightthickness=1)
        source_card.pack(fill="x", padx=36, pady=(0, 12))
        card_header = tk.Frame(source_card, bg=COLORS["card"])
        card_header.pack(fill="x", padx=20, pady=(15, 8))
        tk.Label(card_header, text="结算文件", bg=COLORS["card"], fg=COLORS["text"], font=("Microsoft YaHei UI", 11, "bold")).pack(side="left")
        tk.Label(card_header, text="模板决定车险 / 非车业务类型", bg=COLORS["accent_soft"], fg=COLORS["accent"], font=("Microsoft YaHei UI", 8), padx=9, pady=3).pack(side="right")

        self.fee_data_path = tk.StringVar()
        self.car_template_path = tk.StringVar()
        self.noncar_template_path = tk.StringVar()
        self.month = tk.StringVar(value=str(datetime.now().month))
        self.channel = tk.StringVar(value="华瑞")

        form = tk.Frame(source_card, bg=COLORS["card"])
        form.pack(fill="x", padx=14, pady=(0, 15))
        self._add_fee_file_row(form, 0, "01", "手续费数据文件", "包含保单号、险种产品及手续费明细", self.fee_data_path, "data")
        self._add_fee_file_row(form, 1, "02", "车险结算模板", "可选，用于生成车险业务结算单", self.car_template_path, "car_template", required=False)
        self._add_fee_file_row(form, 2, "03", "非车险结算模板", "可选，选择后将同时生成非车险结算单", self.noncar_template_path, "noncar_template", required=False)

        separator = tk.Frame(form, bg="#E5E7EB", height=1)
        separator.grid(row=3, column=0, columnspan=5, sticky="ew", padx=6, pady=(8, 10))
        tk.Label(form, text="结算月份", bg=COLORS["card"], fg=COLORS["muted"], font=("Microsoft YaHei UI", 9, "bold")).grid(row=4, column=1, sticky="w", padx=(0, 8), pady=5)
        ttk.Combobox(form, textvariable=self.month, state="readonly", values=[str(i) for i in range(1, 13)], width=10).grid(row=4, column=2, sticky="w", padx=6, pady=5)
        tk.Label(form, text="渠道名称", bg=COLORS["card"], fg=COLORS["muted"], font=("Microsoft YaHei UI", 9, "bold")).grid(row=4, column=3, sticky="e", padx=(18, 6), pady=5)
        ttk.Entry(form, textvariable=self.channel, width=24).grid(row=4, column=4, sticky="ew", padx=8, pady=5)
        form.columnconfigure(2, weight=1)

        actions = ttk.Frame(self, style="Page.TFrame"); actions.pack(fill="x", padx=36, pady=(0, 4))
        self.fee_generate_button = ttk.Button(actions, text="生成结算单  →", style="Primary.TButton", command=self.start)
        self.fee_generate_button.pack(side="left")
        ttk.Button(actions, text="打开输出目录", command=self.open_output_directory).pack(side="left", padx=10)
        self.fee_status = ttk.Label(actions, text="等待选择数据和模板", foreground=COLORS["muted"], background=COLORS["bg"])
        self.fee_status.pack(side="right")
        self.log = log_widget(self)

    def _add_fee_file_row(self, parent, row, number, name, description, variable, kind, required=True):
        tk.Label(parent, text=number, bg="#F1F5F9", fg="#64748B", font=("Segoe UI", 8, "bold"), width=3, pady=5).grid(row=row, column=0, padx=(6, 8), pady=6)
        label_box = tk.Frame(parent, bg=COLORS["card"])
        label_box.grid(row=row, column=1, sticky="w", padx=(0, 12), pady=6)
        suffix = "  *" if required else "  （可选）"
        tk.Label(label_box, text=name + suffix, bg=COLORS["card"], fg=COLORS["text"], font=("Microsoft YaHei UI", 9, "bold")).pack(anchor="w")
        tk.Label(label_box, text=description, bg=COLORS["card"], fg="#94A3B8", font=("Microsoft YaHei UI", 8)).pack(anchor="w", pady=(2, 0))
        ttk.Entry(parent, textvariable=variable).grid(row=row, column=2, columnspan=2, sticky="ew", padx=6, pady=6)
        ttk.Button(parent, text="选择 Excel", command=lambda: self.choose_file(kind)).grid(row=row, column=4, padx=8, pady=6)

    def choose_file(self, kind):
        initial_dir = FEE_DIR if kind == "data" else FEE_DIR / "模板"
        titles = {
            "data": "选择手续费数据文件",
            "car_template": "选择车险结算模板",
            "noncar_template": "选择非车险结算模板",
        }
        path = filedialog.askopenfilename(initialdir=initial_dir, title=titles[kind], filetypes=[("Excel 文件", "*.xlsx *.xlsm")])
        if path:
            variables = {
                "data": self.fee_data_path,
                "car_template": self.car_template_path,
                "noncar_template": self.noncar_template_path,
            }
            variables[kind].set(path)

    def open_output_directory(self):
        data_file = Path(self.fee_data_path.get().strip())
        open_path(data_file.parent / "输出结果" if data_file.is_file() else FEE_DIR)

    def start(self):
        data_file = Path(self.fee_data_path.get().strip())
        car_template_text = self.car_template_path.get().strip()
        car_template = Path(car_template_text) if car_template_text else None
        noncar_template_text = self.noncar_template_path.get().strip()
        noncar_template = Path(noncar_template_text) if noncar_template_text else None
        channel = self.channel.get().strip()
        month = self.month.get().strip()
        if not data_file.is_file(): messagebox.showerror("缺少手续费数据", "请选择有效的手续费数据 Excel 文件。"); return
        if car_template is None and noncar_template is None: messagebox.showerror("缺少结算模板", "请至少选择一个车险或非车险结算模板。"); return
        if car_template is not None and not car_template.is_file(): messagebox.showerror("车险模板无效", "请选择有效的车险结算模板 Excel 文件，或清空该输入框。"); return
        if noncar_template is not None and not noncar_template.is_file(): messagebox.showerror("非车险模板无效", "请选择有效的非车险结算模板 Excel 文件，或清空该输入框。"); return
        if not channel: messagebox.showerror("缺少渠道", "请输入渠道名称，例如：华瑞。"); return

        def task():
            module = self.app.backend.module("fee_settlement", FEE_DIR / "generate_fee_settlement_1.py")
            stream = io.StringIO()
            with contextlib.redirect_stdout(stream):
                result = module.generate_settlements_from_files(data_file, car_template, noncar_template, month, channel)
            return result, stream.getvalue()

        self.fee_generate_button.configure(state="disabled", text="生成中…")
        self.fee_status.configure(text="正在读取并填充模板…", foreground=COLORS["warning"])
        self.write_log(f"[{datetime.now():%H:%M:%S}] 手续费数据：{data_file.name}")
        if car_template is not None:
            self.write_log(f"[{datetime.now():%H:%M:%S}] 车险模板：{car_template.name}")
        if noncar_template is not None:
            self.write_log(f"[{datetime.now():%H:%M:%S}] 非车险模板：{noncar_template.name}")
        self.run_task(task, self._generation_complete, "正在生成手续费结算单…")

    def _generation_complete(self, payload):
        batch, output = payload
        results = batch["results"]
        self.fee_generate_button.configure(state="normal", text="生成结算单  →")
        result_summary = "、".join(f"{item['business_label']} {item['rows']} 条" for item in results)
        self.fee_status.configure(text=f"已生成 {len(results)} 份 · {result_summary}", foreground=COLORS["success"])
        self.write_log(output)
        file_summary = "\n".join(f"{item['business_label']}：{item['rows']} 条 · {Path(item['output']).name}" for item in results)
        messagebox.showinfo("处理完成", f"手续费结算单已生成 {len(results)} 份。\n\n{file_summary}")

    def on_task_failure(self):
        self.fee_generate_button.configure(state="normal", text="重新生成  →")
        self.fee_status.configure(text="生成失败，请查看日志", foreground="#DC2626")


class OCRPage(AsyncPage):
    def __init__(self, parent, app: "DWCXApp"):
        super().__init__(parent, app)
        title(self, "身份证 OCR", "识别身份证正反面，维护数据库记录并下载原图")
        card = ttk.LabelFrame(self, text="模块说明", padding=22, style="Card.TLabelframe"); card.pack(fill="x", padx=36, pady=12)
        ttk.Label(card, text="OCR 模块功能较完整，将作为独立业务窗口启动。", font=("Microsoft YaHei UI", 12, "bold")).pack(anchor="w")
        ttk.Label(card, text="数据库：id_card  ·  主机：localhost:3306  ·  用户：root", foreground=COLORS["muted"]).pack(anchor="w", pady=(8, 0))
        ttk.Label(card, text="首次启动 OCR 引擎可能需要数十秒。", foreground=COLORS["warning"]).pack(anchor="w", pady=(8, 0))
        actions = ttk.Frame(self, style="Page.TFrame"); actions.pack(fill="x", padx=36, pady=4)
        ttk.Button(actions, text="启动身份证 OCR", style="Primary.TButton", command=self.launch).pack(side="left")
        ttk.Button(actions, text="测试数据库", command=self.test_database).pack(side="left", padx=10)
        ttk.Button(actions, text="打开 OCR 目录", command=lambda: open_path(OCR_DIR)).pack(side="left")
        self.log = log_widget(self)

    def launch(self):
        script = OCR_DIR / "app_gui.py"
        self.app.show_loading("正在启动身份证 OCR…", "首次启动可能需要数十秒")
        try:
            process, started = self.app.backend.launch_once("ocr", [sys.executable, str(script)], OCR_DIR)
            if started:
                self.write_log(f"[{datetime.now():%H:%M:%S}] 已启动 OCR 窗口（PID {process.pid}）")
            else:
                self.write_log(f"[{datetime.now():%H:%M:%S}] OCR 窗口已在运行（PID {process.pid}）")
                messagebox.showinfo("已经运行", "身份证 OCR 窗口已经打开，无需重复启动。")
        except Exception as exc: messagebox.showerror("启动失败", str(exc))
        finally:
            self.app.hide_loading()

    def test_database(self):
        def task():
            return self.app.backend.database_count()
        self.run_task(task, lambda count: (self.write_log(f"数据库连接成功，当前 {count} 条身份证记录。"), messagebox.showinfo("连接成功", f"数据库连接正常，当前 {count} 条记录。")), "正在测试数据库连接…")


class WeeklyPage(AsyncPage):
    def __init__(self, parent, app: "DWCXApp"):
        super().__init__(parent, app)
        title(self, "周末总结", "汇总本周询单与生效保单，生成报告及数据检查表")

        input_card = tk.Frame(self, bg=COLORS["card"], highlightbackground="#E5E7EB", highlightthickness=1)
        input_card.pack(fill="x", padx=36, pady=(0, 10))
        card_header = tk.Frame(input_card, bg=COLORS["card"])
        card_header.pack(fill="x", padx=18, pady=(13, 7))
        tk.Label(card_header, text="统计数据源", bg=COLORS["card"], fg=COLORS["text"], font=("Microsoft YaHei UI", 11, "bold")).pack(side="left")
        self.week_range = tk.Label(card_header, bg=COLORS["accent_soft"], fg=COLORS["accent"], font=("Microsoft YaHei UI", 8), padx=9, pady=3)
        self.week_range.pack(side="right")

        samples = sorted(WEEKLY_DIR.glob("[0-9][0-9][0-9][0-9].xlsx"), reverse=True)
        default_order = str(samples[0]) if samples else ""
        default_policy_path = APP_ROOT / "数据基础" / "出单保单信息.xlsx"
        self.weekly_order_path = tk.StringVar(value=default_order)
        self.weekly_policy_path = tk.StringVar(value=str(default_policy_path) if default_policy_path.is_file() else "")
        default_date = Path(default_order).stem if default_order and len(Path(default_order).stem) == 4 else datetime.now().strftime("%m%d")
        self.weekly_date = tk.StringVar(value=default_date)

        form = tk.Frame(input_card, bg=COLORS["card"])
        form.pack(fill="x", padx=13, pady=(0, 12))
        self._add_input_row(form, 0, "询单/订单表", "统计询单并为保单匹配代理人", self.weekly_order_path, "order")
        self._add_input_row(form, 1, "保单信息表", "统计本周状态为“生效”的保单", self.weekly_policy_path, "policy")
        tk.Label(form, text="统计日期", bg=COLORS["card"], fg=COLORS["muted"], font=("Microsoft YaHei UI", 9, "bold")).grid(row=2, column=0, sticky="w", padx=8, pady=(7, 4))
        date_entry = ttk.Entry(form, textvariable=self.weekly_date, width=14)
        date_entry.grid(row=2, column=1, sticky="w", padx=6, pady=(7, 4))
        date_entry.bind("<KeyRelease>", lambda _event: self._update_week_range())
        tk.Label(form, text="MMDD，例如 0718 · 周期按周六至周五计算", bg=COLORS["card"], fg="#94A3B8", font=("Microsoft YaHei UI", 8)).grid(row=2, column=2, sticky="w", padx=6, pady=(7, 4))
        form.columnconfigure(1, weight=1)
        self._update_week_range()

        actions = ttk.Frame(self, style="Page.TFrame")
        actions.pack(fill="x", padx=36, pady=(0, 8))
        self.weekly_generate_button = ttk.Button(actions, text="生成周末总结  →", style="Primary.TButton", command=self.generate)
        self.weekly_generate_button.pack(side="left")
        ttk.Button(actions, text="打开输出目录", command=self.open_output_directory).pack(side="left", padx=10)
        ttk.Button(actions, text="刷新报告", command=self.refresh_reports).pack(side="left")
        self.generate_status = ttk.Label(actions, text="等待生成", foreground=COLORS["muted"], background=COLORS["bg"])
        self.generate_status.pack(side="right")

        body = ttk.Frame(self, style="Page.TFrame")
        body.pack(fill="both", expand=True, padx=36, pady=(0, 16))
        report_panel = tk.Frame(body, bg="#FFFFFF", highlightbackground="#E5E7EB", highlightthickness=1, width=245)
        report_panel.pack(side="left", fill="y")
        report_panel.pack_propagate(False)
        tk.Label(report_panel, text="历史报告", bg="#FFFFFF", fg=COLORS["text"], font=("Microsoft YaHei UI", 10, "bold"), anchor="w", padx=14, pady=11).pack(fill="x")
        self.listbox = tk.Listbox(report_panel, bd=0, highlightthickness=0, activestyle="none", selectbackground="#DBEAFE", selectforeground="#1E3A8A", font=("Microsoft YaHei UI", 9), exportselection=False)
        self.listbox.pack(fill="both", expand=True, padx=7, pady=(0, 7))
        self.listbox.bind("<<ListboxSelect>>", self.preview)

        self.tabs = ttk.Notebook(body)
        self.tabs.pack(side="left", fill="both", expand=True, padx=(12, 0))
        self.preview_tab = ttk.Frame(self.tabs, style="Card.TFrame")
        log_tab = ttk.Frame(self.tabs, style="Card.TFrame")
        self.tabs.add(self.preview_tab, text="  报告预览  ")
        self.tabs.add(log_tab, text="  运行日志  ")
        self.preview_text = tk.Text(self.preview_tab, bg="white", fg="#334155", relief="flat", wrap="word", font=("Microsoft YaHei UI", 10), padx=18, pady=16)
        self.preview_text.pack(fill="both", expand=True)
        self.preview_text.configure(state="disabled")
        self.log = tk.Text(log_tab, bg="#111827", fg="#E5E7EB", insertbackground="white", relief="flat", wrap="word", font=("Consolas", 10), padx=16, pady=14)
        self.log.pack(fill="both", expand=True)
        self.log.configure(state="disabled")
        self.refresh_reports()

    def _add_input_row(self, parent, row, label, description, variable, kind):
        label_box = tk.Frame(parent, bg=COLORS["card"])
        label_box.grid(row=row, column=0, sticky="w", padx=8, pady=5)
        tk.Label(label_box, text=label + "  *", bg=COLORS["card"], fg=COLORS["text"], font=("Microsoft YaHei UI", 9, "bold")).pack(anchor="w")
        tk.Label(label_box, text=description, bg=COLORS["card"], fg="#94A3B8", font=("Microsoft YaHei UI", 8)).pack(anchor="w", pady=(1, 0))
        ttk.Entry(parent, textvariable=variable).grid(row=row, column=1, sticky="ew", padx=6, pady=5)
        ttk.Button(parent, text="选择 Excel", command=lambda: self.choose_file(kind)).grid(row=row, column=2, padx=8, pady=5)

    def choose_file(self, kind):
        path = filedialog.askopenfilename(initialdir=WEEKLY_DIR if kind == "order" else APP_ROOT / "数据基础", title="选择询单/订单表" if kind == "order" else "选择保单信息表", filetypes=[("Excel 文件", "*.xlsx *.xls")])
        if not path:
            return
        if kind == "order":
            self.weekly_order_path.set(path)
            stem = Path(path).stem
            if len(stem) == 4 and stem.isdigit():
                self.weekly_date.set(stem)
                self._update_week_range()
        else:
            self.weekly_policy_path.set(path)

    def _update_week_range(self):
        text = self.weekly_date.get().strip()
        try:
            run_date = datetime.strptime(f"{datetime.now().year}{text}", "%Y%m%d").date()
            week_start = run_date - timedelta(days=run_date.weekday() - 5) if run_date.weekday() >= 5 else run_date - timedelta(days=run_date.weekday() + 2)
            self.week_range.configure(text=f"统计周期  {week_start:%m.%d} — {(week_start + timedelta(days=6)):%m.%d}")
        except ValueError:
            self.week_range.configure(text="请输入有效 MMDD 日期")

    def open_output_directory(self):
        order_file = Path(self.weekly_order_path.get().strip())
        open_path(order_file.parent if order_file.is_file() else WEEKLY_DIR)

    def generate(self):
        order_file = Path(self.weekly_order_path.get().strip())
        policy_file = Path(self.weekly_policy_path.get().strip())
        if not order_file.is_file():
            messagebox.showerror("缺少订单表", "请选择有效的询单/订单 Excel 文件。")
            return
        if not policy_file.is_file():
            messagebox.showerror("缺少保单表", "请选择有效的保单信息 Excel 文件。")
            return
        date_text = self.weekly_date.get().strip()

        def task():
            module = self.app.backend.module("weekend_summary", WEEKLY_DIR / "weekend_summary.py")
            run_date = module.parse_mmdd_date(date_text)
            stream = io.StringIO()
            with contextlib.redirect_stdout(stream):
                result = module.process_weekend_summary(str(order_file), str(policy_file), run_date=run_date)
            return result, stream.getvalue()

        self.weekly_generate_button.configure(state="disabled", text="生成中…")
        self.generate_status.configure(text="正在统计并生成报告…", foreground=COLORS["warning"])
        self.tabs.select(1)
        self.write_log(f"[{datetime.now():%H:%M:%S}] 订单表：{order_file.name}")
        self.write_log(f"[{datetime.now():%H:%M:%S}] 保单表：{policy_file.name}")
        self.run_task(task, self._generation_complete, "正在汇总本周业务数据…")

    def _generation_complete(self, payload):
        result, output = payload
        self.weekly_generate_button.configure(state="normal", text="生成周末总结  →")
        self.generate_status.configure(text=f"已生成 · {result['total_count']} 笔 · {result['total_amount']:,.2f} 元", foreground=COLORS["success"])
        self.write_log(output)
        self.refresh_reports(Path(result["report_path"]))
        self.tabs.select(self.preview_tab)
        messagebox.showinfo("生成完成", f"周末总结已生成。\n\n生效出单：{result['total_count']} 笔\n生效保费：{result['total_amount']:,.2f} 元\n未匹配代理人：{result['unmatched_count']} 笔")

    def on_task_failure(self):
        self.weekly_generate_button.configure(state="normal", text="重新生成  →")
        self.generate_status.configure(text="生成失败，请查看运行日志", foreground="#DC2626")
        self.tabs.select(1)

    def refresh_reports(self, extra_path=None):
        reports = list(WEEKLY_DIR.glob("*_周末总结结果*.txt"))
        if extra_path and Path(extra_path).is_file():
            reports.append(Path(extra_path))
        self.reports = sorted(set(reports), key=lambda path: path.stat().st_mtime, reverse=True)
        self.listbox.delete(0, "end")
        for path in self.reports:
            self.listbox.insert("end", path.name)
        if self.reports:
            self.listbox.selection_set(0)
            self.listbox.activate(0)
            self.preview()
        else:
            self._set_preview("暂无周末总结报告。\n\n请选择订单表和保单信息表后点击“生成周末总结”。")

    def preview(self, _event=None):
        selected = self.listbox.curselection()
        if not selected: return
        text = self.reports[selected[0]].read_text(encoding="utf-8", errors="replace")
        self._set_preview(text)

    def _set_preview(self, text):
        self.preview_text.configure(state="normal")
        self.preview_text.delete("1.0", "end")
        self.preview_text.insert("1.0", text)
        self.preview_text.configure(state="disabled")


class HistoryPage(ttk.Frame):
    def __init__(self, parent, app: "DWCXApp"):
        super().__init__(parent, style="Page.TFrame")
        self.app = app
        title(self, "历史数据", "查询和查看历史数据压缩包中的文件清单")
        actions = ttk.Frame(self, style="Page.TFrame"); actions.pack(fill="x", padx=36, pady=(2, 8))
        ttk.Button(actions, text="打开历史数据目录", command=lambda: open_path(HISTORY_DIR)).pack(side="left")
        ttk.Button(actions, text="刷新清单", command=lambda: self.refresh(show_loading=True)).pack(side="left", padx=10)

        search_card = tk.Frame(self, bg=COLORS["card"], highlightbackground="#E5E7EB", highlightthickness=1)
        search_card.pack(fill="x", padx=36, pady=(0, 10))
        tk.Label(search_card, text="查询历史文件", bg=COLORS["card"], fg=COLORS["text"], font=("Microsoft YaHei UI", 10, "bold"), padx=15, pady=12).pack(side="left")
        self.query_text = tk.StringVar()
        query_entry = ttk.Entry(search_card, textvariable=self.query_text, width=34)
        query_entry.pack(side="left", fill="x", expand=True, padx=(4, 8), pady=9)
        query_entry.bind("<Return>", lambda _event: self.apply_query())
        ttk.Button(search_card, text="查询", style="Analysis.TButton", command=self.apply_query).pack(side="left", padx=(0, 7), pady=7)
        ttk.Button(search_card, text="清空", command=self.clear_query).pack(side="left", padx=(0, 12), pady=7)

        result_header = ttk.Frame(self, style="Page.TFrame")
        result_header.pack(fill="x", padx=36, pady=(0, 6))
        ttk.Label(result_header, text="文件清单", foreground=COLORS["text"], background=COLORS["bg"], font=("Microsoft YaHei UI", 10, "bold")).pack(side="left")
        self.info = ttk.Label(result_header, foreground=COLORS["muted"])
        self.info.pack(side="right")

        tree_card = tk.Frame(self, bg="#FFFFFF", highlightbackground="#E5E7EB", highlightthickness=1)
        tree_card.pack(fill="both", expand=True, padx=36, pady=(0, 22))
        tree_wrap = ttk.Frame(tree_card, style="Card.TFrame")
        tree_wrap.pack(fill="both", expand=True, padx=9, pady=9)
        self.tree = ttk.Treeview(tree_wrap, columns=("archive", "name", "size"), show="headings", style="Analysis.Treeview")
        self.tree.heading("archive", text="所属压缩包")
        self.tree.heading("name", text="档案内文件")
        self.tree.heading("size", text="大小")
        self.tree.column("archive", width=190, minwidth=130)
        self.tree.column("name", width=560, minwidth=260)
        self.tree.column("size", width=110, minwidth=85, anchor="e")
        vertical = ttk.Scrollbar(tree_wrap, orient="vertical", command=self.tree.yview)
        horizontal = ttk.Scrollbar(tree_wrap, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        vertical.grid(row=0, column=1, sticky="ns")
        horizontal.grid(row=1, column=0, sticky="ew")
        tree_wrap.rowconfigure(0, weight=1)
        tree_wrap.columnconfigure(0, weight=1)
        self.tree.tag_configure("even", background="#F8FAFC")
        self.tree.tag_configure("odd", background="#FFFFFF")
        self.records = []
        self.archive_count = 0
        self.refresh()

    def refresh(self, show_loading=False):
        if show_loading:
            self.app.show_loading("正在刷新历史数据…", "正在读取压缩包文件清单")
            self.after(80, lambda: self._load_records(hide_loading=True))
            return
        self._load_records()

    def _load_records(self, hide_loading=False):
        archives = sorted(HISTORY_DIR.glob("*.zip"), key=lambda path: path.name.casefold())
        records = []
        try:
            for archive in archives:
                try:
                    with zipfile.ZipFile(archive) as zf:
                        for item in zf.infolist():
                            if not item.is_dir():
                                records.append((archive.name, item.filename, item.file_size))
                except zipfile.BadZipFile:
                    records.append((archive.name, "压缩包损坏，无法读取", None))
            self.records = records
            self.archive_count = len(archives)
            self.apply_query()
        finally:
            if hide_loading:
                self.app.hide_loading()

    def apply_query(self):
        keyword = self.query_text.get().strip().casefold()
        matches = [record for record in self.records if not keyword or keyword in record[0].casefold() or keyword in record[1].casefold()]
        self.tree.delete(*self.tree.get_children())
        for index, (archive, name, size) in enumerate(matches):
            self.tree.insert("", "end", values=(archive, name, self._format_size(size)), tags=("even" if index % 2 == 0 else "odd",))
        if keyword:
            self.info.configure(text=f"查询“{self.query_text.get().strip()}” · 命中 {len(matches)} / {len(self.records)} 个文件")
        else:
            self.info.configure(text=f"{self.archive_count} 个压缩包 · {len(self.records)} 个文件")

    def clear_query(self):
        self.query_text.set("")
        self.apply_query()

    @staticmethod
    def _format_size(size):
        if size is None:
            return "—"
        if size >= 1024 * 1024:
            return f"{size / 1024 / 1024:.2f} MB"
        return f"{size / 1024:.1f} KB"


class DataAnalysisPage(AsyncPage):
    MODES = ["报价分析", "保单分析", "联合分析", "数据质量"]

    def __init__(self, parent, app: "DWCXApp"):
        super().__init__(parent, app)
        self.report = None
        self.current_chart: list[tuple[str, float]] = []

        header = ttk.Frame(self, style="Page.TFrame")
        header.pack(fill="x", padx=40, pady=(26, 13))
        ttk.Label(header, text="BUSINESS INTELLIGENCE", foreground=COLORS["accent"], background=COLORS["bg"], font=("Segoe UI", 8, "bold")).pack(anchor="w")
        ttk.Label(header, text="数据分析", style="Title.TLabel").pack(anchor="w", pady=(2, 0))
        ttk.Label(header, text="将报价与保单数据转化为可读的业务指标、分布和关键结论", style="Subtitle.TLabel").pack(anchor="w", pady=(4, 0))

        source_card = tk.Frame(self, bg=COLORS["card"], highlightbackground="#E5E7EB", highlightthickness=1)
        source_card.pack(fill="x", padx=40, pady=(0, 11))
        source_header = tk.Frame(source_card, bg=COLORS["card"])
        source_header.pack(fill="x", padx=18, pady=(13, 8))
        tk.Label(source_header, text="数据源与分析方式", bg=COLORS["card"], fg=COLORS["text"], font=("Microsoft YaHei UI", 11, "bold")).pack(side="left")
        tk.Label(source_header, text="支持 .xlsx 文件", bg=COLORS["accent_soft"], fg=COLORS["accent"], font=("Microsoft YaHei UI", 8), padx=8, pady=3).pack(side="right")

        form = tk.Frame(source_card, bg=COLORS["card"])
        form.pack(fill="x", padx=12, pady=(0, 13))
        default_dir = APP_ROOT / "数据基础"
        self.quote_path = tk.StringVar(value=str(default_dir / "26年上半年报价数据.xlsx") if (default_dir / "26年上半年报价数据.xlsx").is_file() else "")
        self.policy_path = tk.StringVar(value=str(default_dir / "出单保单信息.xlsx") if (default_dir / "出单保单信息.xlsx").is_file() else "")
        self.mode = tk.StringVar(value="报价分析")
        tk.Label(form, text="报价数据", bg=COLORS["card"], fg=COLORS["muted"], font=("Microsoft YaHei UI", 9)).grid(row=0, column=0, sticky="w", padx=6, pady=5)
        ttk.Entry(form, textvariable=self.quote_path).grid(row=0, column=1, sticky="ew", padx=6)
        ttk.Button(form, text="浏览…", command=lambda: self.choose_file("quote")).grid(row=0, column=2, padx=6)
        tk.Label(form, text="保单数据", bg=COLORS["card"], fg=COLORS["muted"], font=("Microsoft YaHei UI", 9)).grid(row=1, column=0, sticky="w", padx=6, pady=5)
        ttk.Entry(form, textvariable=self.policy_path).grid(row=1, column=1, sticky="ew", padx=6)
        ttk.Button(form, text="浏览…", command=lambda: self.choose_file("policy")).grid(row=1, column=2, padx=6)
        tk.Label(form, text="分析类型", bg=COLORS["card"], fg=COLORS["muted"], font=("Microsoft YaHei UI", 9)).grid(row=0, column=3, sticky="w", padx=(20, 6))
        ttk.Combobox(form, textvariable=self.mode, state="readonly", values=self.MODES, width=14).grid(row=0, column=4, padx=6, sticky="ew")
        self.analyze_button = ttk.Button(form, text="开始分析  →", style="Analysis.TButton", command=self.start_analysis)
        self.analyze_button.grid(row=1, column=4, padx=6, sticky="ew")
        form.columnconfigure(1, weight=1)

        self.kpi_frame = ttk.Frame(self, style="Page.TFrame")
        self.kpi_frame.pack(fill="x", padx=33, pady=(0, 7))
        self._show_empty_kpis()

        toolbar = ttk.Frame(self, style="Page.TFrame")
        toolbar.pack(fill="x", padx=40, pady=(1, 8))
        ttk.Label(toolbar, text="查看维度", foreground=COLORS["text"], background=COLORS["bg"], font=("Microsoft YaHei UI", 9, "bold")).pack(side="left")
        self.section = tk.StringVar()
        self.section_box = ttk.Combobox(toolbar, textvariable=self.section, state="readonly", width=22)
        self.section_box.pack(side="left", padx=(9, 0))
        self.section_box.bind("<<ComboboxSelected>>", lambda _event: self.render_section())
        self.result_title = tk.Label(toolbar, text="●  等待分析", bg="#E5E7EB", fg="#6B7280", font=("Microsoft YaHei UI", 8, "bold"), padx=10, pady=5)
        self.result_title.pack(side="right")

        body = ttk.Frame(self, style="Page.TFrame")
        body.pack(fill="both", expand=True, padx=40, pady=(0, 10))
        chart_card = tk.Frame(body, bg="#FFFFFF", highlightbackground="#E5E7EB", highlightthickness=1, width=320)
        chart_card.pack(side="left", fill="both"); chart_card.pack_propagate(False)
        chart_header = tk.Frame(chart_card, bg="#FFFFFF")
        chart_header.pack(fill="x", padx=17, pady=(14, 4))
        tk.Label(chart_header, text="分布概览", bg="#FFFFFF", fg=COLORS["text"], font=("Microsoft YaHei UI", 11, "bold")).pack(anchor="w")
        tk.Label(chart_header, text="当前维度 Top 8", bg="#FFFFFF", fg=COLORS["muted"], font=("Microsoft YaHei UI", 8)).pack(anchor="w", pady=(2, 0))
        self.chart = tk.Canvas(chart_card, bg="#FFFFFF", highlightthickness=0, width=318)
        self.chart.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.chart.bind("<Configure>", lambda _event: self.draw_chart())

        table_card = tk.Frame(body, bg="#FFFFFF", highlightbackground="#E5E7EB", highlightthickness=1)
        table_card.pack(side="left", fill="both", expand=True, padx=(12, 0))
        table_header = tk.Frame(table_card, bg="#FFFFFF")
        table_header.pack(fill="x", padx=15, pady=(12, 2))
        self.table_title = tk.Label(table_header, text="明细数据", bg="#FFFFFF", fg=COLORS["text"], font=("Microsoft YaHei UI", 11, "bold"))
        self.table_title.pack(side="left")
        self.table_meta = tk.Label(table_header, text="0 条记录", bg="#FFFFFF", fg=COLORS["muted"], font=("Microsoft YaHei UI", 8))
        self.table_meta.pack(side="right")
        tree_wrap = ttk.Frame(table_card, style="Card.TFrame")
        tree_wrap.pack(fill="both", expand=True, padx=10, pady=(7, 10))
        self.tree = ttk.Treeview(tree_wrap, show="headings", style="Analysis.Treeview")
        vertical = ttk.Scrollbar(tree_wrap, orient="vertical", command=self.tree.yview)
        horizontal = ttk.Scrollbar(tree_wrap, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        self.tree.grid(row=0, column=0, sticky="nsew"); vertical.grid(row=0, column=1, sticky="ns"); horizontal.grid(row=1, column=0, sticky="ew")
        tree_wrap.rowconfigure(0, weight=1); tree_wrap.columnconfigure(0, weight=1)
        self.tree.tag_configure("even", background="#F8FAFC")
        self.tree.tag_configure("odd", background="#FFFFFF")

        insight_card = tk.Frame(self, bg=COLORS["accent_soft"], highlightbackground="#BFDBFE", highlightthickness=1)
        insight_card.pack(fill="x", padx=40, pady=(0, 15))
        tk.Label(insight_card, text="关键结论", bg=COLORS["accent_soft"], fg=COLORS["accent"], font=("Microsoft YaHei UI", 9, "bold"), padx=14, pady=10).pack(side="left", anchor="n")
        self.insights = tk.Label(insight_card, text="分析完成后将在这里显示值得关注的业务信息。", bg=COLORS["accent_soft"], fg="#334155", justify="left", anchor="w", wraplength=760, font=("Microsoft YaHei UI", 9), padx=4, pady=10)
        self.insights.pack(side="left", fill="x", expand=True)
        insight_card.bind("<Configure>", lambda event: self.insights.configure(wraplength=max(event.width - 130, 240)))

    def choose_file(self, kind: str):
        path = filedialog.askopenfilename(initialdir=APP_ROOT / "数据基础", filetypes=[("Excel 文件", "*.xlsx")])
        if path:
            (self.quote_path if kind == "quote" else self.policy_path).set(path)

    def _show_empty_kpis(self):
        self.render_kpis([("—", "等待分析", ""), ("—", "等待分析", ""), ("—", "等待分析", ""), ("—", "等待分析", "")])

    def render_kpis(self, kpis):
        for child in self.kpi_frame.winfo_children(): child.destroy()
        accents = [COLORS["accent"], "#059669", "#D97706", "#7C3AED"]
        for index, (label, value, note) in enumerate(kpis):
            accent = accents[index % len(accents)]
            card = tk.Frame(self.kpi_frame, bg="#FFFFFF", highlightbackground="#E5E7EB", highlightthickness=1)
            card.grid(row=0, column=index, sticky="nsew", padx=7, pady=3)
            tk.Frame(card, bg=accent, height=3).pack(fill="x")
            tk.Label(card, text=label, bg="#FFFFFF", fg="#64748B", font=("Microsoft YaHei UI", 9)).pack(anchor="w", padx=15, pady=(9, 1))
            tk.Label(card, text=value, bg="#FFFFFF", fg="#0F172A", font=("Segoe UI", 17, "bold")).pack(anchor="w", padx=15)
            tk.Label(card, text=note or " ", bg="#FFFFFF", fg="#94A3B8", font=("Microsoft YaHei UI", 8)).pack(anchor="w", padx=15, pady=(1, 9))
            self.kpi_frame.columnconfigure(index, weight=1)

    def start_analysis(self):
        mode = self.mode.get()
        quote = self.quote_path.get().strip()
        policy = self.policy_path.get().strip()
        if mode == "报价分析" and not quote: messagebox.showerror("缺少文件", "请选择报价数据 Excel。"); return
        if mode == "保单分析" and not policy: messagebox.showerror("缺少文件", "请选择保单数据 Excel。"); return
        if mode == "联合分析" and (not quote or not policy): messagebox.showerror("缺少文件", "联合分析需要报价表和保单表。"); return
        if mode == "数据质量" and not (quote or policy): messagebox.showerror("缺少文件", "请至少选择一个 Excel 文件。"); return

        def task():
            module = self.app.backend.module("data_analysis", APP_ROOT / "data_analysis.py")
            return module.run_analysis(mode, quote if quote else "", policy if policy else "")
        self.result_title.configure(text="●  正在分析", bg="#FEF3C7", fg="#92400E")
        self.analyze_button.configure(state="disabled", text="分析中…")
        self.run_task(task, self.show_report, "正在读取并分析业务数据…")

    def show_report(self, report):
        self.report = report
        self.analyze_button.configure(state="normal", text="开始分析  →")
        self.result_title.configure(text="●  分析完成", bg="#DCFCE7", fg="#166534")
        self.render_kpis(report.kpis)
        names = list(report.tables)
        self.section_box.configure(values=names)
        self.section.set(names[0] if names else "")
        self.insights.configure(text="  •  " + "\n  •  ".join(report.insights) if report.insights else "暂无需要特别关注的结论。")
        self.render_section()
        messagebox.showinfo("分析完成", f"{report.title}已生成，共 {len(names)} 个分析维度。")

    def on_task_failure(self):
        self.analyze_button.configure(state="normal", text="重新分析  →")
        self.result_title.configure(text="●  分析失败", bg="#FEE2E2", fg="#991B1B")

    def render_section(self):
        if not self.report or self.section.get() not in self.report.tables: return
        section_name = self.section.get()
        table = self.report.tables[section_name]
        self.table_title.configure(text=section_name)
        self.table_meta.configure(text=f"{len(table.rows):,} 条记录")
        self.tree.delete(*self.tree.get_children())
        self.tree.configure(columns=table.columns)
        for column in table.columns:
            self.tree.heading(column, text=column)
            width = 230 if column in ("代理人/渠道", "渠道", "业务方案", "字段") else 110
            self.tree.column(column, width=width, minwidth=80, anchor="w" if width > 150 else "center")
        for index, row in enumerate(table.rows):
            self.tree.insert("", "end", values=["" if value is None else value for value in row], tags=("even" if index % 2 == 0 else "odd",))
        self.current_chart = self.report.charts.get(section_name, [])
        self.draw_chart()

    def draw_chart(self):
        canvas = self.chart; canvas.delete("all")
        width, height = max(canvas.winfo_width(), 280), max(canvas.winfo_height(), 180)
        data = self.current_chart[:8]
        if not data:
            canvas.create_text(width / 2, height / 2, text="暂无可视化数据", fill=COLORS["muted"], font=("Microsoft YaHei UI", 10)); return
        max_value = max((abs(value) for _, value in data), default=1) or 1
        left, right, top = 104, 47, 13
        row_height = max(min((height - top - 8) / len(data), 34), 21)
        for index, (label, value) in enumerate(data):
            y = top + index * row_height
            display_label = label if len(label) <= 8 else label[:8] + "…"
            center_y = y + row_height * 0.42
            canvas.create_text(left - 9, center_y, text=display_label, anchor="e", fill="#475569", font=("Microsoft YaHei UI", 8))
            canvas.create_rectangle(left, y + 5, width - right, y + row_height * 0.72, fill="#EFF6FF", outline="")
            bar_width = max((width - left - right) * abs(value) / max_value, 2)
            canvas.create_rectangle(left, y + 5, left + bar_width, y + row_height * 0.72, fill=COLORS["accent"], outline="")
            display_value = f"{value / 10000:.1f}万" if abs(value) >= 10000 else f"{value:,.0f}"
            canvas.create_text(width - 4, center_y, text=display_value, anchor="e", fill="#64748B", font=("Segoe UI", 8, "bold"))


def title(parent, heading: str, subtitle: str) -> None:
    header = ttk.Frame(parent, style="Page.TFrame"); header.pack(fill="x", padx=40, pady=(34, 16))
    ttk.Label(header, text=heading, style="Title.TLabel").pack(anchor="w")
    ttk.Label(header, text=subtitle, style="Subtitle.TLabel").pack(anchor="w", pady=(5, 0))


def log_widget(parent):
    widget = tk.Text(parent, height=16, bg="#1D1D1F", fg="#F5F5F7", insertbackground="white", relief="flat", font=("Consolas", 10), padx=16, pady=14, selectbackground="#515154")
    widget.pack(fill="both", expand=True, padx=36, pady=14); widget.configure(state="disabled")
    return widget


class DWCXApp(tk.Tk):
    PAGES = [
        ("home", "工作台", HomePage), ("analysis", "数据分析", DataAnalysisPage), ("ocr", "身份证 OCR", OCRPage), ("discount", "优惠计算", DiscountPage),
        ("daily", "日常总结", DailyPage), ("weekly", "周末总结", WeeklyPage), ("fee", "手续费结算", FeePage),
        ("history", "历史数据", HistoryPage),
    ]

    def __init__(self):
        super().__init__()
        self.title("DWCX 综合业务平台")
        self.geometry("1280x820"); self.minsize(1100, 720)
        self.configure(bg=COLORS["bg"])
        self.backend = BackendService(CONFIG)
        self._configure_styles()
        sidebar = tk.Frame(self, width=220, bg=COLORS["nav"]); sidebar.pack(side="left", fill="y"); sidebar.pack_propagate(False)
        tk.Label(sidebar, text="DWCX", bg=COLORS["nav"], fg="white", font=("Segoe UI", 24, "bold")).pack(anchor="w", padx=26, pady=(34, 0))
        tk.Label(sidebar, text="BUSINESS SUITE", bg=COLORS["nav"], fg="#8E8E93", font=("Segoe UI", 8, "bold")).pack(anchor="w", padx=27, pady=(2, 30))
        self.nav_buttons = {}
        for key, label, _ in self.PAGES:
            button = tk.Button(sidebar, text=label, anchor="w", bd=0, relief="flat", bg=COLORS["nav"], fg="#AEAEB2", activebackground=COLORS["nav_hover"], activeforeground="white", font=("Microsoft YaHei UI", 10), padx=18, pady=11, cursor="hand2", command=lambda k=key: self.show_page(k))
            button.pack(fill="x", padx=12, pady=3); self.nav_buttons[key] = button
        self.status = tk.Label(sidebar, text="●  就绪", bg=COLORS["nav"], fg="#A7F3B5", font=("Microsoft YaHei UI", 9), anchor="w")
        self.status.pack(side="bottom", fill="x", padx=26, pady=22)
        self.content = ttk.Frame(self, style="Page.TFrame"); self.content.pack(side="left", fill="both", expand=True)
        self.loading_overlay = LoadingOverlay(self.content)
        self.pages = {key: cls(self.content, self) for key, _, cls in self.PAGES}
        for page in self.pages.values(): page.place(relx=0, rely=0, relwidth=1, relheight=1)
        self.show_page("home")
        missing = self.backend.validate_layout()
        if missing:
            self.after(300, lambda: messagebox.showerror("模块缺失", "以下模块文件不存在：\n" + "\n".join(missing)))
        self.after_idle(self._center_window)

    def _configure_styles(self):
        style = ttk.Style(self); style.theme_use("clam")
        style.configure("Page.TFrame", background=COLORS["bg"])
        style.configure("Card.TFrame", background=COLORS["card"])
        style.configure("Title.TLabel", background=COLORS["bg"], foreground=COLORS["text"], font=("Microsoft YaHei UI", 25, "bold"))
        style.configure("Subtitle.TLabel", background=COLORS["bg"], foreground=COLORS["muted"], font=("Microsoft YaHei UI", 10))
        style.configure("TLabel", font=("Microsoft YaHei UI", 10))
        style.configure("TButton", background="#FFFFFF", foreground=COLORS["text"], bordercolor=COLORS["border"], lightcolor="#FFFFFF", darkcolor="#FFFFFF", font=("Microsoft YaHei UI", 10), padding=(14, 8), relief="flat")
        style.map("TButton", background=[("active", "#E8E8ED")], bordercolor=[("focus", "#8E8E93")])
        style.configure("Primary.TButton", background=COLORS["primary"], foreground="white", font=("Microsoft YaHei UI", 10, "bold"))
        style.map("Primary.TButton", background=[("active", "#3A3A3C")])
        style.configure("Analysis.TButton", background=COLORS["accent"], foreground="white", bordercolor=COLORS["accent"], lightcolor=COLORS["accent"], darkcolor=COLORS["accent"], font=("Microsoft YaHei UI", 10, "bold"), padding=(16, 8))
        style.map("Analysis.TButton", background=[("active", "#1D4ED8"), ("pressed", "#1E40AF")], bordercolor=[("active", "#1D4ED8")])
        style.configure("Link.TButton", background="#FFFFFF", foreground=COLORS["text"], borderwidth=0, font=("Microsoft YaHei UI", 9, "bold"), padding=(8, 5))
        style.map("Link.TButton", background=[("active", "#FFFFFF")], foreground=[("active", "#6E6E73")])
        style.configure("Card.TLabelframe", background=COLORS["card"], bordercolor=COLORS["border"], borderwidth=1, relief="solid")
        style.configure("Card.TLabelframe.Label", background=COLORS["card"], foreground=COLORS["text"], font=("Microsoft YaHei UI", 10, "bold"))
        style.configure("TEntry", fieldbackground=COLORS["field"], bordercolor=COLORS["border"], padding=8)
        style.configure("TCombobox", fieldbackground=COLORS["field"], background=COLORS["field"], bordercolor=COLORS["border"], padding=7)
        style.configure("Treeview", background="#FFFFFF", fieldbackground="#FFFFFF", foreground=COLORS["text"], rowheight=30, borderwidth=0, font=("Microsoft YaHei UI", 9))
        style.configure("Treeview.Heading", background="#F5F5F7", foreground=COLORS["text"], borderwidth=0, font=("Microsoft YaHei UI", 9, "bold"))
        style.configure("Analysis.Treeview", background="#FFFFFF", fieldbackground="#FFFFFF", foreground="#334155", rowheight=31, borderwidth=0, font=("Microsoft YaHei UI", 9))
        style.configure("Analysis.Treeview.Heading", background="#F1F5F9", foreground="#475569", borderwidth=0, relief="flat", font=("Microsoft YaHei UI", 9, "bold"), padding=(7, 7))
        style.map("Analysis.Treeview", background=[("selected", "#DBEAFE")], foreground=[("selected", "#1E3A8A")])

    def _center_window(self):
        self.update_idletasks()
        width, height = self.winfo_width(), self.winfo_height()
        x = max((self.winfo_screenwidth() - width) // 2, 0)
        y = max((self.winfo_screenheight() - height) // 2, 0)
        self.geometry(f"{width}x{height}+{x}+{y}")

    def set_status(self, text: str, color: str): self.status.configure(text="● " + text, fg=color)

    def show_loading(self, message="正在处理，请稍候…", hint="请勿关闭程序"):
        self.loading_overlay.show(message, hint)
        self.update_idletasks()

    def hide_loading(self):
        self.loading_overlay.hide()

    def show_page(self, key: str):
        self.pages[key].tkraise()
        for nav_key, button in self.nav_buttons.items():
            button.configure(bg=COLORS["nav_active"] if nav_key == key else COLORS["nav"], fg=COLORS["text"] if nav_key == key else "#AEAEB2", activeforeground=COLORS["text"] if nav_key == key else "white")


if __name__ == "__main__":
    DWCXApp().mainloop()

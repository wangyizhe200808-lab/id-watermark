"""Tk desktop application. The worker queue never touches Tk from a thread."""

import queue
import secrets
import threading
import tkinter as tk
from dataclasses import replace
from pathlib import Path
from tkinter import colorchooser, filedialog, messagebox, ttk

from PIL import Image, ImageTk

from . import HIDDEN_TEXT, VISIBLE_TEXT
from .core import create_watermarked, extract_watermark, load_image, load_receipt, save_export
from .visible import VisibleConfig, apply_visible, find_font

PROFILES = {"增强（默认）": "strong", "较轻": "balanced", "纸面试验（痕迹更明显）": "print"}
FILE_TYPES = [("图片", "*.png *.jpg *.jpeg *.bmp *.tif *.tiff *.webp"), ("所有文件", "*.*")]


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("证件双水印 · 本地版")
        self.geometry(
            f"{min(1260, self.winfo_screenwidth() - 50)}x{min(940, self.winfo_screenheight() - 60)}"
        )
        self.minsize(980, 700)
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TFrame", background="#f3f5f7")
        style.configure("TLabel", background="#f3f5f7", foreground="#213547", font=("Arial", 10))
        style.configure("Title.TLabel", font=("Arial", 21, "bold"), foreground="#0d675f")
        style.configure("Hint.TLabel", font=("Arial", 9), foreground="#657687")
        style.configure("TButton", padding=(10, 7))
        style.configure(
            "Accent.TButton", background="#087f75", foreground="white", padding=(15, 10)
        )
        self.configure(background="#f3f5f7")
        self.image = None
        self.source = ""
        self.scan = None
        self.corners = []
        self.events = queue.Queue()
        self.busy = False
        self.preview_job = None
        self.photo = self.scan_photo = None
        self.password = tk.StringVar(value=secrets.token_urlsafe(12))
        self.extract_password = tk.StringVar()
        self.input_path = tk.StringVar(value="请选择照片（支持 PNG、JPEG、TIFF）")
        self.scan_path = tk.StringVar()
        self.receipt_path = tk.StringVar()
        self.status = tk.StringVar(value="准备就绪。照片在本机处理，导出为新 PNG。")
        self.visible_on = tk.BooleanVar(value=True)
        self.hidden_on = tk.BooleanVar(value=True)
        self.visible_trace = tk.BooleanVar(value=False)
        self.visible_text = tk.StringVar(value=VISIBLE_TEXT)
        self.hidden_text = tk.StringVar(value=HIDDEN_TEXT)
        self.layout = tk.StringVar(value="平铺")
        self.font_path = tk.StringVar()
        self.color = tk.StringVar(value="#b02232")
        self.profile = tk.StringVar(value="增强（默认）")
        self.recipient = tk.StringVar()
        self.values = {}
        self.buttons = []
        self._build()
        self.after(100, self._poll)

    def _build(self):
        header = ttk.Frame(self, padding=(22, 15, 22, 12))
        header.pack(fill="x")
        ttk.Label(header, text="证件双水印", style="Title.TLabel").pack(anchor="w")
        ttk.Label(header, text="可见用途声明  +  可校验的频域副本标记", style="Hint.TLabel").pack(
            anchor="w", pady=(5, 0)
        )
        book = ttk.Notebook(self)
        book.pack(fill="both", expand=True, padx=16)
        export_tab, extract_tab = ttk.Frame(book), ttk.Frame(book)
        book.add(export_tab, text="  添加水印  ")
        book.add(extract_tab, text="  提取 / 扫描件校正  ")
        self._build_export(export_tab)
        self._build_extract(extract_tab)
        ttk.Label(self, textvariable=self.status, wraplength=1180, padding=(20, 12)).pack(fill="x")

    def _button(self, parent, text, command, accent=False):
        b = ttk.Button(
            parent, text=text, command=command, style="Accent.TButton" if accent else "TButton"
        )
        self.buttons.append(b)
        return b

    def _build_export(self, tab):
        toolbar = ttk.Frame(tab, padding=12)
        toolbar.pack(fill="x")
        self._button(toolbar, "选择照片", self.open_image).pack(side="left")
        ttk.Label(toolbar, textvariable=self.input_path, wraplength=900).pack(side="left", padx=12)
        body = ttk.Panedwindow(tab, orient="horizontal")
        body.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        left = ttk.Frame(body, width=360)
        right = ttk.Frame(body)
        body.add(left, weight=0)
        body.add(right, weight=1)
        scroll = tk.Canvas(left, width=355, highlightthickness=0, background="#f3f5f7")
        bar = ttk.Scrollbar(left, orient="vertical", command=scroll.yview)
        scroll.configure(yscrollcommand=bar.set)
        bar.pack(side="right", fill="y")
        scroll.pack(side="left", fill="both", expand=True)
        controls = ttk.Frame(scroll, padding=(0, 0, 10, 12))
        window = scroll.create_window((0, 0), window=controls, anchor="nw")
        controls.bind("<Configure>", lambda e: scroll.configure(scrollregion=scroll.bbox("all")))
        scroll.bind("<Configure>", lambda e: scroll.itemconfigure(window, width=e.width))

        ttk.Checkbutton(
            controls, text="启用可见水印", variable=self.visible_on, command=self.schedule_preview
        ).pack(anchor="w", pady=5)
        ttk.Entry(controls, textvariable=self.visible_text).pack(fill="x", pady=(0, 6))
        ttk.Checkbutton(
            controls,
            text="附加可见副本编号（便于纸面溯源）",
            variable=self.visible_trace,
            command=self.schedule_preview,
        ).pack(anchor="w", pady=(0, 6))
        combo = ttk.Combobox(
            controls, state="readonly", values=["平铺", "单处放置"], textvariable=self.layout
        )
        combo.pack(fill="x")
        combo.bind("<<ComboboxSelected>>", self.schedule_preview)
        self._scale(controls, "字号（原图像素）", "font_size", 12, 100, 32)
        self._scale(controls, "不透明度（%）", "opacity", 5, 80, 24)
        self._scale(controls, "旋转角度（°）", "angle", -80, 80, -25)
        self._scale(controls, "水平间距（越小越密）", "gap_x", 0, 400, 100)
        self._scale(controls, "垂直间距（越小越密）", "gap_y", 0, 300, 70)
        self._scale(controls, "水平位置 / 平铺偏移（%）", "x", 0, 100, 50)
        self._scale(controls, "垂直位置 / 平铺偏移（%）", "y", 0, 100, 50)
        row = ttk.Frame(controls)
        row.pack(fill="x", pady=6)
        self._button(row, "文字颜色", self.choose_color).pack(side="left")
        self._button(row, "中文字体…", self.choose_font).pack(side="left", padx=6)
        ttk.Label(controls, textvariable=self.font_path, style="Hint.TLabel", wraplength=310).pack(
            anchor="w"
        )
        ttk.Separator(controls).pack(fill="x", pady=12)
        ttk.Checkbutton(controls, text="启用频域水印", variable=self.hidden_on).pack(anchor="w")
        ttk.Entry(controls, textvariable=self.hidden_text).pack(fill="x", pady=6)
        ttk.Combobox(
            controls, textvariable=self.profile, values=list(PROFILES), state="readonly"
        ).pack(fill="x")
        ttk.Label(controls, text="提取密码（已随机生成，请自行保存）", style="Hint.TLabel").pack(
            anchor="w", pady=(8, 3)
        )
        self.pass_entry = ttk.Entry(controls, textvariable=self.password, show="•")
        self.pass_entry.pack(fill="x")
        row = ttk.Frame(controls)
        row.pack(fill="x", pady=5)
        show = tk.BooleanVar()
        ttk.Checkbutton(
            row,
            text="显示密码",
            variable=show,
            command=lambda: self.pass_entry.configure(show="" if show.get() else "•"),
        ).pack(side="left")
        self._button(row, "复制密码", self.copy_password).pack(side="right")
        ttk.Label(controls, text="接收方备注（仅保存在本地凭据）", style="Hint.TLabel").pack(
            anchor="w", pady=(6, 3)
        )
        ttk.Entry(controls, textvariable=self.recipient).pack(fill="x")

        ttk.Label(right, text="可见水印预览", font=("Arial", 12, "bold")).pack(
            anchor="w", padx=16, pady=(3, 6)
        )
        self.preview = tk.Label(right, text="选择一张照片开始", bg="#e5eaef", fg="#6c7e8e")
        self.preview.pack(fill="both", expand=True, padx=(16, 0))
        self.preview.bind("<Configure>", self.schedule_preview)
        ttk.Label(
            right,
            text="预览显示可见水印。频域水印在导出时写入，并完成提取校验。\n打印 / 复印后的恢复需实机测试，无法保证。",
            style="Hint.TLabel",
            wraplength=710,
        ).pack(anchor="w", padx=16, pady=10)
        self._button(right, "导出水印 PNG 与提取凭据", self.export, True).pack(
            fill="x", padx=(16, 0)
        )
        self.visible_text.trace_add("write", self.schedule_preview)

    def _scale(self, parent, label, key, low, high, value):
        self.values[key] = tk.DoubleVar(value=value)
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=(7, 0))
        ttk.Label(row, text=label).pack(side="left")
        number = ttk.Label(row, text=str(value))
        number.pack(side="right")

        def changed(v):
            number.configure(text=str(round(float(v))))
            self.schedule_preview()

        ttk.Scale(parent, from_=low, to=high, variable=self.values[key], command=changed).pack(
            fill="x"
        )

    def _config(self):
        return VisibleConfig(
            text=self.visible_text.get(),
            layout="tile" if self.layout.get() == "平铺" else "single",
            font_size=round(self.values["font_size"].get()),
            opacity=self.values["opacity"].get() / 100,
            angle=self.values["angle"].get(),
            gap_x=round(self.values["gap_x"].get()),
            gap_y=round(self.values["gap_y"].get()),
            x=self.values["x"].get() / 100,
            y=self.values["y"].get() / 100,
            color=self.color.get(),
            font_path=self.font_path.get(),
        )

    def open_image(self):
        path = filedialog.askopenfilename(filetypes=FILE_TYPES)
        if not path:
            return
        try:
            image = load_image(path)
        except (ValueError, OSError) as exc:
            messagebox.showerror("无法打开图片", str(exc))
            return
        self.source, self.image = path, image
        self.input_path.set(f"{Path(path).name}  ·  {image.width} × {image.height}")
        self.values["font_size"].set(max(16, min(80, round(image.width * 0.026))))
        self.schedule_preview()

    def choose_color(self):
        _, color = colorchooser.askcolor(self.color.get(), parent=self)
        if color:
            self.color.set(color)
            self.schedule_preview()

    def choose_font(self):
        path = filedialog.askopenfilename(filetypes=[("字体", "*.ttf *.ttc *.otf")])
        if path:
            self.font_path.set(path)
            self.schedule_preview()

    def copy_password(self):
        self.clipboard_clear()
        self.clipboard_append(self.password.get())
        self.status.set("密码已复制，请保存在安全位置；提取凭据不包含密码。")

    def schedule_preview(self, *_):
        if self.preview_job:
            self.after_cancel(self.preview_job)
        self.preview_job = self.after(180, self.render_preview)

    def render_preview(self):
        self.preview_job = None
        if self.image is None:
            return
        try:
            # Render at original coordinates to keep spacing/position exact in preview.
            cfg = self._config()
            if self.visible_trace.get():
                cfg = replace(cfg, text=f"{cfg.text}\n副本编号：导出时生成")
            out = apply_visible(self.image, cfg) if self.visible_on.get() else self.image.copy()
            out.thumbnail(
                (
                    max(200, self.preview.winfo_width() - 16),
                    max(150, self.preview.winfo_height() - 16),
                )
            )
            self.photo = ImageTk.PhotoImage(out)
            self.preview.configure(image=self.photo, text="")
        except (ValueError, OSError) as exc:
            self.status.set(str(exc))

    def _run_worker(self, task, done):
        if self.busy:
            return
        self.busy = True
        for b in self.buttons:
            b.configure(state="disabled")
        self.status.set("正在处理，请稍候… 大图频域处理可能需要数秒至数十秒。")

        def worker():
            try:
                self.events.put((done, task(), None))
            except Exception as exc:  # noqa: BLE001 -- report worker failures on the UI thread
                self.events.put((done, None, exc))

        threading.Thread(target=worker, daemon=True).start()

    def _poll(self):
        try:
            done, result, error = self.events.get_nowait()
            self.busy = False
            for b in self.buttons:
                b.configure(state="normal")
            if error:
                self.status.set(f"处理失败：{error}")
                messagebox.showerror("处理失败", str(error))
            else:
                done(result)
        except queue.Empty:
            pass
        self.after(100, self._poll)

    def export(self):
        if self.image is None:
            messagebox.showinfo("请选择照片", "先选择需要添加水印的照片。")
            return
        try:
            cfg = self._config() if self.visible_on.get() else None
            if cfg:
                find_font(cfg.font_path)
            if cfg is None and not self.hidden_on.get():
                raise ValueError("请至少启用一种水印。")
            if self.hidden_on.get() and len(self.password.get()) < 8:
                raise ValueError("频域水印密码至少 8 位。")
        except ValueError as exc:
            messagebox.showerror("参数错误", str(exc))
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".png",
            filetypes=[("PNG", "*.png")],
            initialfile=Path(self.source).stem + "_watermarked.png",
        )
        if not path:
            return
        image, source = self.image.copy(), self.source
        hidden, text, password = self.hidden_on.get(), self.hidden_text.get(), self.password.get()
        profile, recipient = PROFILES[self.profile.get()], self.recipient.get()
        visible_trace = self.visible_trace.get()

        def task():
            out, receipt = create_watermarked(
                image, cfg, hidden, text, password, profile, recipient, visible_trace
            )
            paths = save_export(out, receipt, path, source=source, overwrite=True)
            return paths, receipt

        def done(result):
            (out, receipt_path), receipt = result
            self.status.set(f"已导出：{out.name}")
            msg = f"图片：{out}\n\n本地凭据：{receipt_path}"
            if receipt["frequency"]:
                self.extract_password.set(password)
                self.receipt_path.set(str(receipt_path))
                msg += (
                    f"\n\n副本编号：{receipt['frequency']['trace_id']}\n导出前提取校验通过。"
                    "\n\n仅将 PNG 发给对方；请自行保留密码和提取凭据。"
                )
            messagebox.showinfo("导出完成", msg)

        self._run_worker(task, done)

    def _build_extract(self, tab):
        controls = ttk.Frame(tab, padding=12)
        controls.pack(fill="x")
        for label, var, cmd in [
            ("选择待提取图片", self.scan_path, self.open_scan),
            ("选择提取凭据", self.receipt_path, self.open_receipt),
        ]:
            row = ttk.Frame(controls)
            row.pack(fill="x", pady=4)
            self._button(row, label, cmd).pack(side="left")
            ttk.Entry(row, textvariable=var).pack(fill="x", side="left", expand=True, padx=10)
        row = ttk.Frame(controls)
        row.pack(fill="x", pady=6)
        ttk.Label(row, text="提取密码").pack(side="left")
        ttk.Entry(row, textvariable=self.extract_password, show="•", width=30).pack(
            side="left", padx=10
        )
        self._button(row, "清除角点 / 使用整幅图", self.reset_corners).pack(side="left")
        self._button(row, "提取并校验", self.extract, True).pack(side="right")
        ttk.Label(
            controls,
            text="扫描件：依次点击整张外发图像的左上 → 右上 → 右下 → 左下角。"
            "原始 PNG 无需选点。若图像有背景，四角需包含原来的背景。",
            style="Hint.TLabel",
            wraplength=1120,
        ).pack(anchor="w", pady=6)
        self.corner_label = ttk.Label(controls, text="未选角点：按整幅图恢复到导出尺寸。")
        self.corner_label.pack(anchor="w")
        self.scan_canvas = tk.Canvas(tab, background="#e5eaef", highlightthickness=0)
        self.scan_canvas.pack(fill="both", expand=True, padx=12)
        self.scan_canvas.bind("<Button-1>", self.add_corner)
        self.scan_canvas.bind("<Configure>", lambda e: self.render_scan())
        self.result_text = tk.Text(
            tab, height=7, wrap="word", background="white", font=("Arial", 11)
        )
        self.result_text.pack(fill="x", padx=12, pady=12)

    def open_scan(self):
        path = filedialog.askopenfilename(filetypes=FILE_TYPES)
        if not path:
            return
        try:
            self.scan = load_image(path)
            self.scan_path.set(path)
            sidecar = Path(path + ".receipt.json")
            if sidecar.is_file():
                self.receipt_path.set(str(sidecar))
            self.reset_corners()
        except (ValueError, OSError) as exc:
            messagebox.showerror("无法打开图片", str(exc))

    def open_receipt(self):
        path = filedialog.askopenfilename(filetypes=[("提取凭据", "*.receipt.json *.json")])
        if path:
            self.receipt_path.set(path)

    def reset_corners(self):
        self.corners.clear()
        self.corner_label.configure(text="未选角点：按整幅图恢复到导出尺寸。")
        self.render_scan()

    def render_scan(self):
        if self.scan is None:
            return
        cw, ch = self.scan_canvas.winfo_width(), self.scan_canvas.winfo_height()
        if cw < 10 or ch < 10:
            return
        image = self.scan.copy()
        image.thumbnail((cw - 12, ch - 12), Image.Resampling.LANCZOS)
        self.scan_scale = (image.width / self.scan.width, image.height / self.scan.height)
        self.scan_offset = ((cw - image.width) // 2, (ch - image.height) // 2)
        self.scan_photo = ImageTk.PhotoImage(image)
        self.scan_canvas.delete("all")
        self.scan_canvas.create_image(*self.scan_offset, image=self.scan_photo, anchor="nw")
        projected = []
        for i, (x, y) in enumerate(self.corners):
            px = x * self.scan_scale[0] + self.scan_offset[0]
            py = y * self.scan_scale[1] + self.scan_offset[1]
            projected.extend([px, py])
            self.scan_canvas.create_oval(
                px - 5, py - 5, px + 5, py + 5, fill="#e34e40", outline="white"
            )
            self.scan_canvas.create_text(
                px + 12, py + 12, text=str(i + 1), fill="#e34e40", font=("Arial", 13, "bold")
            )
        if len(projected) >= 4:
            if len(self.corners) == 4:
                projected += projected[:2]
            self.scan_canvas.create_line(*projected, fill="#e34e40", width=2)

    def add_corner(self, event):
        if self.scan is None or len(self.corners) == 4:
            return
        x = (event.x - self.scan_offset[0]) / self.scan_scale[0]
        y = (event.y - self.scan_offset[1]) / self.scan_scale[1]
        if 0 <= x < self.scan.width and 0 <= y < self.scan.height:
            self.corners.append((min(x, self.scan.width - 1), min(y, self.scan.height - 1)))
            self.corner_label.configure(text=f"已选 {len(self.corners)} / 4 个角点。")
            self.render_scan()

    def extract(self):
        self.result_text.delete("1.0", "end")
        if len(self.corners) not in (0, 4):
            messagebox.showinfo("角点未选全", "请选满四个角点，或清除角点后使用整幅图。")
            return
        try:
            image = load_image(self.scan_path.get())
            receipt = load_receipt(self.receipt_path.get())
        except (ValueError, OSError) as exc:
            messagebox.showerror("提取参数错误", str(exc))
            return
        password = self.extract_password.get()
        corners = list(self.corners) or None

        def done(result):
            text = (
                f"提取成功，完整性校验通过\n水印：{result['text']}\n副本编号：{result['trace_id']}"
                f"\n接收方备注（来自本地凭据）：{result['recipient_note_from_receipt']}"
                f"\n纠正错误字节数：{result['corrected_bytes']}\n{result['notice']}"
            )
            self.result_text.insert("1.0", text)
            self.status.set("频域水印提取及完整性校验通过。")

        self._run_worker(lambda: extract_watermark(image, receipt, password, corners), done)


def main():
    App().mainloop()


if __name__ == "__main__":
    main()

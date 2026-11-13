"""
YT Downloader Pro — Modernized with customtkinter
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Install dependencies:
    pip install customtkinter yt-dlp pillow

Build EXE (run once first to generate icon.ico, then):
    python -m PyInstaller --onefile --noconsole --icon=icon.ico yt_downloader_pro.py
"""

import customtkinter as ctk
from tkinter import filedialog, messagebox
import yt_dlp
import threading
import os
import subprocess
import sys
import json
import time
import re
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageTk
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False


# ══════════════════════════════════════════════════════════════════════════════
#  UTILITIES
# ══════════════════════════════════════════════════════════════════════════════

def resource_path(relative: str) -> str:
    """Resolve path for both dev environment and PyInstaller bundle."""
    try:
        base = sys._MEIPASS          # type: ignore[attr-defined]
    except AttributeError:
        base = os.path.abspath(".")
    return os.path.join(base, relative)


SETTINGS_FILE = os.path.join(str(Path.home()), ".yt_dlp_pro_settings.json")

def load_settings() -> dict:
    try:
        with open(SETTINGS_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return {}

def save_settings(data: dict) -> None:
    try:
        with open(SETTINGS_FILE, "w") as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass

def fmt_duration(seconds) -> str:
    if not seconds:
        return ""
    s = int(seconds)
    h, rem = divmod(s, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"

def fmt_speed(bps) -> str:
    if not bps:
        return ""
    if bps >= 1_048_576:
        return f"{bps/1_048_576:.1f} MB/s"
    if bps >= 1024:
        return f"{bps/1024:.0f} KB/s"
    return f"{bps:.0f} B/s"

def fmt_eta(eta) -> str:
    if not eta:
        return ""
    eta = int(eta)
    if eta >= 3600:
        return f"{eta//3600}h {(eta%3600)//60}m"
    if eta >= 60:
        return f"{eta//60}m {eta%60}s"
    return f"{eta}s"

def fmt_size(total_bytes) -> str:
    if not total_bytes:
        return ""
    if total_bytes >= 1_073_741_824:
        return f"{total_bytes/1_073_741_824:.2f} GB"
    if total_bytes >= 1_048_576:
        return f"{total_bytes/1_048_576:.1f} MB"
    return f"{total_bytes/1024:.0f} KB"

def clean_filename(title: str) -> str:
    return re.sub(r'[\\/*?:"<>|]', "", title)


# ══════════════════════════════════════════════════════════════════════════════
#  ICON GENERATOR  (creates icon.ico once; used by PyInstaller & window title)
# ══════════════════════════════════════════════════════════════════════════════

def generate_icon(out_path: str = "icon.ico") -> str | None:
    if not PIL_AVAILABLE:
        return None
    if os.path.exists(out_path):
        return out_path
    try:
        sizes = [256, 128, 64, 48, 32, 16]
        frames = []
        for sz in sizes:
            img = Image.new("RGBA", (sz, sz), (0, 0, 0, 0))
            d   = ImageDraw.Draw(img)
            pad = sz // 10

            # ── Background rounded square ──────────────────────────────────
            d.rounded_rectangle([pad, pad, sz-pad, sz-pad],
                                 radius=sz//5, fill=(18, 18, 32, 255))

            cx = sz // 2
            # ── Stem ──────────────────────────────────────────────────────
            sw = max(2, sz//10)
            st, sb = sz//5, int(sz*0.55)
            d.rectangle([cx-sw//2, st, cx+sw//2, sb], fill=(80, 160, 255, 255))

            # ── Arrow head ────────────────────────────────────────────────
            aw = sz // 3
            ah = sz // 6
            arrow_top = sb
            pts = [(cx, arrow_top + ah), (cx-aw//2, arrow_top), (cx+aw//2, arrow_top)]
            d.polygon(pts, fill=(80, 160, 255, 255))

            # ── Base line ─────────────────────────────────────────────────
            bh = max(2, sz//16)
            by = sz - sz//5
            d.rectangle([pad+sz//8, by, sz-pad-sz//8, by+bh], fill=(80, 160, 255, 255))

            frames.append(img)

        frames[0].save(out_path, format="ICO",
                       sizes=[(s, s) for s in sizes],
                       append_images=frames[1:])
        return out_path
    except Exception as e:
        print(f"[icon] {e}")
        return None


# ══════════════════════════════════════════════════════════════════════════════
#  DOWNLOADER WORKER
# ══════════════════════════════════════════════════════════════════════════════

class VideoDownloader:
    def __init__(self, video_info: dict, download_path: str, quality: str,
                 fmt_type: str, progress_cb, status_cb, complete_cb,
                 use_numbering: bool = False):
        self.video_info   = video_info
        self.download_path = download_path
        self.quality       = quality
        self.fmt_type      = fmt_type      # "Video" | "Audio"
        self.progress_cb   = progress_cb
        self.status_cb     = status_cb
        self.complete_cb   = complete_cb
        self.use_numbering = use_numbering
        self.cancelled     = False
        self.retry_count   = 0
        self.max_retries   = 5

    # ── public ────────────────────────────────────────────────────────────────
    def start(self):
        self.cancelled = False
        t = threading.Thread(target=self._run, daemon=True)
        t.start()

    def cancel(self):
        self.cancelled = True

    # ── private ───────────────────────────────────────────────────────────────
    def _build_opts(self) -> dict:
        if self.fmt_type == "Audio":
            fmt = "bestaudio/best"
            post = [{"key": "FFmpegExtractAudio",
                     "preferredcodec": "mp3",
                     "preferredquality": "192"},
                    {"key": "FFmpegMetadata", "add_metadata": True}]
        else:
            q_map = {
                "Best":  "best[ext=mp4]/best",
                "1080p": "best[height<=1080][ext=mp4]/best[height<=1080]",
                "720p":  "best[height<=720][ext=mp4]/best[height<=720]",
                "480p":  "best[height<=480][ext=mp4]/best[height<=480]",
                "360p":  "best[height<=360][ext=mp4]/best[height<=360]",
            }
            fmt  = q_map.get(self.quality, q_map["720p"])
            post = [{"key": "FFmpegMetadata", "add_metadata": True}]

        if self.use_numbering and "index" in self.video_info:
            tmpl = os.path.join(self.download_path,
                                f"{self.video_info['index']:02d}. %(title)s.%(ext)s")
        else:
            tmpl = os.path.join(self.download_path, "%(title)s.%(ext)s")

        return {
            "format":                   fmt,
            "outtmpl":                  tmpl,
            "noplaylist":               True,
            "quiet":                    True,
            "no_warnings":              True,
            "socket_timeout":           30,
            "retries":                  10,
            "fragment_retries":         10,
            "skip_unavailable_fragments": True,
            "progress_hooks":           [self._hook],
            "postprocessors":           post,
        }

    def _run(self):
        opts = self._build_opts()
        while self.retry_count < self.max_retries and not self.cancelled:
            try:
                self.status_cb("Downloading", None, None, None)
                with yt_dlp.YoutubeDL(opts) as ydl:
                    ydl.download([self.video_info["url"]])
                self.progress_cb(100)
                self.status_cb("Completed", None, None, None)
                self.complete_cb(True)
                return
            except Exception as e:
                self.retry_count += 1
                if self.cancelled:
                    self.status_cb("Cancelled", None, None, None)
                    self.complete_cb(False)
                    return
                if self.retry_count < self.max_retries:
                    self.status_cb(f"Retry {self.retry_count}/{self.max_retries}",
                                   None, None, None)
                    time.sleep(2)
                else:
                    self.status_cb("Failed", None, None, None)
                    self.complete_cb(False)

    def _hook(self, d: dict):
        if self.cancelled:
            raise Exception("Cancelled by user")
        if d["status"] == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate", 0)
            downloaded = d.get("downloaded_bytes", 0)
            pct = (downloaded / total * 100) if total else 0
            self.progress_cb(pct)
            self.status_cb(
                "Downloading",
                fmt_speed(d.get("speed")),
                fmt_eta(d.get("eta")),
                fmt_size(total),
            )
        elif d["status"] == "finished":
            self.progress_cb(99)
            self.status_cb("Processing…", None, None, None)


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN APPLICATION
# ══════════════════════════════════════════════════════════════════════════════

# ─── Colour palette ───────────────────────────────────────────────────────────
C = {
    "bg":       "#0e0e18",
    "surface":  "#16162a",
    "card":     "#1c1c32",
    "card2":    "#20203a",
    "border":   "#2a2a4a",
    "accent":   "#4f8ef7",
    "accent2":  "#6fa8ff",
    "green":    "#3dba6a",
    "red":      "#e05252",
    "orange":   "#e09032",
    "text":     "#e8e8f0",
    "sub":      "#8888aa",
    "dim":      "#555570",
}

class App(ctk.CTk):
    def __init__(self):
        super().__init__()

        # ── Appearance ────────────────────────────────────────────────────────
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")
        self.configure(fg_color=C["bg"])

        self.title("YT Downloader Pro")
        self.geometry("960x650")
        self.minsize(820, 640)
        self.resizable(False, False)

        # ── Window icon ───────────────────────────────────────────────────────
        icon = generate_icon()
        if icon and os.path.exists(icon):
            try:
                self.after(100, lambda: self.iconbitmap(icon))
            except Exception:
                pass

        # ── State ─────────────────────────────────────────────────────────────
        self.videos:      list[dict]               = []
        self.downloaders: dict[str, VideoDownloader] = {}
        self.widgets:     dict[str, dict]          = {}   # vid_id → {pb, status, info}
        self.done_count   = 0

        # ── Settings ──────────────────────────────────────────────────────────
        cfg = load_settings()
        default_dl = str(Path.home() / "Downloads" / "YouTube")
        self.dl_path    = cfg.get("dl_path", default_dl)
        self.quality_v  = ctk.StringVar(value=cfg.get("quality",  "720p"))
        self.fmt_v      = ctk.StringVar(value=cfg.get("format",   "Video"))
        self.number_v   = ctk.BooleanVar(value=cfg.get("numbering", False))

        self._build()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ══════════════════════════════════════════════════════════════════════════
    #  UI BUILDER
    # ══════════════════════════════════════════════════════════════════════════

    def _build(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self._build_header()
        self._build_panel()
        self._build_list()

    # ── Header ────────────────────────────────────────────────────────────────
    def _build_header(self):
        hdr = ctk.CTkFrame(self, fg_color=C["surface"], corner_radius=0, height=64)
        hdr.grid(row=0, column=0, sticky="ew")
        hdr.grid_propagate(False)
        hdr.grid_columnconfigure(0, weight=1)

        inner = ctk.CTkFrame(hdr, fg_color="transparent")
        inner.place(relx=0.5, rely=0.5, anchor="center")

        ctk.CTkLabel(inner, text="▼",
                     font=ctk.CTkFont(family="Segoe UI", size=26, weight="bold"),
                     text_color=C["accent"]).pack(side="left", padx=(0, 10))
        ctk.CTkLabel(inner, text="YT Downloader",
                     font=ctk.CTkFont(family="Segoe UI", size=20, weight="bold"),
                     text_color=C["text"]).pack(side="left")
        ctk.CTkLabel(inner, text="  Pro",
                     font=ctk.CTkFont(family="Segoe UI", size=20, weight="bold"),
                     text_color=C["accent"]).pack(side="left")
        ctk.CTkLabel(inner, text="  v2.0",
                     font=ctk.CTkFont(family="Segoe UI", size=11),
                     text_color=C["dim"]).pack(side="left", pady=(6, 0))

    # ── Control panel ─────────────────────────────────────────────────────────
    def _build_panel(self):
        panel = ctk.CTkFrame(self, fg_color=C["surface"],
                             corner_radius=14,
                             border_width=1, border_color=C["border"])
        panel.grid(row=0, column=0, sticky="ew", padx=14, pady=(78, 0))
        panel.grid_columnconfigure(1, weight=1)

        # Row helper
        def row_label(text, r):
            ctk.CTkLabel(panel, text=text,
                         font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
                         text_color=C["sub"], width=64, anchor="e"
                         ).grid(row=r, column=0, padx=(16, 8), pady=6, sticky="e")

        # ── URL ───────────────────────────────────────────────────────────────
        row_label("URL", 0)
        url_f = ctk.CTkFrame(panel, fg_color="transparent")
        url_f.grid(row=0, column=1, columnspan=2, sticky="ew", padx=(0, 14), pady=6)
        url_f.grid_columnconfigure(0, weight=1)

        self.url_entry = ctk.CTkEntry(
            url_f,
            placeholder_text="Paste a YouTube video or playlist link…",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            fg_color=C["card"], border_color=C["border"],
            text_color=C["text"], height=38,
        )
        self.url_entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.url_entry.bind("<Return>", lambda _: self._load())

        ctk.CTkButton(url_f, text="Paste", width=72, height=38,
                      fg_color=C["card2"], hover_color=C["border"],
                      text_color=C["text"],
                      font=ctk.CTkFont(size=12),
                      command=self._paste).grid(row=0, column=1)

        # ── Save path ─────────────────────────────────────────────────────────
        row_label("Save to", 1)
        path_f = ctk.CTkFrame(panel, fg_color="transparent")
        path_f.grid(row=1, column=1, columnspan=2, sticky="ew", padx=(0, 14), pady=6)
        path_f.grid_columnconfigure(0, weight=1)

        self.path_entry = ctk.CTkEntry(
            path_f,
            font=ctk.CTkFont(family="Segoe UI", size=12),
            fg_color=C["card"], border_color=C["border"],
            text_color=C["text"], height=38,
        )
        self.path_entry.insert(0, self.dl_path)
        self.path_entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))

        ctk.CTkButton(path_f, text="Browse", width=78, height=38,
                      fg_color=C["card2"], hover_color=C["border"],
                      text_color=C["text"], font=ctk.CTkFont(size=12),
                      command=self._browse).grid(row=0, column=1, padx=(0, 6))

        ctk.CTkButton(path_f, text="📂 Open", width=82, height=38,
                      fg_color=C["card2"], hover_color=C["border"],
                      text_color=C["text"], font=ctk.CTkFont(size=12),
                      command=self._open_folder).grid(row=0, column=2)

        # ── Options ───────────────────────────────────────────────────────────
        row_label("Options", 2)
        opt_f = ctk.CTkFrame(panel, fg_color="transparent")
        opt_f.grid(row=2, column=1, columnspan=2, sticky="ew", padx=(0, 14), pady=6)

        ctk.CTkLabel(opt_f, text="Quality",
                     font=ctk.CTkFont(size=11), text_color=C["sub"]).pack(side="left")
        ctk.CTkOptionMenu(opt_f, variable=self.quality_v,
                          values=["Best", "1080p", "720p", "480p", "360p"],
                          width=110, height=34,
                          fg_color=C["card"], button_color=C["accent"],
                          font=ctk.CTkFont(size=12),
                          command=lambda _: self._save()
                          ).pack(side="left", padx=(6, 24))

        ctk.CTkLabel(opt_f, text="Format",
                     font=ctk.CTkFont(size=11), text_color=C["sub"]).pack(side="left")
        ctk.CTkSegmentedButton(opt_f, variable=self.fmt_v,
                               values=["Video", "Audio (MP3)"],
                               height=34, width=200,
                               font=ctk.CTkFont(size=12),
                               command=lambda _: self._save()
                               ).pack(side="left", padx=(6, 24))

        ctk.CTkCheckBox(opt_f, text="Number playlist files",
                        variable=self.number_v,
                        font=ctk.CTkFont(size=12),
                        text_color=C["text"],
                        command=self._save
                        ).pack(side="left")

        # ── Action row ────────────────────────────────────────────────────────
        row_label("", 3)
        act_f = ctk.CTkFrame(panel, fg_color="transparent")
        act_f.grid(row=3, column=1, columnspan=2, sticky="ew", padx=(0, 14), pady=(6, 14))

        self.load_btn = ctk.CTkButton(
            act_f, text="🔍  Load", width=130, height=42,
            fg_color=C["accent"], hover_color=C["accent2"],
            text_color="#ffffff",
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self._load,
        )
        self.load_btn.pack(side="left", padx=(0, 10))

        self.dl_all_btn = ctk.CTkButton(
            act_f, text="⬇  Download All", width=160, height=42,
            fg_color=(C["green"], "#0a3920"), hover_color="#4dce7a",
            text_color=("#ffffff"),
            font=ctk.CTkFont(size=13, weight="bold"),
            state="disabled",
            command=self._download_all,
        )
        self.dl_all_btn.pack(side="left", padx=(0, 10))

        self.cancel_all_btn = ctk.CTkButton(
            act_f, text="✖  Cancel All", width=140, height=42,
            fg_color="#4a1a1a", hover_color=C["red"],
            text_color="#ffffff",
            font=ctk.CTkFont(size=13, weight="bold"),
            state="disabled",
            command=self._cancel_all,
        )
        self.cancel_all_btn.pack(side="left", padx=(0, 20))

        # Overall progress
        overall_f = ctk.CTkFrame(act_f, fg_color="transparent")
        overall_f.pack(side="right")

        self.overall_lbl = ctk.CTkLabel(overall_f, text="",
                                         font=ctk.CTkFont(size=11),
                                         text_color=C["sub"])
        self.overall_lbl.pack()
        self.overall_bar = ctk.CTkProgressBar(overall_f, width=200, height=6,
                                               progress_color=C["accent"])
        self.overall_bar.set(0)

    # ── Video list ────────────────────────────────────────────────────────────
    def _build_list(self):
        outer = ctk.CTkFrame(self, fg_color=C["surface"],
                             corner_radius=14,
                             border_width=1, border_color=C["border"])
        outer.grid(row=1, column=0, sticky="nsew", padx=14, pady=14)
        outer.grid_columnconfigure(0, weight=1)
        outer.grid_rowconfigure(1, weight=1)

        # list header
        lhdr = ctk.CTkFrame(outer, fg_color="transparent")
        lhdr.grid(row=0, column=0, sticky="ew", padx=14, pady=(12, 4))

        self.count_lbl = ctk.CTkLabel(lhdr, text="No videos loaded",
                                       font=ctk.CTkFont(size=13, weight="bold"),
                                       text_color=C["text"])
        self.count_lbl.pack(side="left")

        # retry failed button (hidden until needed)
        self.retry_btn = ctk.CTkButton(lhdr, text="↻ Retry Failed",
                                        width=130, height=30,
                                        fg_color=C["orange"], hover_color="#e8a040",
                                        text_color="#fff",
                                        font=ctk.CTkFont(size=11),
                                        command=self._retry_failed)
        # not packed until failures exist

        self.scroll = ctk.CTkScrollableFrame(outer, fg_color="transparent",
                                              corner_radius=0,
                                              scrollbar_button_color=C["border"],
                                              scrollbar_button_hover_color=C["accent"])
        self.scroll.grid(row=1, column=0, sticky="nsew", padx=6, pady=(0, 6))
        self.scroll.grid_columnconfigure(0, weight=1)

        self._show_empty("Enter a YouTube URL above and click  🔍 Load")

    # ══════════════════════════════════════════════════════════════════════════
    #  ACTIONS
    # ══════════════════════════════════════════════════════════════════════════

    def _paste(self):
        try:
            txt = self.clipboard_get()
            self.url_entry.delete(0, "end")
            self.url_entry.insert(0, txt)
        except Exception:
            pass

    def _browse(self):
        folder = filedialog.askdirectory()
        if folder:
            self.path_entry.delete(0, "end")
            self.path_entry.insert(0, folder)
            self.dl_path = folder
            self._save()

    def _open_folder(self):
        p = self.path_entry.get().strip()
        if not os.path.exists(p):
            os.makedirs(p, exist_ok=True)
        if sys.platform == "win32":
            os.startfile(p)
        elif sys.platform == "darwin":
            subprocess.run(["open", p])
        else:
            subprocess.run(["xdg-open", p])

    def _save(self, *_):
        save_settings({
            "dl_path":  self.path_entry.get().strip(),
            "quality":  self.quality_v.get(),
            "format":   self.fmt_v.get(),
            "numbering": self.number_v.get(),
        })

    # ── Load ──────────────────────────────────────────────────────────────────
    def _load(self):
        url = self.url_entry.get().strip()
        if not url:
            messagebox.showwarning("YT Downloader Pro", "Please enter a URL first.")
            return

        self._clear_list()
        self.videos.clear()
        self.downloaders.clear()
        self.widgets.clear()
        self.done_count = 0
        self.overall_bar.set(0)
        self.overall_lbl.configure(text="")
        self.overall_bar.pack_forget()
        self.dl_all_btn.configure(state="disabled")
        self.cancel_all_btn.configure(state="disabled")
        self.retry_btn.pack_forget()

        self.load_btn.configure(state="disabled", text="Loading…")
        self.count_lbl.configure(text="Fetching info…", text_color=C["sub"])
        self._show_empty("⟳  Fetching playlist info…")

        threading.Thread(target=self._fetch, args=(url,), daemon=True).start()

    def _fetch(self, url: str):
        try:
            opts = {"quiet": True, "no_warnings": True, "extract_flat": "in_playlist"}
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)

            if "entries" in info:
                for i, e in enumerate(info["entries"], 1):
                    if e:
                        self.videos.append({
                            "title":    e.get("title", "Unknown"),
                            "url":      f"https://www.youtube.com/watch?v={e.get('id','')}",
                            "id":       e.get("id", f"_{i}"),
                            "index":    i,
                            "duration": e.get("duration", 0),
                        })
            else:
                self.videos.append({
                    "title":    info.get("title", "Unknown"),
                    "url":      url,
                    "id":       info.get("id", "_1"),
                    "index":    1,
                    "duration": info.get("duration", 0),
                })

            self.after(0, self._display)
        except Exception as exc:
            self.after(0, lambda: messagebox.showerror("Load Error", str(exc)))
            self.after(0, self._reset_load)

    def _reset_load(self):
        self.load_btn.configure(state="normal", text="🔍  Load")
        self.count_lbl.configure(text="No videos loaded", text_color=C["text"])
        self._clear_list()
        self._show_empty("Enter a YouTube URL above and click  🔍 Load")

    def _display(self):
        self._clear_list()
        n = len(self.videos)
        self.load_btn.configure(state="normal", text="🔍  Load")
        self.count_lbl.configure(
            text=f"{n} video{'s' if n != 1 else ''} found",
            text_color=C["green"],
        )

        if not self.videos:
            self._show_empty("No videos found in the provided URL.")
            return

        self.dl_all_btn.configure(state="normal")
        self.cancel_all_btn.configure(state="normal")

        if n > 1:
            self.overall_lbl.configure(text=f"0 / {n} completed")
            self.overall_bar.pack(pady=(2, 0))

        for idx, vid in enumerate(self.videos):
            self._make_card(idx, vid)

    # ── Card builder ──────────────────────────────────────────────────────────
    def _make_card(self, idx: int, vid: dict):
        card = ctk.CTkFrame(self.scroll, fg_color=C["card"],
                             corner_radius=10,
                             border_width=1, border_color=C["border"])
        card.grid(row=idx, column=0, sticky="ew", padx=4, pady=5)
        card.grid_columnconfigure(1, weight=1)

        # ── Badge ─────────────────────────────────────────────────────────────
        badge_f = ctk.CTkFrame(card, fg_color=C["card2"],
                               corner_radius=8, width=44, height=44)
        badge_f.grid(row=0, column=0, rowspan=3, padx=(10, 8), pady=10, sticky="n")
        badge_f.grid_propagate(False)
        ctk.CTkLabel(badge_f, text=f"{idx+1:02d}",
                     font=ctk.CTkFont(size=13, weight="bold"),
                     text_color=C["accent"]).place(relx=0.5, rely=0.5, anchor="center")

        # ── Title row ─────────────────────────────────────────────────────────
        title_f = ctk.CTkFrame(card, fg_color="transparent")
        title_f.grid(row=0, column=1, sticky="ew", padx=(0, 6), pady=(10, 2))
        title_f.grid_columnconfigure(0, weight=1)

        title = vid["title"]
        if len(title) > 95:
            title = title[:92] + "…"
        ctk.CTkLabel(title_f, text=title,
                     font=ctk.CTkFont(size=12, weight="bold"),
                     text_color=C["text"], anchor="w"
                     ).grid(row=0, column=0, sticky="w")

        dur = fmt_duration(vid.get("duration", 0))
        if dur:
            ctk.CTkLabel(title_f, text=dur,
                         font=ctk.CTkFont(size=11),
                         text_color=C["dim"]).grid(row=0, column=1, padx=(8, 0))

        # ── Progress row ──────────────────────────────────────────────────────
        prog_f = ctk.CTkFrame(card, fg_color="transparent")
        prog_f.grid(row=1, column=1, sticky="ew", padx=(0, 6), pady=2)
        prog_f.grid_columnconfigure(0, weight=1)

        pb = ctk.CTkProgressBar(prog_f, height=7, corner_radius=4,
                                  progress_color=C["accent"])
        pb.set(0)
        pb.grid(row=0, column=0, sticky="ew", padx=(0, 10))

        status_lbl = ctk.CTkLabel(prog_f, text="Ready",
                                   font=ctk.CTkFont(size=10),
                                   text_color=C["dim"], width=110, anchor="w")
        status_lbl.grid(row=0, column=1)

        # ── Info row (speed / ETA / size) ─────────────────────────────────────
        info_lbl = ctk.CTkLabel(card, text="",
                                 font=ctk.CTkFont(size=10),
                                 text_color=C["dim"], anchor="w")
        info_lbl.grid(row=2, column=1, sticky="w", padx=(0, 6), pady=(2, 8))

        # ── Buttons ───────────────────────────────────────────────────────────
        btn_f = ctk.CTkFrame(card, fg_color="transparent")
        btn_f.grid(row=0, column=2, rowspan=3, padx=10, pady=8, sticky="ns")

        def _dl(v=vid, p=pb, s=status_lbl, i=info_lbl):
            self._start_download(v, p, s, i)

        ctk.CTkButton(btn_f, text="⬇", width=38, height=30,
                      fg_color="#1a3a6a", hover_color=C["accent"],
                      text_color="#fff", font=ctk.CTkFont(size=15),
                      command=_dl).pack(pady=(0, 4))

        ctk.CTkButton(btn_f, text="✖", width=38, height=30,
                      fg_color="#3a1515", hover_color=C["red"],
                      text_color="#fff", font=ctk.CTkFont(size=12),
                      command=lambda v=vid: self._cancel(v)).pack(pady=(0, 4))

        ctk.CTkButton(btn_f, text="▶", width=38, height=30,
                      fg_color="#1a3a1a", hover_color=C["green"],
                      text_color="#fff", font=ctk.CTkFont(size=12),
                      command=lambda v=vid: self._play(v)).pack()

        self.widgets[vid["id"]] = {
            "pb": pb, "status": status_lbl, "info": info_lbl,
            "failed": False,
        }

    # ── Download logic ────────────────────────────────────────────────────────
    def _start_download(self, vid, pb, status_lbl, info_lbl):
        self.dl_path = self.path_entry.get().strip()
        os.makedirs(self.dl_path, exist_ok=True)
        self._save()

        vid_id = vid["id"]
        n      = len(self.videos)

        def on_progress(pct):
            self.after(0, lambda: pb.set(pct / 100))

        def on_status(st, speed, eta, size):
            # colour by state
            col = C["sub"]
            if st == "Completed":   col = C["green"]
            elif st == "Failed":    col = C["red"]
            elif st == "Cancelled": col = C["orange"]
            elif st == "Downloading": col = C["accent2"]

            info_parts = [p for p in [speed,
                                       f"ETA {eta}" if eta else None,
                                       size] if p]
            self.after(0, lambda:
                status_lbl.configure(text=st, text_color=col))
            self.after(0, lambda:
                info_lbl.configure(text="  ·  ".join(info_parts)))

        def on_complete(success):
            w = self.widgets.get(vid_id)
            if w:
                w["failed"] = not success
            if success:
                self.done_count += 1
                if n > 1:
                    self.after(0, lambda: self.overall_bar.set(self.done_count / n))
                    self.after(0, lambda: self.overall_lbl.configure(
                        text=f"{self.done_count} / {n} completed"))
            else:
                # show retry button if any failures
                self.after(0, lambda: self.retry_btn.pack(side="right"))

        fmt = "Audio" if "Audio" in self.fmt_v.get() else "Video"
        dl  = VideoDownloader(
            vid, self.dl_path, self.quality_v.get(), fmt,
            on_progress, on_status, on_complete,
            use_numbering=self.number_v.get(),
        )
        self.downloaders[vid_id] = dl
        dl.start()

    def _download_all(self):
        for vid in self.videos:
            w = self.widgets.get(vid["id"])
            if w:
                dl = self.downloaders.get(vid["id"])
                if dl is None or dl.cancelled:
                    self._start_download(vid, w["pb"], w["status"], w["info"])

    def _cancel_all(self):
        for dl in self.downloaders.values():
            if not dl.cancelled:
                dl.cancel()

    def _cancel(self, vid):
        dl = self.downloaders.get(vid["id"])
        if dl:
            dl.cancel()

    def _retry_failed(self):
        self.retry_btn.pack_forget()
        for vid in self.videos:
            vid_id = vid["id"]
            w  = self.widgets.get(vid_id)
            dl = self.downloaders.get(vid_id)
            if w and w.get("failed"):
                w["failed"] = False
                self.downloaders.pop(vid_id, None)
                self._start_download(vid, w["pb"], w["status"], w["info"])

    def _play(self, vid):
        title  = clean_filename(vid["title"])
        idx    = vid.get("index", 1)
        prefix = f"{idx:02d}. "
        exts   = [".mp4", ".webm", ".mkv", ".m4a", ".mp3"]

        for ext in exts:
            for name in [f"{prefix}{title}{ext}", f"{title}{ext}"]:
                path = os.path.join(self.dl_path, name)
                if os.path.exists(path):
                    if sys.platform == "win32":
                        os.startfile(path)
                    elif sys.platform == "darwin":
                        subprocess.run(["open", path])
                    else:
                        subprocess.run(["xdg-open", path])
                    return

        messagebox.showinfo("YT Downloader Pro",
                            "File not found — please download it first.")

    # ── Helpers ───────────────────────────────────────────────────────────────
    def _clear_list(self):
        for w in self.scroll.winfo_children():
            w.destroy()

    def _show_empty(self, text: str):
        ctk.CTkLabel(self.scroll, text=text,
                     font=ctk.CTkFont(size=13),
                     text_color=C["dim"]).grid(row=0, column=0, pady=60)

    def _on_close(self):
        self._save()
        self.destroy()


# ══════════════════════════════════════════════════════════════════════════════
#  ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    # Generate icon.ico once (needed before calling PyInstaller)
    generate_icon()

    app = App()
    app.mainloop()

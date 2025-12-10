import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import yt_dlp
import threading
import os
import subprocess
import sys
from pathlib import Path

class VideoDownloader:
    def __init__(self, video_info, download_path, quality, progress_callback, status_callback, complete_callback):
        self.video_info = video_info
        self.download_path = download_path
        self.quality = quality
        self.progress_callback = progress_callback
        self.status_callback = status_callback
        self.complete_callback = complete_callback
        self.cancelled = False
        self.paused = False
        self.thread = None
        self.retry_count = 0
        self.max_retries = 5

    def download(self):
        self.cancelled = False
        self.thread = threading.Thread(target=self._download_video, daemon=True)
        self.thread.start()

    def _download_video(self):
        video_url = self.video_info['url']
        video_title = self.video_info['title']
        
        # Quality format selection without merging
        if self.quality == "Best":
            format_option = 'best[ext=mp4]/best'
        elif self.quality == "1080p":
            format_option = 'best[height<=1080][ext=mp4]/best[height<=1080]'
        elif self.quality == "720p":
            format_option = 'best[height<=720][ext=mp4]/best[height<=720]'
        elif self.quality == "480p":
            format_option = 'best[height<=480][ext=mp4]/best[height<=480]'
        else:  # 360p
            format_option = 'best[height<=360][ext=mp4]/best[height<=360]'

        ydl_opts = {
            'format': format_option,
            'outtmpl': os.path.join(self.download_path, '%(title)s.%(ext)s'),
            'noplaylist': True,
            'quiet': True,
            'no_warnings': True,
            'socket_timeout': 30,
            'retries': 10,
            'fragment_retries': 10,
            'skip_unavailable_fragments': True,
            'progress_hooks': [self._progress_hook],
        }

        while self.retry_count < self.max_retries and not self.cancelled:
            try:
                self.status_callback("Downloading...")
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([video_url])
                
                self.status_callback("Completed")
                self.progress_callback(100)
                self.complete_callback(True)
                return
            
            except Exception as e:
                self.retry_count += 1
                error_msg = str(e)
                
                if self.cancelled:
                    self.status_callback("Cancelled")
                    self.complete_callback(False)
                    return
                
                if self.retry_count < self.max_retries:
                    self.status_callback(f"Retrying... ({self.retry_count}/{self.max_retries})")
                    import time
                    time.sleep(2)
                else:
                    self.status_callback(f"Failed: {error_msg[:50]}")
                    self.complete_callback(False)
                    return

    def _progress_hook(self, d):
        if self.cancelled:
            raise Exception("Download cancelled by user")
        
        if d['status'] == 'downloading':
            try:
                if 'total_bytes' in d:
                    total = d['total_bytes']
                elif 'total_bytes_estimate' in d:
                    total = d['total_bytes_estimate']
                else:
                    return
                
                downloaded = d['downloaded_bytes']
                percent = (downloaded / total) * 100
                self.progress_callback(percent)
            except:
                pass
        elif d['status'] == 'finished':
            self.progress_callback(100)

    def cancel(self):
        self.cancelled = True
        self.status_callback("Cancelling...")


class PlaylistDownloaderApp:
    def __init__(self, root):
        self.root = root
        self.root.title("YouTube Video/Playlist Downloader")
        self.root.geometry("800x700")
        self.root.configure(bg='#1e1e2e')
        self.root.resizable(False, False)

        self.videos = []
        self.downloaders = {}
        self.download_path = str(Path.home() / "Downloads" / "YouTube")
        
        self.setup_ui()

    def setup_ui(self):
        # Header Frame
        header_frame = tk.Frame(self.root, bg='#2d2d44', padx=20, pady=15)
        header_frame.pack(fill=tk.X)
        
        tk.Label(header_frame, text="YouTube Video/Playlist Downloader", 
                font=('Segoe UI', 18, 'bold'), bg='#2d2d44', fg='#cdd6f4').pack()

        # Input Frame
        input_frame = tk.Frame(self.root, bg='#1e1e2e', padx=20, pady=15)
        input_frame.pack(fill=tk.X)
        
        tk.Label(input_frame, text="Video/Playlist URL:", font=('Segoe UI', 10), 
                bg='#1e1e2e', fg='#cdd6f4').grid(row=0, column=0, sticky='w', pady=5)
        
        self.url_entry = tk.Entry(input_frame, font=('Segoe UI', 10), 
                                  bg='#313244', fg='#cdd6f4', insertbackground='#cdd6f4',
                                  relief=tk.FLAT, width=60)
        self.url_entry.grid(row=0, column=1, padx=10, pady=5)
        
        tk.Label(input_frame, text="Save to:", font=('Segoe UI', 10), 
                bg='#1e1e2e', fg='#cdd6f4').grid(row=1, column=0, sticky='w', pady=5)
        
        path_frame = tk.Frame(input_frame, bg='#1e1e2e')
        path_frame.grid(row=1, column=1, sticky='w', pady=5)
        
        self.path_entry = tk.Entry(path_frame, font=('Segoe UI', 10), 
                                   bg='#313244', fg='#cdd6f4', insertbackground='#cdd6f4',
                                   relief=tk.FLAT, width=45)
        self.path_entry.insert(0, self.download_path)
        self.path_entry.pack(side=tk.LEFT, padx=(0, 10))
        
        browse_btn = tk.Button(path_frame, text="Browse", command=self.browse_folder,
                               font=('Segoe UI', 9), bg='#45475a', fg='#cdd6f4',
                               activebackground='#585b70', relief=tk.FLAT, padx=15, pady=5)
        browse_btn.pack(side=tk.LEFT)
        
        tk.Label(input_frame, text="Quality:", font=('Segoe UI', 10), 
                bg='#1e1e2e', fg='#cdd6f4').grid(row=2, column=0, sticky='w', pady=5)
        
        self.quality_var = tk.StringVar(value="720p")
        quality_combo = ttk.Combobox(input_frame, textvariable=self.quality_var, 
                                     values=["Best", "1080p", "720p", "480p", "360p"],
                                     font=('Segoe UI', 10), width=15, state='readonly')
        quality_combo.grid(row=2, column=1, sticky='w', padx=10, pady=5)
        
        # Buttons Frame
        btn_frame = tk.Frame(input_frame, bg='#1e1e2e')
        btn_frame.grid(row=3, column=1, sticky='w', pady=10)
        
        load_btn = tk.Button(btn_frame, text="Load Video/Playlist", command=self.load_content,
                            font=('Segoe UI', 10, 'bold'), bg='#89b4fa', fg='#1e1e2e',
                            activebackground='#74c7ec', relief=tk.FLAT, padx=20, pady=8)
        load_btn.pack(side=tk.LEFT, padx=(0, 10))
        
        self.download_all_btn = tk.Button(btn_frame, text="Download All", 
                                         command=self.download_all,
                                         font=('Segoe UI', 10, 'bold'), bg='#a6e3a1', 
                                         fg='#1e1e2e', activebackground='#94e2d5',
                                         relief=tk.FLAT, padx=20, pady=8, state=tk.DISABLED)
        self.download_all_btn.pack(side=tk.LEFT)
        
        # Videos Frame with Scrollbar
        videos_container = tk.Frame(self.root, bg='#1e1e2e')
        videos_container.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)
        
        canvas = tk.Canvas(videos_container, bg='#1e1e2e', highlightthickness=0)
        scrollbar = tk.Scrollbar(videos_container, orient="vertical", command=canvas.yview)
        self.videos_frame = tk.Frame(canvas, bg='#1e1e2e')
        
        self.videos_frame.bind("<Configure>", 
                              lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        
        canvas.create_window((0, 0), window=self.videos_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Bind mousewheel
        canvas.bind_all("<MouseWheel>", lambda e: canvas.yview_scroll(int(-1*(e.delta/120)), "units"))

    def browse_folder(self):
        folder = filedialog.askdirectory()
        if folder:
            self.path_entry.delete(0, tk.END)
            self.path_entry.insert(0, folder)
            self.download_path = folder

    def load_content(self):
        url = self.url_entry.get().strip()
        if not url:
            messagebox.showwarning("Warning", "Please enter a video or playlist URL")
            return
        
        # Clear previous videos
        for widget in self.videos_frame.winfo_children():
            widget.destroy()
        self.videos.clear()
        self.downloaders.clear()
        
        loading_label = tk.Label(self.videos_frame, text="Loading...", 
                                font=('Segoe UI', 12), bg='#1e1e2e', fg='#cdd6f4')
        loading_label.pack(pady=20)
        
        threading.Thread(target=self._fetch_content, args=(url,), daemon=True).start()

    def _fetch_content(self, url):
        try:
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'extract_flat': 'in_playlist',
            }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                
                # Check if it's a playlist or a single video
                if 'entries' in info:
                    # It's a playlist
                    entries = info['entries']
                    for entry in entries:
                        if entry:
                            video_info = {
                                'title': entry.get('title', 'Unknown'),
                                'url': f"https://www.youtube.com/watch?v={entry.get('id', '')}",
                                'id': entry.get('id', '')
                            }
                            self.videos.append(video_info)
                else:
                    # It's a single video
                    video_info = {
                        'title': info.get('title', 'Unknown'),
                        'url': url,
                        'id': info.get('id', '')
                    }
                    self.videos.append(video_info)
            
            self.root.after(0, self._display_videos)
        
        except Exception as e:
            self.root.after(0, lambda: messagebox.showerror("Error", f"Failed to load content: {str(e)}"))
            self.root.after(0, self._clear_loading)

    def _clear_loading(self):
        for widget in self.videos_frame.winfo_children():
            widget.destroy()

    def _display_videos(self):
        for widget in self.videos_frame.winfo_children():
            widget.destroy()
        
        if not self.videos:
            tk.Label(self.videos_frame, text="No videos found", 
                    font=('Segoe UI', 12), bg='#1e1e2e', fg='#f38ba8').pack(pady=20)
            return
        
        self.download_all_btn.config(state=tk.NORMAL)
        
        # Display count
        count_label = tk.Label(self.videos_frame, 
                              text=f"Found {len(self.videos)} video(s)", 
                              font=('Segoe UI', 10, 'bold'), 
                              bg='#1e1e2e', fg='#a6e3a1')
        count_label.pack(pady=10)
        
        for idx, video in enumerate(self.videos):
            self._create_video_row(idx, video)

    def _create_video_row(self, idx, video):
        row_frame = tk.Frame(self.videos_frame, bg='#313244', relief=tk.FLAT, bd=1)
        row_frame.pack(fill=tk.X, padx=5, pady=5)
        
        # Video title
        title_text = f"{idx + 1}. {video['title'][:80]}"
        title_label = tk.Label(row_frame, text=title_text, font=('Segoe UI', 9), 
                              bg='#313244', fg='#cdd6f4', anchor='w')
        title_label.grid(row=0, column=0, sticky='w', padx=10, pady=5, columnspan=3)
        
        # Progress bar
        progress = ttk.Progressbar(row_frame, length=300, mode='determinate')
        progress.grid(row=1, column=0, padx=10, pady=5)
        
        # Status label
        status_label = tk.Label(row_frame, text="Ready", font=('Segoe UI', 8), 
                               bg='#313244', fg='#a6adc8', width=20)
        status_label.grid(row=1, column=1, padx=5)
        
        # Buttons frame
        btn_frame = tk.Frame(row_frame, bg='#313244')
        btn_frame.grid(row=1, column=2, padx=10)
        
        download_btn = tk.Button(btn_frame, text="⬇ Download", 
                                command=lambda v=video, p=progress, s=status_label: self.download_video(v, p, s),
                                font=('Segoe UI', 8), bg='#89b4fa', fg='#1e1e2e',
                                relief=tk.FLAT, padx=10, pady=3)
        download_btn.pack(side=tk.LEFT, padx=2)
        
        cancel_btn = tk.Button(btn_frame, text="✖ Cancel", 
                              command=lambda v=video: self.cancel_video(v),
                              font=('Segoe UI', 8), bg='#f38ba8', fg='#1e1e2e',
                              relief=tk.FLAT, padx=10, pady=3)
        cancel_btn.pack(side=tk.LEFT, padx=2)
        
        play_btn = tk.Button(btn_frame, text="▶ Play", 
                            command=lambda v=video: self.play_video(v),
                            font=('Segoe UI', 8), bg='#a6e3a1', fg='#1e1e2e',
                            relief=tk.FLAT, padx=10, pady=3)
        play_btn.pack(side=tk.LEFT, padx=2)
        
        # Store references
        video['progress'] = progress
        video['status_label'] = status_label

    def download_video(self, video, progress, status_label):
        self.download_path = self.path_entry.get().strip()
        if not self.download_path:
            messagebox.showwarning("Warning", "Please select a download folder")
            return
        
        os.makedirs(self.download_path, exist_ok=True)
        
        def progress_callback(percent):
            self.root.after(0, lambda: progress.config(value=percent))
        
        def status_callback(status):
            self.root.after(0, lambda: status_label.config(text=status))
        
        def complete_callback(success):
            if success:
                self.root.after(0, lambda: status_label.config(text="Completed", fg='#a6e3a1'))
        
        downloader = VideoDownloader(
            video, self.download_path, self.quality_var.get(),
            progress_callback, status_callback, complete_callback
        )
        self.downloaders[video['id']] = downloader
        downloader.download()

    def cancel_video(self, video):
        if video['id'] in self.downloaders:
            self.downloaders[video['id']].cancel()

    def play_video(self, video):
        # Find the downloaded video file
        video_title = video['title']
        # Clean the title to match the filename
        import re
        clean_title = re.sub(r'[\\/*?:"<>|]', "", video_title)
        
        # Look for the video file with common extensions
        extensions = ['.mp4', '.webm', '.mkv', '.m4a']
        video_path = None
        
        for ext in extensions:
            potential_path = os.path.join(self.download_path, f"{clean_title}{ext}")
            if os.path.exists(potential_path):
                video_path = potential_path
                break
        
        if video_path and os.path.exists(video_path):
            # Open with default video player
            if sys.platform == 'win32':
                os.startfile(video_path)
            elif sys.platform == 'darwin':  # macOS
                subprocess.run(['open', video_path])
            else:  # Linux
                subprocess.run(['xdg-open', video_path])
        else:
            messagebox.showinfo("Info", "Video not found. Please download it first.")

    def download_all(self):
        self.download_path = self.path_entry.get().strip()
        if not self.download_path:
            messagebox.showwarning("Warning", "Please select a download folder")
            return
        
        for video in self.videos:
            if video['id'] not in self.downloaders or self.downloaders[video['id']].cancelled:
                self.download_video(video, video['progress'], video['status_label'])


if __name__ == "__main__":
    root = tk.Tk()
    app = PlaylistDownloaderApp(root)
    root.mainloop()
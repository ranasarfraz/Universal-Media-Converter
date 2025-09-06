
import os
import sys
import glob
import shutil
import subprocess
import threading
import tempfile
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
# --- put near imports ---
import sys, os
if os.name == "nt":
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "MachSquare.UniversalMediaConverter"
        )
    except Exception:
        pass

def _res_path(name: str) -> str:
    """Find resource both in dev and PyInstaller .exe."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(sys.argv[0]))
    return os.path.join(base, name)

APP_NAME = "Universal Media Converter (ffmpeg)"
VERSION = "1.3"

VIDEO_CONTAINERS = ["mp4", "mkv", "mov", "avi", "ts", "flv", "webm", "m4v", "3gp", "mpg"]
AUDIO_FORMATS = ["mp3", "aac", "m4a", "wav", "flac", "ogg", "opus", "wma", "aiff", "amr"]
IMAGE_FORMATS = ["png", "jpg", "jpeg", "bmp", "tiff", "webp"]
SUB_FORMATS = ["srt", "vtt", "ass", "ssa"]

VIDEO_CODECS = ["copy (no re-encode)", "h264", "hevc (h265)", "vp9", "av1"]
AUDIO_CODECS = ["copy (no re-encode)", "aac", "mp3", "opus", "vorbis", "flac", "pcm_s16le"]
GIF_PALETTES = ["auto (simple)", "optimized (palettegen)"]

MODES = [
    "Video → Video",
    "Video → Audio",
    "Audio → Audio",
    "Video → Images",
    "Images → Video",
    "Video → GIF",
    "Subtitles: Extract",
    "Subtitles: Convert",
    "Subtitles: Burn into Video"
]

def _find(bin_name: str) -> str:
    """
    Prefer a binary placed next to the script/exe. Fallback to PATH.
    This makes the packaged .exe portable if ffmpeg.exe / ffprobe.exe are shipped beside it.
    """
    here = os.path.dirname(sys.argv[0])  # Works for both .py and frozen .exe
    local = os.path.join(here, bin_name + (".exe" if os.name == "nt" else ""))
    if os.path.exists(local):
        return local
    return shutil.which(bin_name) or bin_name

FFMPEG = _find("ffmpeg")
FFPROBE = _find("ffprobe")

def ffmpeg_exists() -> bool:
    try:
        subprocess.run([FFMPEG, "-version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        subprocess.run([FFPROBE, "-version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        return True
    except Exception:
        return False

class UniversalConverter(tk.Tk):
    def __init__(self):
        super().__init__()




        icon_path = _res_path("app_icon.ico")
        try:
            # Windows supports .ico directly
            self.iconbitmap(icon_path)
            win = tk.Toplevel(self)
            win.iconbitmap(_res_path("app_icon.ico"))
        except Exception:
            # Fallback for other platforms: use a PNG if you have one
            try:
                ico_png = _res_path("app_icon.png")
                self.iconphoto(True, tk.PhotoImage(file=ico_png))
            except Exception:
                pass
 



        # ----- Window behavior -----
        self.title(f"{APP_NAME} v{VERSION}")
        self.minsize(1100, 720)
        try:
            self.state('zoomed')  # Windows maximize (no-op elsewhere)
        except Exception:
            pass
        self.configure(padx=16, pady=14)

        # Base font
        base_font = ("Segoe UI", 10)
        self.option_add("*Font", base_font)

        # ----- State vars -----
        self.mode = tk.StringVar(value=MODES[0])
        self.input_var = tk.StringVar()
        self.output_var = tk.StringVar()
        self.out_format = tk.StringVar(value="mp4")
        self.video_codec = tk.StringVar(value=VIDEO_CODECS[0])
        self.audio_codec = tk.StringVar(value=AUDIO_CODECS[0])
        self.crf = tk.StringVar(value="23")
        self.bitrate = tk.StringVar(value="")
        self.scale = tk.StringVar(value="")
        self.fps = tk.StringVar(value="")
        self.audio_bitrate = tk.StringVar(value="")
        self.start_time = tk.StringVar(value="")
        self.duration = tk.StringVar(value="")
        self.gif_palette = tk.StringVar(value=GIF_PALETTES[1])
        self.sub_stream_index = tk.StringVar(value="0")
        self.sub_in_fmt = tk.StringVar(value=SUB_FORMATS[0])
        self.sub_out_fmt = tk.StringVar(value=SUB_FORMATS[1])
        self.image_pattern = tk.StringVar(value="")
        self.images_fps = tk.StringVar(value="24")
        self.temp_seq_dir = None  # for Images→Video folder fallback

        # Layout growth
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(9, weight=1)  # log row

        # Header
        title = ttk.Label(self, text=APP_NAME, font=("Segoe UI", 18, "bold"))
        title.grid(row=0, column=0, sticky="w")
        subtitle = ttk.Label(self, text="Powered by FFmpeg • Remux, transcode, extract audio, images, GIFs, and subtitles")
        subtitle.grid(row=1, column=0, sticky="w", pady=(0, 10))

        # Mode
        mode_row = ttk.Frame(self)
        mode_row.grid(row=2, column=0, sticky="ew", pady=(0,6))
        mode_row.grid_columnconfigure(2, weight=1)
        ttk.Label(mode_row, text="Mode:", width=10).grid(row=0, column=0, sticky="w")
        mode_combo = ttk.Combobox(mode_row, values=MODES, textvariable=self.mode, state="readonly", width=32)
        mode_combo.grid(row=0, column=1, sticky="w")
        mode_combo.bind("<<ComboboxSelected>>", lambda e: self._refresh_options())

        # IO
        io = ttk.Frame(self)
        io.grid(row=3, column=0, sticky="ew", pady=(4,6))
        io.grid_columnconfigure(1, weight=1)

        ttk.Label(io, text="Input", width=10).grid(row=0, column=0, sticky="w")
        in_entry = ttk.Entry(io, textvariable=self.input_var)
        in_entry.grid(row=0, column=1, sticky="ew", padx=(6,6))
        ttk.Button(io, text="Browse…", command=self.browse_input, width=12).grid(row=0, column=2, sticky="e")

        ttk.Label(io, text="Output", width=10).grid(row=1, column=0, sticky="w", pady=(6,0))
        out_entry = ttk.Entry(io, textvariable=self.output_var)
        out_entry.grid(row=1, column=1, sticky="ew", padx=(6,6), pady=(6,0))
        ttk.Button(io, text="Browse…", command=self.browse_output, width=12).grid(row=1, column=2, sticky="e", pady=(6,0))

        # Format/codec
        fmt = ttk.Frame(self)
        fmt.grid(row=4, column=0, sticky="ew", pady=(4,10))
        ttk.Label(fmt, text="Output format", width=14).grid(row=0, column=0, sticky="w")
        self.format_combo = ttk.Combobox(fmt, values=VIDEO_CONTAINERS + AUDIO_FORMATS + IMAGE_FORMATS + SUB_FORMATS + ["gif"], textvariable=self.out_format, width=10, state="readonly")
        self.format_combo.grid(row=0, column=1, sticky="w", padx=(6,12))
        ttk.Label(fmt, text="Video codec", width=12).grid(row=0, column=2, sticky="w")
        self.vcodec_combo = ttk.Combobox(fmt, values=VIDEO_CODECS, textvariable=self.video_codec, width=20, state="readonly")
        self.vcodec_combo.grid(row=0, column=3, sticky="w", padx=(6,12))
        ttk.Label(fmt, text="Audio codec", width=12).grid(row=0, column=4, sticky="w")
        self.acodec_combo = ttk.Combobox(fmt, values=AUDIO_CODECS, textvariable=self.audio_codec, width=20, state="readonly")
        self.acodec_combo.grid(row=0, column=5, sticky="w", padx=(6,12))

        # Advanced
        adv = ttk.LabelFrame(self, text="Advanced")
        adv.grid(row=5, column=0, sticky="ew", pady=(0,10))
        for c in range(12):
            adv.grid_columnconfigure(c, weight=0)

        r = 0
        ttk.Label(adv, text="CRF (x264/x265)").grid(row=r, column=0, sticky="w", padx=6, pady=6)
        ttk.Entry(adv, width=7, textvariable=self.crf).grid(row=r, column=1, sticky="w")
        ttk.Label(adv, text="Video bitrate (e.g. 2500k)").grid(row=r, column=2, sticky="w", padx=(14,6))
        ttk.Entry(adv, width=12, textvariable=self.bitrate).grid(row=r, column=3, sticky="w")
        ttk.Label(adv, text="Audio bitrate").grid(row=r, column=4, sticky="w", padx=(14,6))
        ttk.Entry(adv, width=10, textvariable=self.audio_bitrate).grid(row=r, column=5, sticky="w")
        ttk.Label(adv, text="Scale (WxH)").grid(row=r, column=6, sticky="w", padx=(14,6))
        ttk.Entry(adv, width=12, textvariable=self.scale).grid(row=r, column=7, sticky="w")
        ttk.Label(adv, text="FPS").grid(row=r, column=8, sticky="w", padx=(14,6))
        ttk.Entry(adv, width=7, textvariable=self.fps).grid(row=r, column=9, sticky="w")

        r += 1
        ttk.Label(adv, text="Start at (HH:MM:SS)").grid(row=r, column=0, sticky="w", padx=6, pady=6)
        ttk.Entry(adv, width=12, textvariable=self.start_time).grid(row=r, column=1, sticky="w")
        ttk.Label(adv, text="Duration (HH:MM:SS)").grid(row=r, column=2, sticky="w", padx=(14,6))
        ttk.Entry(adv, width=12, textvariable=self.duration).grid(row=r, column=3, sticky="w")
        ttk.Label(adv, text="GIF palette").grid(row=r, column=4, sticky="w", padx=(14,6))
        ttk.Combobox(adv, values=GIF_PALETTES, textvariable=self.gif_palette, width=24, state="readonly").grid(row=r, column=5, sticky="w")
        ttk.Label(adv, text="Sub idx").grid(row=r, column=6, sticky="w", padx=(14,6))
        ttk.Entry(adv, width=5, textvariable=self.sub_stream_index).grid(row=r, column=7, sticky="w")
        ttk.Label(adv, text="Sub in").grid(row=r, column=8, sticky="w", padx=(14,6))
        ttk.Combobox(adv, values=SUB_FORMATS, textvariable=self.sub_in_fmt, width=7, state="readonly").grid(row=r, column=9, sticky="w")
        ttk.Label(adv, text="Sub out").grid(row=r, column=10, sticky="w", padx=(14,6))
        ttk.Combobox(adv, values=SUB_FORMATS, textvariable=self.sub_out_fmt, width=7, state="readonly").grid(row=r, column=11, sticky="w")

        # Images
        imgs = ttk.LabelFrame(self, text="Images")
        imgs.grid(row=6, column=0, sticky="ew", pady=(0,10))
        imgs.grid_columnconfigure(1, weight=1)
        ttk.Label(imgs, text="Image pattern or folder", width=20).grid(row=0, column=0, sticky="w", padx=6, pady=6)
        ttk.Entry(imgs, textvariable=self.image_pattern).grid(row=0, column=1, sticky="ew", padx=(6,6))
        ttk.Button(imgs, text="Browse…", command=self.browse_images, width=12).grid(row=0, column=2, sticky="e")
        ttk.Label(imgs, text="Images FPS").grid(row=0, column=3, sticky="w", padx=(16,6))
        ttk.Entry(imgs, width=7, textvariable=self.images_fps).grid(row=0, column=4, sticky="w")

        # Controls
        ctrl = ttk.Frame(self)
        ctrl.grid(row=7, column=0, sticky="ew")
        ctrl.grid_columnconfigure(1, weight=1)
        self.convert_btn = ttk.Button(ctrl, text="Convert", command=self.on_convert, width=14)
        self.convert_btn.grid(row=0, column=0, sticky="w")
        self.prog = ttk.Progressbar(ctrl, mode="indeterminate")
        self.prog.grid(row=0, column=1, sticky="ew", padx=(10,0))

        # Log
        ttk.Label(self, text="Log").grid(row=8, column=0, sticky="w", pady=(10,4))
        self.log = tk.Text(self, height=14, wrap="word")
        self.log.grid(row=9, column=0, sticky="nsew")
        self._append(f"Tip: FFmpeg binary: {FFMPEG}\n")
        self._append(f"Tip: FFprobe binary: {FFPROBE}\n")
        if not ffmpeg_exists():
            self._append("Warning: ffmpeg/ffprobe not detected.\n")

        self._refresh_options()

    # ---------------- UI helpers ----------------
    def _append(self, text: str):
        self.log.insert("end", text)
        self.log.see("end")

    def set_busy(self, busy: bool):
        if busy:
            self.convert_btn.configure(state="disabled")
            self.prog.start(10)
        else:
            self.convert_btn.configure(state="normal")
            self.prog.stop()

    def browse_input(self):
        m = self.mode.get()
        if m in ("Images → Video",):
            path = filedialog.askdirectory(title="Choose folder with images (or cancel)")
            if path:
                self.image_pattern.set(path)
        else:
            types = [("All media", "*.*")]
            path = filedialog.askopenfilename(title="Choose input file", filetypes=types)
            if path:
                self.input_var.set(path)
                self._suggest_output()

    def browse_output(self):
        fmt = self.out_format.get().lower()
        initial = self.output_var.get() or f"output.{fmt}"
        path = filedialog.asksaveasfilename(
            title="Save as",
            initialfile=os.path.basename(initial),
            defaultextension=f".{fmt}",
            filetypes=[(fmt.upper(), f"*.{fmt}"), ("All files","*.*")]
        )
        if path:
            root, ext = os.path.splitext(path)
            want = f".{fmt}"
            if ext.lower() != want:
                path = root + want
            self.output_var.set(path)

    def browse_images(self):
        path = filedialog.askdirectory(title="Choose images folder")
        if path:
            self.image_pattern.set(path)

    def _suggest_output(self):
        m = self.mode.get()
        fmt = self._default_format_for_mode()
        inpath = self.input_var.get().strip()
        if inpath and fmt:
            base = os.path.splitext(inpath)[0]
            # If video->images, suggest numbered pattern
            if m == "Video → Images":
                self.output_var.set(base + "_frame_%04d.png")
                self.out_format.set("png")
            else:
                self.output_var.set(base + "." + fmt)
                self.out_format.set(fmt)

    def _default_format_for_mode(self):
        m = self.mode.get()
        if m == "Video → Video": return "mp4"
        if m == "Video → Audio": return "mp3"
        if m == "Audio → Audio": return "mp3"
        if m == "Video → Images": return "png"
        if m == "Images → Video": return "mp4"
        if m == "Video → GIF":   return "gif"
        if m.startswith("Subtitles"): return "srt"
        return "mp4"

    def _refresh_options(self):
        m = self.mode.get()
        if m in ("Video → Video", "Images → Video"):
            self.vcodec_combo.configure(state="readonly")
            self.acodec_combo.configure(state="readonly")
        elif m in ("Video → GIF", "Video → Images"):
            self.vcodec_combo.configure(state="disabled")
            self.acodec_combo.configure(state="disabled")
        elif m in ("Video → Audio", "Audio → Audio"):
            self.vcodec_combo.configure(state="disabled")
            self.acodec_combo.configure(state="readonly")
        elif m.startswith("Subtitles"):
            self.vcodec_combo.configure(state="disabled")
            self.acodec_combo.configure(state="disabled")
        self._suggest_output()

    # ---------------- Main convert ----------------
    def on_convert(self):
        if not ffmpeg_exists():
            messagebox.showerror("ffmpeg not found", "ffmpeg/ffprobe are not installed or not found.\n\nPlace ffmpeg.exe & ffprobe.exe next to this app, or add them to PATH.")
            return
        m = self.mode.get()
        if m != "Images → Video" and not self.input_var.get().strip():
            messagebox.showerror("Missing input", "Please choose an input file.")
            return
        if not self.output_var.get().strip():
            self._suggest_output()
        if not self.output_var.get().strip():
            messagebox.showerror("Missing output", "Please choose an output file.")
            return

        self.set_busy(True)
        threading.Thread(target=self._run_mode, daemon=True).start()

    def _run_mode(self):
        m = self.mode.get()
        try:
            if m == "Video → Video":
                cmd = self._cmd_video_to_video()
                self._run_ffmpeg(cmd)
            elif m == "Video → Audio":
                cmd = self._cmd_video_to_audio()
                self._run_ffmpeg(cmd)
            elif m == "Audio → Audio":
                cmd = self._cmd_audio_to_audio()
                self._run_ffmpeg(cmd)
            elif m == "Video → Images":
                cmd = self._cmd_video_to_images()
                self._run_ffmpeg(cmd)
            elif m == "Images → Video":
                cmds = self._cmd_images_to_video()
                if isinstance(cmds[0], list):
                    for c in cmds:
                        self._run_ffmpeg(c, allow_fail=(c != cmds[-1]))
                else:
                    self._run_ffmpeg(cmds)
            elif m == "Video → GIF":
                cmds = self._cmd_video_to_gif()
                for c in cmds:
                    self._run_ffmpeg(c, allow_fail=(c != cmds[-1]))
            elif m == "Subtitles: Extract":
                cmd = self._cmd_sub_extract()
                self._run_ffmpeg(cmd)
            elif m == "Subtitles: Convert":
                cmd = self._cmd_sub_convert()
                self._run_ffmpeg(cmd)
            elif m == "Subtitles: Burn into Video":
                cmd = self._cmd_sub_burn()
                self._run_ffmpeg(cmd)
            else:
                raise RuntimeError("Unknown mode")
        except Exception as e:
            self._append(f"\n❌ Error: {e}\n")
            messagebox.showerror("Error", str(e))
        finally:
            self.set_busy(False)
            if self.temp_seq_dir and os.path.isdir(self.temp_seq_dir):
                try:
                    shutil.rmtree(self.temp_seq_dir, ignore_errors=True)
                except Exception:
                    pass
                self.temp_seq_dir = None

    # ---------------- Command builders ----------------
    def _common_inputs(self):
        args = []
        if self.start_time.get().strip():
            args += ["-ss", self.start_time.get().strip()]
        if self.duration.get().strip():
            args += ["-t", self.duration.get().strip()]
        return args

    def _video_filters(self):
        vf = []
        if self.scale.get().strip():
            vf.append(f"scale={self.scale.get().strip()}")
        if self.fps.get().strip():
            vf.append(f"fps={self.fps.get().strip()}")
        return ",".join(vf) if vf else None

    def _cmd_video_to_video(self):
        inp = self.input_var.get().strip()
        out = self.output_var.get().strip()
        vcodec = self.video_codec.get()
        acodec = self.audio_codec.get()
        fmt = self.out_format.get().lower()

        cmd = [FFMPEG, "-y"] + self._common_inputs() + ["-i", inp]

        if vcodec.startswith("copy"):
            cmd += ["-c:v", "copy"]
        elif vcodec == "h264":
            cmd += ["-c:v", "libx264", "-preset", "medium", "-crf", self.crf.get().strip() or "23"]
        elif vcodec.startswith("hevc"):
            cmd += ["-c:v", "libx265", "-preset", "medium", "-crf", self.crf.get().strip() or "28"]
        elif vcodec == "vp9":
            cmd += ["-c:v", "libvpx-vp9", "-b:v", self.bitrate.get().strip() or "0"]
        elif vcodec == "av1":
            cmd += ["-c:v", "libaom-av1", "-crf", self.crf.get().strip() or "30", "-b:v", "0"]
        else:
            cmd += ["-c:v", "libx264", "-crf", "23"]

        vf = self._video_filters()
        if vf:
            cmd += ["-vf", vf]

        if acodec.startswith("copy"):
            cmd += ["-c:a", "copy"]
        elif acodec == "aac":
            cmd += ["-c:a", "aac", "-b:a", self.audio_bitrate.get().strip() or "192k"]
        elif acodec == "mp3":
            cmd += ["-c:a", "libmp3lame", "-b:a", self.audio_bitrate.get().strip() or "192k"]
        elif acodec == "opus":
            cmd += ["-c:a", "libopus", "-b:a", self.audio_bitrate.get().strip() or "128k"]
        elif acodec == "vorbis":
            cmd += ["-c:a", "libvorbis", "-b:a", self.audio_bitrate.get().strip() or "160k"]
        elif acodec == "flac":
            cmd += ["-c:a", "flac"]
        elif acodec == "pcm_s16le":
            cmd += ["-c:a", "pcm_s16le"]
        else:
            cmd += ["-c:a", "aac", "-b:a", "192k"]

        if fmt in VIDEO_CONTAINERS:
            cmd += ["-f", fmt]

        cmd += [out]
        return cmd

    def _cmd_video_to_audio(self):
        inp = self.input_var.get().strip()
        out = self.output_var.get().strip()
        acodec = self.audio_codec.get()
        cmd = [FFMPEG, "-y"] + self._common_inputs() + ["-i", inp, "-vn"]
        if acodec.startswith("copy"):
            cmd += ["-c:a", "copy"]
        elif acodec == "aac":
            cmd += ["-c:a", "aac", "-b:a", self.audio_bitrate.get().strip() or "192k"]
        elif acodec == "mp3":
            cmd += ["-c:a", "libmp3lame", "-b:a", self.audio_bitrate.get().strip() or "192k"]
        elif acodec == "opus":
            cmd += ["-c:a", "libopus", "-b:a", self.audio_bitrate.get().strip() or "128k"]
        elif acodec == "vorbis":
            cmd += ["-c:a", "libvorbis", "-b:a", self.audio_bitrate.get().strip() or "160k"]
        elif acodec == "flac":
            cmd += ["-c:a", "flac"]
        elif acodec == "pcm_s16le":
            cmd += ["-c:a", "pcm_s16le"]
        else:
            cmd += ["-c:a", "libmp3lame", "-b:a", "192k"]
        cmd += [out]
        return cmd

    def _cmd_audio_to_audio(self):
        return self._cmd_video_to_audio()

    def _cmd_video_to_images(self):
        inp = self.input_var.get().strip()
        out = self.output_var.get().strip()
        if "%0" not in out:
            raise RuntimeError("For 'Video → Images', set output like: C:/path/frame_%04d.png")
        cmd = [FFMPEG, "-y"] + self._common_inputs() + ["-i", inp]
        vf = self._video_filters()
        if vf:
            cmd += ["-vf", vf]
        if self.fps.get().strip():
            cmd += ["-r", self.fps.get().strip()]
        cmd += [out]
        return cmd

    def _build_sequence_folder(self, src_dir: str):
        self.temp_seq_dir = tempfile.mkdtemp(prefix="umc_seq_")
        files = []
        for ext in ("*.png", "*.jpg", "*.jpeg"):
            files.extend(sorted(glob.glob(os.path.join(src_dir, ext))))
        if not files:
            raise RuntimeError("No PNG/JPG images found in selected folder.")
        for i, f in enumerate(files, start=1):
            dst = os.path.join(self.temp_seq_dir, f"img_{i:06d}.png")
            try:
                shutil.copy2(f, dst)
            except Exception as e:
                raise RuntimeError(f"Failed to copy {f}: {e}")
        return os.path.join(self.temp_seq_dir, "img_%06d.png")

    def _cmd_images_to_video(self):
        src = self.image_pattern.get().strip()
        out = self.output_var.get().strip()
        fmt = self.out_format.get().lower()

        if os.path.isdir(src):
            pattern = self._build_sequence_folder(src)
            cmd = [FFMPEG, "-y", "-framerate", self.images_fps.get().strip() or "24", "-i", pattern]
        else:
            cmd = [FFMPEG, "-y", "-framerate", self.images_fps.get().strip() or "24", "-i", src]

        vf = self._video_filters()
        if vf:
            cmd += ["-vf", vf]

        if fmt == "webm":
            cmd += ["-c:v", "libvpx-vp9", "-b:v", self.bitrate.get().strip() or "0"]
        else:
            cmd += ["-c:v", "libx264", "-preset", "medium", "-crf", self.crf.get().strip() or "23"]

        cmd += [out]
        return cmd

    def _cmd_video_to_gif(self):
        inp = self.input_var.get().strip()
        out = self.output_var.get().strip()
        palette = os.path.splitext(out)[0] + "_palette.png"
        vf = self._video_filters() or "fps=15,scale=640:-1:flags=lanczos"

        if self.gif_palette.get().startswith("optimized"):
            p1 = [FFMPEG, "-y"] + self._common_inputs() + ["-i", inp, "-vf", vf + ",palettegen", palette]
            p2 = [FFMPEG, "-y"] + self._common_inputs() + ["-i", inp, "-i", palette, "-lavfi", f"{vf} [x]; [x][1:v] paletteuse", out]
            return [p1, p2]
        else:
            return [[FFMPEG, "-y"] + self._common_inputs() + ["-i", inp, "-vf", vf, out]]

    def _cmd_sub_extract(self):
        inp = self.input_var.get().strip()
        out = self.output_var.get().strip()
        idx = self.sub_stream_index.get().strip() or "0"
        return [FFMPEG, "-y", "-i", inp, "-map", f"0:s:{idx}", out]

    def _cmd_sub_convert(self):
        inp = self.input_var.get().strip()
        out = self.output_var.get().strip()
        return [FFMPEG, "-y", "-i", inp, out]

    def _cmd_sub_burn(self):
        inp = self.input_var.get().strip()
        out = self.output_var.get().strip()
        subfile = self.image_pattern.get().strip()
        if not subfile or not os.path.exists(subfile):
            raise RuntimeError("Pick a subtitle file to burn (use the Images section's 'Browse…' to select .srt/.ass).")
        vf = self._video_filters()
        subfile_fixed = subfile.replace("\\", "/")
        subfilter = f"subtitles='{subfile_fixed}'"
        vf = (vf + "," + subfilter) if vf else subfilter
        return [FFMPEG, "-y"] + self._common_inputs() + ["-i", inp, "-vf", vf, "-c:v", "libx264", "-preset", "medium", "-crf", self.crf.get().strip() or "20", "-c:a", "copy", out]

    # ---------------- Runner ----------------
    def _run_ffmpeg(self, cmd, allow_fail=False):
        if isinstance(cmd[0], list):
            for c in cmd:
                self._run_ffmpeg(c, allow_fail=(c != cmd[-1]))
            return

        self._append("\n$ " + " ".join(cmd) + "\n")
        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
            for line in proc.stdout:
                self._append(line)
            rc = proc.wait()
            if rc != 0 and not allow_fail:
                raise RuntimeError(f"ffmpeg exited with code {rc}")
        except Exception as e:
            if allow_fail:
                self._append(f"(non-fatal) {e}\n")
            else:
                raise

if __name__ == "__main__":
    app = UniversalConverter()
    app.mainloop()

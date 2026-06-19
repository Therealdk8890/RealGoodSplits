"""Desktop GUI for RealGoodSplits, built with CustomTkinter.

Launch with ``python -m realgoodsplits`` or the ``realgoodsplits`` entry point.
The heavy ML work runs on a background thread so the window stays responsive;
progress and log lines are marshalled back to the UI through a queue.
"""

from __future__ import annotations

import queue
import threading
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk

from . import __version__
from .separator import (
    MODELS,
    MODEL_STEMS,
    StemSeparator,
    auto_device,
    collect_audio_files,
)

# Optional drag-and-drop. We subclass CTk + the tkdnd wrapper when available,
# and fall back to a plain CTk window otherwise.
try:
    from tkinterdnd2 import DND_FILES, TkinterDnD

    class _Root(ctk.CTk, TkinterDnD.DnDWrapper):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.TkdndVersion = TkinterDnD._require(self)

    _DND_AVAILABLE = True
except Exception:  # tkinterdnd2 not installed / failed to load
    _Root = ctk.CTk
    _DND_AVAILABLE = False


ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

MODE_2 = "Vocals + Instrumental"
MODE_4 = "4 stems"
MODE_6 = "6 stems"
FORMATS = ["wav", "mp3", "flac"]


class App(_Root):
    def __init__(self) -> None:
        super().__init__()
        self.title(f"RealGoodSplits {__version__}")
        self.geometry("860x680")
        self.minsize(760, 600)
        self._set_icon()

        self.files: list[Path] = []
        self.stem_vars: dict[str, ctk.BooleanVar] = {}
        self._queue: "queue.Queue[tuple]" = queue.Queue()
        self._worker: threading.Thread | None = None

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self._build_header()
        self._build_body()
        self._build_footer()
        self._refresh_stem_checkboxes()
        self._poll_queue()

    def _set_icon(self) -> None:
        """Set the window/taskbar icon; never fatal if assets are missing."""
        assets = Path(__file__).resolve().parent / "assets"
        try:
            import tkinter as tk

            png = assets / "icon.png"
            if png.exists():
                self._icon_img = tk.PhotoImage(file=str(png))  # keep a reference
                self.iconphoto(True, self._icon_img)
        except Exception:
            pass
        try:
            ico = assets / "icon.ico"  # Windows title bar / taskbar
            if ico.exists():
                self.iconbitmap(default=str(ico))
        except Exception:
            pass

    # ------------------------------------------------------------------ UI
    def _build_header(self) -> None:
        header = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=20, pady=(16, 4))
        ctk.CTkLabel(
            header, text="🎵  RealGoodSplits",
            font=ctk.CTkFont(size=24, weight="bold"),
        ).pack(side="left")
        ctk.CTkLabel(
            header, text="AI stem splitter · powered by Demucs",
            text_color=("gray40", "gray60"),
        ).pack(side="left", padx=12)

    def _build_body(self) -> None:
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.grid(row=1, column=0, sticky="nsew", padx=20, pady=8)
        body.grid_columnconfigure(0, weight=3)
        body.grid_columnconfigure(1, weight=2)
        body.grid_rowconfigure(0, weight=1)

        self._build_file_panel(body)
        self._build_settings_panel(body)

    def _build_file_panel(self, parent) -> None:
        panel = ctk.CTkFrame(parent)
        panel.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        panel.grid_rowconfigure(1, weight=1)
        panel.grid_columnconfigure(0, weight=1)

        bar = ctk.CTkFrame(panel, fg_color="transparent")
        bar.grid(row=0, column=0, sticky="ew", padx=10, pady=10)
        ctk.CTkButton(bar, text="+ Add files", width=90,
                      command=self._add_files).pack(side="left", padx=(0, 6))
        ctk.CTkButton(bar, text="+ Folder", width=80,
                      command=self._add_folder).pack(side="left", padx=6)
        ctk.CTkButton(bar, text="Clear", width=60, fg_color="transparent",
                      border_width=1, command=self._clear_files).pack(side="left", padx=6)

        hint = "Drag & drop audio here" if _DND_AVAILABLE else "Add audio files to begin"
        self.file_list = ctk.CTkScrollableFrame(panel, label_text=hint)
        self.file_list.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 10))
        self.file_list.grid_columnconfigure(0, weight=1)

        if _DND_AVAILABLE:
            self.file_list.drop_target_register(DND_FILES)
            self.file_list.dnd_bind("<<Drop>>", self._on_drop)

    def _build_settings_panel(self, parent) -> None:
        panel = ctk.CTkScrollableFrame(parent, label_text="Settings")
        panel.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        panel.grid_columnconfigure(0, weight=1)

        def section(text: str) -> None:
            ctk.CTkLabel(panel, text=text, anchor="w",
                         font=ctk.CTkFont(size=13, weight="bold")).pack(
                fill="x", padx=12, pady=(14, 2))

        # Model
        section("Model")
        self.model_var = ctk.StringVar(value="htdemucs")
        ctk.CTkOptionMenu(panel, variable=self.model_var, values=list(MODELS),
                          command=self._on_model_change).pack(fill="x", padx=12)
        self.model_desc = ctk.CTkLabel(
            panel, text=MODELS["htdemucs"], wraplength=240, justify="left",
            text_color=("gray40", "gray60"), font=ctk.CTkFont(size=11))
        self.model_desc.pack(fill="x", padx=12, pady=(4, 0))

        # Mode
        section("What to extract")
        self.mode_var = ctk.StringVar(value=MODE_4)
        ctk.CTkSegmentedButton(
            panel, values=[MODE_2, MODE_4, MODE_6], variable=self.mode_var,
            command=self._on_mode_change).pack(fill="x", padx=12)
        self.stem_frame = ctk.CTkFrame(panel, fg_color="transparent")
        self.stem_frame.pack(fill="x", padx=12, pady=(6, 0))

        # Output format
        section("Output format")
        self.format_var = ctk.StringVar(value="wav")
        ctk.CTkSegmentedButton(panel, values=FORMATS, variable=self.format_var,
                               command=lambda _=None: self._on_format_change()
                               ).pack(fill="x", padx=12)
        self.bitrate_row = ctk.CTkFrame(panel, fg_color="transparent")
        ctk.CTkLabel(self.bitrate_row, text="MP3 bitrate").pack(side="left")
        self.bitrate_var = ctk.StringVar(value="320")
        ctk.CTkOptionMenu(self.bitrate_row, variable=self.bitrate_var,
                          values=["128", "192", "256", "320"], width=90
                          ).pack(side="right")

        # Device
        section("Device")
        self.device_var = ctk.StringVar(value="auto")
        ctk.CTkOptionMenu(panel, variable=self.device_var,
                          values=["auto", "cpu", "cuda", "mps"]).pack(fill="x", padx=12)
        ctk.CTkLabel(panel, text=f"detected: {auto_device()}",
                     text_color=("gray40", "gray60"),
                     font=ctk.CTkFont(size=11)).pack(fill="x", padx=12, pady=(2, 0))

        # Output folder
        section("Save to")
        self.same_as_input = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(panel, text="Next to each source file",
                        variable=self.same_as_input,
                        command=self._on_output_toggle).pack(fill="x", padx=12)
        out_row = ctk.CTkFrame(panel, fg_color="transparent")
        out_row.pack(fill="x", padx=12, pady=(6, 0))
        self.output_var = ctk.StringVar(value="")
        self.output_entry = ctk.CTkEntry(out_row, textvariable=self.output_var,
                                         placeholder_text="choose a folder…")
        self.output_entry.pack(side="left", fill="x", expand=True)
        self.output_btn = ctk.CTkButton(out_row, text="…", width=36,
                                        command=self._choose_output)
        self.output_btn.pack(side="right", padx=(6, 0))
        self._on_output_toggle()
        self._on_format_change()

    def _build_footer(self) -> None:
        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.grid(row=2, column=0, sticky="ew", padx=20, pady=(4, 16))
        footer.grid_columnconfigure(0, weight=1)

        self.log = ctk.CTkTextbox(footer, height=110, activate_scrollbars=True)
        self.log.grid(row=0, column=0, columnspan=2, sticky="ew")
        self.log.configure(state="disabled")

        self.progress = ctk.CTkProgressBar(footer)
        self.progress.set(0)
        self.progress.grid(row=1, column=0, sticky="ew", pady=(10, 0), padx=(0, 12))

        self.status = ctk.CTkLabel(footer, text="Ready", anchor="w")
        self.status.grid(row=2, column=0, sticky="w", pady=(4, 0))

        self.run_btn = ctk.CTkButton(
            footer, text="Split Stems", width=160, height=44,
            font=ctk.CTkFont(size=15, weight="bold"), command=self._start)
        self.run_btn.grid(row=1, column=1, rowspan=2, sticky="e", pady=(10, 0))

    # -------------------------------------------------------------- actions
    def _add_files(self) -> None:
        paths = filedialog.askopenfilenames(
            title="Choose audio files",
            filetypes=[("Audio", "*.wav *.mp3 *.flac *.m4a *.aac *.ogg *.opus *.wma *.aif *.aiff"),
                       ("All files", "*.*")])
        self._add_paths(paths)

    def _add_folder(self) -> None:
        folder = filedialog.askdirectory(title="Choose a folder of audio")
        if folder:
            self._add_paths([folder])

    def _on_drop(self, event) -> None:
        # tkdnd returns a brace-wrapped, space-separated list of paths.
        paths = self.tk.splitlist(event.data)
        self._add_paths(paths)

    def _add_paths(self, paths) -> None:
        new = collect_audio_files(paths)
        existing = {p.resolve() for p in self.files}
        added = 0
        for f in new:
            if f.resolve() not in existing:
                self.files.append(f)
                existing.add(f.resolve())
                added += 1
        if added:
            self._render_file_list()

    def _clear_files(self) -> None:
        self.files.clear()
        self._render_file_list()

    def _remove_file(self, path: Path) -> None:
        self.files = [f for f in self.files if f != path]
        self._render_file_list()

    def _render_file_list(self) -> None:
        for child in self.file_list.winfo_children():
            child.destroy()
        for f in self.files:
            row = ctk.CTkFrame(self.file_list)
            row.pack(fill="x", pady=2)
            row.grid_columnconfigure(0, weight=1)
            ctk.CTkLabel(row, text=f.name, anchor="w").grid(
                row=0, column=0, sticky="ew", padx=(8, 4), pady=4)
            ctk.CTkButton(row, text="✕", width=28, fg_color="transparent",
                          hover_color=("gray80", "gray30"),
                          command=lambda p=f: self._remove_file(p)).grid(
                row=0, column=1, padx=4)
        self.status.configure(text=f"{len(self.files)} file(s) ready"
                              if self.files else "Ready")

    def _on_model_change(self, _value: str) -> None:
        self.model_desc.configure(text=MODELS[self.model_var.get()])
        # 6-stem models force 6-stem mode; others can't do 6 stems.
        if self.model_var.get() == "htdemucs_6s":
            self.mode_var.set(MODE_6)
        elif self.mode_var.get() == MODE_6:
            self.mode_var.set(MODE_4)
        self._refresh_stem_checkboxes()

    def _on_mode_change(self, _value: str) -> None:
        if self.mode_var.get() == MODE_6 and self.model_var.get() != "htdemucs_6s":
            self.model_var.set("htdemucs_6s")
            self.model_desc.configure(text=MODELS["htdemucs_6s"])
        self._refresh_stem_checkboxes()

    def _refresh_stem_checkboxes(self) -> None:
        for child in self.stem_frame.winfo_children():
            child.destroy()
        self.stem_vars.clear()
        if self.mode_var.get() == MODE_2:
            ctk.CTkLabel(self.stem_frame,
                         text="→ vocals.* and no_vocals.*",
                         text_color=("gray40", "gray60"),
                         font=ctk.CTkFont(size=11), anchor="w").pack(fill="x")
            return
        stems = MODEL_STEMS.get(self.model_var.get(), [])
        for stem in stems:
            var = ctk.BooleanVar(value=True)
            self.stem_vars[stem] = var
            ctk.CTkCheckBox(self.stem_frame, text=stem.capitalize(),
                            variable=var).pack(anchor="w", pady=1)

    def _on_format_change(self) -> None:
        if self.format_var.get() == "mp3":
            self.bitrate_row.pack(fill="x", padx=12, pady=(6, 0))
        else:
            self.bitrate_row.pack_forget()

    def _on_output_toggle(self) -> None:
        disabled = self.same_as_input.get()
        state = "disabled" if disabled else "normal"
        self.output_entry.configure(state=state)
        self.output_btn.configure(state=state)

    def _choose_output(self) -> None:
        folder = filedialog.askdirectory(title="Choose output folder")
        if folder:
            self.output_var.set(folder)

    # ------------------------------------------------------------- run loop
    def _start(self) -> None:
        if self._worker and self._worker.is_alive():
            return
        if not self.files:
            messagebox.showinfo("RealGoodSplits", "Add some audio files first.")
            return

        mode = self.mode_var.get()
        two_stems = mode == MODE_2
        stems = None
        if not two_stems:
            stems = [s for s, v in self.stem_vars.items() if v.get()]
            if not stems:
                messagebox.showinfo("RealGoodSplits", "Pick at least one stem.")
                return

        if not self.same_as_input.get() and not self.output_var.get():
            messagebox.showinfo("RealGoodSplits", "Choose an output folder "
                                "(or tick 'Next to each source file').")
            return

        device = self.device_var.get()
        device = auto_device() if device == "auto" else device

        cfg = dict(
            files=list(self.files),
            model=self.model_var.get(),
            device=device,
            two_stems=two_stems,
            stems=stems,
            fmt=self.format_var.get(),
            bitrate=int(self.bitrate_var.get()),
            same_as_input=self.same_as_input.get(),
            output=self.output_var.get(),
        )

        self.run_btn.configure(state="disabled", text="Working…")
        self.progress.set(0)
        self._log_clear()
        self._log(f"Starting · {cfg['model']} · {device}")

        self._worker = threading.Thread(target=self._work, args=(cfg,), daemon=True)
        self._worker.start()

    def _work(self, cfg: dict) -> None:
        """Runs on a background thread. Communicates via self._queue."""
        try:
            separator = StemSeparator(model_name=cfg["model"], device=cfg["device"])
            total = len(cfg["files"])
            for i, audio in enumerate(cfg["files"]):
                self._queue.put(("file_start", (i, total, audio.name)))
                out_dir = (audio.parent if cfg["same_as_input"]
                           else Path(cfg["output"]))
                separator.separate_file(
                    audio, out_dir,
                    stems=cfg["stems"], two_stems=cfg["two_stems"],
                    output_format=cfg["fmt"], mp3_bitrate=cfg["bitrate"],
                    log_cb=lambda line: self._queue.put(("log", line)),
                )
                self._queue.put(("file_done", (i + 1) / total))
            self._queue.put(("done", None))
        except Exception as exc:  # surfaced to the user on the main thread
            self._queue.put(("error", str(exc)))

    def _poll_queue(self) -> None:
        try:
            while True:
                kind, payload = self._queue.get_nowait()
                if kind == "file_start":
                    i, total, name = payload
                    self.status.configure(text=f"[{i+1}/{total}] Separating {name}…")
                    self._log(f"[{i+1}/{total}] {name}")
                    self.progress.configure(mode="indeterminate")
                    self.progress.start()  # animate while the model works
                elif kind == "file_done":
                    self.progress.stop()
                    self.progress.configure(mode="determinate")
                    self.progress.set(payload)
                elif kind == "log":
                    self._log(payload)
                elif kind == "done":
                    self._finish("Done ✓")
                elif kind == "error":
                    self._finish("Failed")
                    messagebox.showerror("RealGoodSplits", payload)
        except queue.Empty:
            pass
        self.after(100, self._poll_queue)

    def _finish(self, status: str) -> None:
        try:
            self.progress.stop()
        except Exception:
            pass
        self.progress.configure(mode="determinate")
        self.progress.set(1 if status.startswith("Done") else 0)
        self.status.configure(text=status)
        self.run_btn.configure(state="normal", text="Split Stems")

    # ----------------------------------------------------------------- log
    def _log(self, line: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", line + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _log_clear(self) -> None:
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")


def main() -> None:
    # Needed when frozen with PyInstaller (Demucs may spawn workers).
    import multiprocessing
    multiprocessing.freeze_support()
    App().mainloop()


if __name__ == "__main__":
    main()

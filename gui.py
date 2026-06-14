import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import asyncio
import threading
import sys
import os
from json import JSONDecodeError
from scraper import run_scraper, CATEGORIES, load_preset, save_preset

# Dark theme palette
BG = "#16191d"
SURFACE = "#21252b"
FIELD = "#2b313a"
BORDER = "#3a414c"
TEXT = "#d7dce2"
MUTED = "#8b94a1"
ACCENT = "#4f9cf9"
ACCENT_ACTIVE = "#3b86e0"
SUCCESS = "#53d28c"
WARNING = "#e5c07b"
ERROR = "#e06c75"
SELECT_BG = "#345a8a"
BUTTON_BG = "#2e3440"
BUTTON_ACTIVE = "#3a414c"

# Log line prefixes mapped to text tags, checked in order
LOG_TAG_RULES = (
    ("header", ("--- Processing", "####", "Location:")),
    ("success", ("Saved ", "All searches completed")),
    ("warn", ("Warning", "Skipping", "Timed out")),
    ("error", ("Error", "Stopping")),
)

STATUS_STYLES = {
    "idle": ("● Idle", MUTED),
    "running": ("● Running", SUCCESS),
    "stopping": ("● Stopping…", WARNING),
    "done": ("● Done", ACCENT),
    "stopped": ("● Stopped", ERROR),
}

class StreamToQueue:
    def __init__(self, text_widget, tag=None):
        self.text_widget = text_widget
        self.tag = tag

    def write(self, str):
        try:
            self.text_widget.after(0, self._insert_text, str)
        except tk.TclError:
            pass

    def _classify(self, line):
        stripped = line.lstrip()
        for tag, prefixes in LOG_TAG_RULES:
            if stripped.startswith(prefixes):
                return tag
        return None

    def _insert_text(self, str):
        try:
            self.text_widget.configure(state="normal")
            for line in str.splitlines(keepends=True):
                tag = self.tag or self._classify(line)
                self.text_widget.insert(tk.END, line, tag or ())
            self.text_widget.see(tk.END)
            self.text_widget.configure(state="disabled")
        except tk.TclError:
            pass

    def flush(self):
        pass

class ScraperGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Google Maps Lead Generator")
        self.root.geometry("1100x720")
        self.root.minsize(900, 600)

        self._init_style()

        self.stop_requested = False
        self._restart_after_stop = False
        self._closed = False
        self._scraper_thread = None
        self.create_widgets()

        # Redirect stdout and stderr to the GUI log area; restore on close
        self._original_stdout = sys.stdout
        self._original_stderr = sys.stderr
        sys.stdout = StreamToQueue(self.log_area)
        sys.stderr = StreamToQueue(self.log_area, tag="error")
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def _init_style(self):
        self.root.configure(bg=BG)
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure(
            ".",
            background=SURFACE,
            foreground=TEXT,
            bordercolor=BORDER,
            darkcolor=SURFACE,
            lightcolor=SURFACE,
            troughcolor=BG,
            focuscolor=ACCENT,
            selectbackground=SELECT_BG,
            selectforeground=TEXT,
            fieldbackground=FIELD,
            font=("Segoe UI", 10),
        )
        style.configure("TFrame", background=SURFACE)
        style.configure("Background.TFrame", background=BG)
        style.configure("TLabel", background=SURFACE, foreground=TEXT)
        style.configure("Hint.TLabel", foreground=MUTED, font=("Segoe UI", 8))
        style.configure("Status.TLabel", font=("Segoe UI", 10, "bold"))
        style.configure("Muted.TLabel", foreground=MUTED)
        style.configure("TLabelframe", background=SURFACE, bordercolor=BORDER)
        style.configure("TLabelframe.Label", background=SURFACE, foreground=MUTED, font=("Segoe UI", 9, "bold"))
        style.configure("TButton", background=BUTTON_BG, foreground=TEXT, padding=(10, 6), bordercolor=BORDER)
        style.map(
            "TButton",
            background=[("disabled", SURFACE), ("pressed", BORDER), ("active", BUTTON_ACTIVE)],
            foreground=[("disabled", MUTED)],
        )
        style.configure("Accent.TButton", background=ACCENT, foreground="#ffffff")
        style.map(
            "Accent.TButton",
            background=[("disabled", SURFACE), ("pressed", ACCENT_ACTIVE), ("active", ACCENT_ACTIVE)],
            foreground=[("disabled", MUTED)],
        )
        style.configure("TEntry", fieldbackground=FIELD, foreground=TEXT, insertcolor=TEXT, bordercolor=BORDER)
        style.map("TEntry", fieldbackground=[("disabled", SURFACE)], foreground=[("disabled", MUTED)])
        style.configure("TSpinbox", fieldbackground=FIELD, foreground=TEXT, insertcolor=TEXT, bordercolor=BORDER, arrowcolor=TEXT, background=FIELD)
        style.map("TSpinbox", fieldbackground=[("disabled", SURFACE)], foreground=[("disabled", MUTED)])
        style.configure("TCheckbutton", background=SURFACE, foreground=TEXT, indicatorbackground=FIELD, indicatorforeground=TEXT)
        style.map("TCheckbutton", background=[("active", SURFACE)], indicatorbackground=[("selected", ACCENT)])
        for orient in ("Vertical", "Horizontal"):
            style.configure(f"{orient}.TScrollbar", background=BORDER, troughcolor=BG, arrowcolor=TEXT, bordercolor=SURFACE)
            style.map(f"{orient}.TScrollbar", background=[("active", "#4a5260")])
        style.configure("Horizontal.TProgressbar", background=ACCENT, lightcolor=ACCENT, darkcolor=ACCENT, troughcolor=FIELD, bordercolor=BORDER)

    def on_close(self):
        self._closed = True
        self.stop_requested = True
        sys.stdout = self._original_stdout
        sys.stderr = self._original_stderr
        self.root.destroy()

    def create_widgets(self):
        self.root.columnconfigure(1, weight=1)
        self.root.rowconfigure(1, weight=1)
        self._build_toolbar()
        self._build_sidebar()
        self._build_log_panel()
        self._build_status_bar()

    def _build_toolbar(self):
        bar = ttk.Frame(self.root, padding=(12, 10))
        bar.grid(row=0, column=0, columnspan=2, sticky="ew")

        self.start_btn = ttk.Button(bar, text="Start Scraping", style="Accent.TButton", command=self.start_scraping)
        self.start_btn.pack(side=tk.LEFT)
        self.stop_btn = ttk.Button(bar, text="Stop", command=self.stop_scraping, state=tk.DISABLED)
        self.stop_btn.pack(side=tk.LEFT, padx=(8, 0))
        self.restart_btn = ttk.Button(bar, text="Save & Restart", command=self.save_and_restart, state=tk.DISABLED)
        self.restart_btn.pack(side=tk.LEFT, padx=(8, 0))

        ttk.Button(bar, text="Save Preset", command=self.save_preset_file).pack(side=tk.RIGHT)
        ttk.Button(bar, text="Load Preset", command=self.load_preset_file).pack(side=tk.RIGHT, padx=(0, 8))

    def _build_sidebar(self):
        sidebar = ttk.Frame(self.root, style="Background.TFrame", padding=(12, 0, 6, 8))
        sidebar.grid(row=1, column=0, sticky="nsew")
        sidebar.columnconfigure(0, weight=1)
        sidebar.rowconfigure(2, weight=1)

        # Location
        loc_frame = ttk.LabelFrame(sidebar, text="Location", padding=8)
        loc_frame.grid(row=0, column=0, sticky="ew")
        loc_frame.columnconfigure(0, weight=1)

        ttk.Label(loc_frame, text="Single location (e.g., Toledo, Ohio)").grid(row=0, column=0, columnspan=2, sticky="w")
        self.location_var = tk.StringVar()
        ttk.Entry(loc_frame, textvariable=self.location_var).grid(row=1, column=0, columnspan=2, sticky="ew", pady=(2, 6))

        ttk.Label(loc_frame, text="OR locations file").grid(row=2, column=0, columnspan=2, sticky="w")
        self.file_var = tk.StringVar()
        ttk.Entry(loc_frame, textvariable=self.file_var).grid(row=3, column=0, sticky="ew", pady=(2, 0))
        ttk.Button(loc_frame, text="Browse", command=self.browse_file).grid(row=3, column=1, sticky="e", padx=(6, 0), pady=(2, 0))

        # Run Settings
        settings_frame = ttk.LabelFrame(sidebar, text="Run Settings", padding=8)
        settings_frame.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        settings_frame.columnconfigure(1, weight=1)

        ttk.Label(settings_frame, text="Limit per category").grid(row=0, column=0, sticky="w")
        self.limit_var = tk.IntVar(value=20)
        ttk.Spinbox(settings_frame, from_=1, to=1000, textvariable=self.limit_var, width=8).grid(row=0, column=1, sticky="w", padx=(6, 0), pady=2)

        ttk.Label(settings_frame, text="Concurrency").grid(row=1, column=0, sticky="w")
        self.concurrency_var = tk.IntVar(value=1)
        ttk.Spinbox(settings_frame, from_=1, to=5, textvariable=self.concurrency_var, width=8).grid(row=1, column=1, sticky="w", padx=(6, 0), pady=2)

        ttk.Label(settings_frame, text="Output filename").grid(row=2, column=0, sticky="w")
        self.output_file_var = tk.StringVar()
        ttk.Entry(settings_frame, textvariable=self.output_file_var).grid(row=2, column=1, columnspan=2, sticky="ew", padx=(6, 0), pady=2)
        ttk.Label(settings_frame, text="Leave blank for a timestamped file", style="Hint.TLabel").grid(row=3, column=1, columnspan=2, sticky="w", padx=(6, 0))

        ttk.Label(settings_frame, text="Output directory").grid(row=4, column=0, sticky="w")
        self.output_dir_var = tk.StringVar(value=".")
        ttk.Entry(settings_frame, textvariable=self.output_dir_var).grid(row=4, column=1, sticky="ew", padx=(6, 0), pady=2)
        ttk.Button(settings_frame, text="Browse", command=self.browse_output_dir).grid(row=4, column=2, padx=(6, 0), pady=2)

        self.dry_run_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(settings_frame, text="Dry run (no CSV/progress files)", variable=self.dry_run_var).grid(row=5, column=0, columnspan=3, sticky="w", pady=(6, 0))
        self.call_sheet_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(settings_frame, text="Create call sheet", variable=self.call_sheet_var).grid(row=6, column=0, columnspan=3, sticky="w")

        ttk.Label(settings_frame, text="Sources").grid(row=7, column=0, sticky="w", pady=(6, 0))
        source_frame = ttk.Frame(settings_frame)
        source_frame.grid(row=7, column=1, columnspan=2, sticky="w", padx=(6, 0), pady=(6, 0))
        self.google_source_var = tk.BooleanVar(value=True)
        self.yelp_source_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(source_frame, text="Google Maps", variable=self.google_source_var).pack(side=tk.LEFT)
        ttk.Checkbutton(source_frame, text="Yelp", variable=self.yelp_source_var).pack(side=tk.LEFT, padx=(10, 0))

        # Categories
        cat_frame = ttk.LabelFrame(sidebar, text="Categories", padding=8)
        cat_frame.grid(row=2, column=0, sticky="nsew", pady=(8, 0))
        cat_frame.columnconfigure(0, weight=1)
        cat_frame.rowconfigure(0, weight=1)

        self.cat_listbox = tk.Listbox(
            cat_frame, selectmode=tk.SINGLE, font=("Consolas", 9), activestyle="none",
            bg=FIELD, fg=TEXT, selectbackground=SELECT_BG, selectforeground=TEXT,
            highlightthickness=1, highlightbackground=BORDER, highlightcolor=ACCENT,
            relief="flat", borderwidth=0,
        )
        self.cat_listbox.grid(row=0, column=0, sticky="nsew")
        cat_scroll = ttk.Scrollbar(cat_frame, orient=tk.VERTICAL, command=self.cat_listbox.yview)
        cat_scroll.grid(row=0, column=1, sticky="ns")
        self.cat_listbox.configure(yscrollcommand=cat_scroll.set)
        for cat in CATEGORIES:
            self.cat_listbox.insert(tk.END, cat)

        self.new_cat_var = tk.StringVar()
        ttk.Entry(cat_frame, textvariable=self.new_cat_var).grid(row=1, column=0, columnspan=2, sticky="ew", pady=(6, 0))

        cat_btns = ttk.Frame(cat_frame)
        cat_btns.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        ttk.Button(cat_btns, text="Add", command=self.add_category).pack(side=tk.LEFT)
        ttk.Button(cat_btns, text="Remove Selected", command=self.remove_category).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Button(cat_btns, text="Reset to Default", command=self.reset_categories).pack(side=tk.LEFT, padx=(6, 0))

    def _build_log_panel(self):
        panel = ttk.LabelFrame(self.root, text="Activity Log", padding=8)
        panel.grid(row=1, column=1, sticky="nsew", padx=(6, 12), pady=(0, 8))
        panel.columnconfigure(0, weight=1)
        panel.rowconfigure(1, weight=1)

        header = ttk.Frame(panel)
        header.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 6))
        ttk.Button(header, text="Clear Logs", command=self.clear_logs).pack(side=tk.RIGHT)

        self.log_area = tk.Text(
            panel, font=("Consolas", 9), wrap="word", state="disabled",
            bg=FIELD, fg=TEXT, insertbackground=TEXT,
            selectbackground=SELECT_BG, selectforeground=TEXT,
            highlightthickness=1, highlightbackground=BORDER, highlightcolor=ACCENT,
            relief="flat", borderwidth=0,
        )
        self.log_area.grid(row=1, column=0, sticky="nsew")
        log_scroll = ttk.Scrollbar(panel, orient=tk.VERTICAL, command=self.log_area.yview)
        log_scroll.grid(row=1, column=1, sticky="ns")
        self.log_area.configure(yscrollcommand=log_scroll.set)

        self.log_area.tag_configure("header", foreground=ACCENT, font=("Consolas", 9, "bold"))
        self.log_area.tag_configure("success", foreground=SUCCESS)
        self.log_area.tag_configure("warn", foreground=WARNING)
        self.log_area.tag_configure("error", foreground=ERROR)

    def _build_status_bar(self):
        bar = ttk.Frame(self.root, padding=(12, 8))
        bar.grid(row=2, column=0, columnspan=2, sticky="ew")
        bar.columnconfigure(1, weight=1)

        self.status_label = ttk.Label(bar, text="", style="Status.TLabel")
        self.status_label.grid(row=0, column=0, sticky="w")
        self.task_label = ttk.Label(bar, text="", style="Muted.TLabel")
        self.task_label.grid(row=0, column=1, sticky="w", padx=(12, 0))
        self.progress_bar = ttk.Progressbar(bar, orient="horizontal", mode="determinate", length=220)
        self.progress_bar.grid(row=0, column=2, sticky="e")
        self.progress_count_label = ttk.Label(bar, text="")
        self.progress_count_label.grid(row=0, column=3, sticky="e", padx=(8, 0))

        self.set_status("idle")

    def set_status(self, state):
        text, color = STATUS_STYLES[state]
        self.status_label.config(text=text, foreground=color)

    def _on_progress_event(self, event):
        if self._closed:
            return
        try:
            self.root.after(0, self._apply_progress, event)
        except (tk.TclError, RuntimeError):
            pass

    def _apply_progress(self, event):
        if self._closed:
            return
        total = event.get("total") or 0
        done = event.get("done") or 0
        if total:
            self.progress_bar.config(maximum=total, value=min(done, total))
            self.progress_count_label.config(text=f"{done}/{total} categories")
        name = event.get("event")
        if name == "category_start":
            self.task_label.config(text=f"{event.get('source', '')}: {event.get('category', '')} — {event.get('location', '')}")
        elif name == "run_end":
            self.task_label.config(text="")

    def add_category(self):
        cat = self.new_cat_var.get().strip()
        if not cat:
            return
        existing = list(self.cat_listbox.get(0, tk.END))
        if cat.lower() in [c.lower() for c in existing]:
            messagebox.showwarning("Duplicate", f"'{cat}' is already in the list.")
            return
        self.cat_listbox.insert(tk.END, cat)
        self.new_cat_var.set("")

    def remove_category(self):
        sel = self.cat_listbox.curselection()
        if sel:
            self.cat_listbox.delete(sel[0])

    def reset_categories(self):
        self.cat_listbox.delete(0, tk.END)
        for cat in CATEGORIES:
            self.cat_listbox.insert(tk.END, cat)

    def browse_file(self):
        filename = filedialog.askopenfilename(filetypes=[("Text files", "*.txt"), ("All files", "*.*")])
        if filename:
            self.file_var.set(filename)

    def browse_output_dir(self):
        directory = filedialog.askdirectory()
        if directory:
            self.output_dir_var.set(directory)

    def clear_logs(self):
        self.log_area.configure(state="normal")
        self.log_area.delete(1.0, tk.END)
        self.log_area.configure(state="disabled")

    def get_categories(self):
        return list(self.cat_listbox.get(0, tk.END))

    def apply_categories(self, categories):
        self.cat_listbox.delete(0, tk.END)
        for cat in categories:
            cat = str(cat).strip()
            if cat:
                self.cat_listbox.insert(tk.END, cat)

    def get_preset_config(self):
        return {
            "location": self.location_var.get().strip(),
            "file": self.file_var.get().strip(),
            "limit": self.limit_var.get(),
            "concurrency": self.concurrency_var.get(),
            "output_file": self.output_file_var.get().strip() or None,
            "output_dir": self.output_dir_var.get().strip() or ".",
            "categories": self.get_categories(),
            "dry_run": self.dry_run_var.get(),
            "call_sheet": self.call_sheet_var.get(),
            "sources": self.get_sources(),
        }

    def load_preset_file(self):
        filename = filedialog.askopenfilename(filetypes=[("JSON files", "*.json"), ("All files", "*.*")])
        if not filename:
            return
        try:
            preset = load_preset(filename)
            locations = preset.get("locations") or []
            self.location_var.set(preset.get("location") or (locations[0] if locations else ""))
            self.file_var.set(preset.get("file") or "")
            self.limit_var.set(int(preset.get("limit", self.limit_var.get())))
            self.concurrency_var.set(int(preset.get("concurrency", self.concurrency_var.get())))
            self.output_file_var.set(preset.get("output_file") or "")
            self.output_dir_var.set(preset.get("output_dir") or ".")
            self.dry_run_var.set(bool(preset.get("dry_run", False)))
            self.call_sheet_var.set(bool(preset.get("call_sheet", False)))
            sources = preset.get("sources") or ["google"]
            self.google_source_var.set("google" in sources)
            self.yelp_source_var.set("yelp" in sources)
            if preset.get("categories"):
                self.apply_categories(preset["categories"])
            elif preset.get("categories_file"):
                with open(preset["categories_file"], "r") as f:
                    self.apply_categories([line.strip() for line in f if line.strip() and not line.strip().startswith("#")])
            print(f"\nLoaded preset: {filename}")
        except (OSError, JSONDecodeError, ValueError, TypeError) as e:
            messagebox.showerror("Error", f"Could not load preset: {e}")

    def save_preset_file(self):
        filename = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON files", "*.json"), ("All files", "*.*")])
        if not filename:
            return
        try:
            save_preset(filename, self.get_preset_config())
            print(f"\nSaved preset: {filename}")
        except (OSError, ValueError, TypeError) as e:
            messagebox.showerror("Error", f"Could not save preset: {e}")

    def stop_scraping(self):
        self.stop_requested = True
        self.stop_btn.config(state=tk.DISABLED)
        self.restart_btn.config(state=tk.DISABLED)
        self.set_status("stopping")
        print("\nStopping... please wait for the current category to finish.")

    def save_and_restart(self):
        """Stop the current run (progress is saved) then automatically restart."""
        self._restart_after_stop = True
        self.stop_requested = True
        self.stop_btn.config(state=tk.DISABLED)
        self.restart_btn.config(state=tk.DISABLED)
        self.set_status("stopping")
        print("\nSaving progress and restarting... please wait for the current category to finish.")

    def start_scraping(self):
        location = self.location_var.get().strip()
        file_path = self.file_var.get().strip()
        try:
            limit = self.limit_var.get()
            concurrency = self.concurrency_var.get()
        except tk.TclError:
            messagebox.showerror("Error", "Limit and concurrency must be whole numbers.")
            return

        if limit < 1:
            messagebox.showerror("Error", "Limit per category must be at least 1.")
            return
        if concurrency < 1:
            messagebox.showerror("Error", "Concurrency must be at least 1.")
            return

        output_file = self.output_file_var.get().strip() or None
        output_dir = self.output_dir_var.get().strip() or "."
        dry_run = self.dry_run_var.get()
        call_sheet = self.call_sheet_var.get()
        sources = self.get_sources()
        if not sources:
            messagebox.showerror("Error", "Please select at least one source.")
            return

        locations = []
        if file_path:
            if os.path.exists(file_path):
                with open(file_path, 'r') as f:
                    locations = [line.strip() for line in f if line.strip()]
            else:
                messagebox.showerror("Error", "Location file not found.")
                return
        elif location:
            locations = [location]
        else:
            messagebox.showerror("Error", "Please provide a location or a file.")
            return

        categories = self.get_categories()
        if not categories:
            messagebox.showerror("Error", "Please add at least one category.")
            return

        self.stop_requested = False
        self._restart_after_stop = False
        self.start_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)
        self.restart_btn.config(state=tk.NORMAL)
        self.set_status("running")
        self.task_label.config(text="")
        self.progress_bar.config(value=0, maximum=1)
        self.progress_count_label.config(text="")
        self._scraper_thread = threading.Thread(target=self.run_async_task, args=(locations, limit, concurrency, categories, output_file, output_dir, dry_run, call_sheet, sources), daemon=True)
        self._scraper_thread.start()

    def get_sources(self):
        sources = []
        if self.google_source_var.get():
            sources.append("google")
        if self.yelp_source_var.get():
            sources.append("yelp")
        return sources

    def run_async_task(self, locations, limit, concurrency, categories, output_file, output_dir, dry_run, call_sheet, sources):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(run_scraper(locations, limit, output_dir, concurrency, stop_check=lambda: self.stop_requested, categories=categories, output_file=output_file, dry_run=dry_run, call_sheet=call_sheet, sources=sources, progress_callback=self._on_progress_event))
        except Exception as e:
            print(f"\nError occurred: {e}")
        finally:
            loop.close()
            if not self._closed:
                try:
                    self.root.after(0, self.on_scraping_finished)
                except tk.TclError:
                    pass

    def on_scraping_finished(self):
        if self._closed:
            return
        self.start_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)
        self.restart_btn.config(state=tk.DISABLED)
        self.task_label.config(text="")
        if getattr(self, '_restart_after_stop', False):
            self._restart_after_stop = False
            print("\nRestarting scraper...")
            self.start_scraping()
        else:
            if self.stop_requested:
                self.set_status("stopped")
                messagebox.showinfo("Finished", "Scraping task stopped.")
            else:
                self.set_status("done")
                messagebox.showinfo("Finished", "Scraping task completed.")

if __name__ == "__main__":
    root = tk.Tk()
    app = ScraperGUI(root)
    root.mainloop()

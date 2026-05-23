import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import asyncio
import threading
import sys
import os
from json import JSONDecodeError
from scraper import run_scraper, CATEGORIES, load_preset, save_preset

class StreamToQueue:
    def __init__(self, text_widget):
        self.text_widget = text_widget

    def write(self, str):
        try:
            self.text_widget.after(0, self._insert_text, str)
        except tk.TclError:
            pass

    def _insert_text(self, str):
        try:
            self.text_widget.insert(tk.END, str)
            self.text_widget.see(tk.END)
        except tk.TclError:
            pass

    def flush(self):
        pass

class ScraperGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Google Maps Lead Generator")
        self.root.geometry("760x680")
        
        # Style
        style = ttk.Style()
        style.configure("TButton", padding=6)
        style.configure("TLabel", font=("Segoe UI", 10))
        
        self.stop_requested = False
        self._restart_after_stop = False
        self._closed = False
        self._scraper_thread = None
        self.create_widgets()

        # Redirect stdout and stderr to the GUI log area; restore on close
        self._original_stdout = sys.stdout
        self._original_stderr = sys.stderr
        stream = StreamToQueue(self.log_area)
        sys.stdout = stream
        sys.stderr = stream
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def on_close(self):
        self._closed = True
        self.stop_requested = True
        sys.stdout = self._original_stdout
        sys.stderr = self._original_stderr
        self.root.destroy()

    def create_widgets(self):
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Location Input
        loc_frame = ttk.LabelFrame(main_frame, text="Location Settings", padding="10")
        loc_frame.pack(fill=tk.X, pady=5)

        ttk.Label(loc_frame, text="Single Location (e.g., Toledo, Ohio):").grid(row=0, column=0, sticky=tk.W)
        self.location_var = tk.StringVar()
        ttk.Entry(loc_frame, textvariable=self.location_var, width=50).grid(row=0, column=1, padx=5, pady=5)

        ttk.Label(loc_frame, text="OR Location File:").grid(row=1, column=0, sticky=tk.W)
        self.file_var = tk.StringVar()
        ttk.Entry(loc_frame, textvariable=self.file_var, width=40).grid(row=1, column=1, padx=5, pady=5, sticky=tk.W)
        ttk.Button(loc_frame, text="Browse", command=self.browse_file).grid(row=1, column=1, sticky=tk.E)

        # Scraper Settings
        settings_frame = ttk.LabelFrame(main_frame, text="Scraper Settings", padding="10")
        settings_frame.pack(fill=tk.X, pady=5)

        ttk.Label(settings_frame, text="Limit per Category:").grid(row=0, column=0, sticky=tk.W)
        self.limit_var = tk.IntVar(value=20)
        ttk.Spinbox(settings_frame, from_=1, to=1000, textvariable=self.limit_var, width=10).grid(row=0, column=1, padx=5, pady=5, sticky=tk.W)

        ttk.Label(settings_frame, text="Concurrency:").grid(row=1, column=0, sticky=tk.W)
        self.concurrency_var = tk.IntVar(value=1)
        ttk.Spinbox(settings_frame, from_=1, to=5, textvariable=self.concurrency_var, width=10).grid(row=1, column=1, padx=5, pady=5, sticky=tk.W)

        ttk.Label(settings_frame, text="Output Filename:").grid(row=2, column=0, sticky=tk.W)
        self.output_file_var = tk.StringVar()
        ttk.Entry(settings_frame, textvariable=self.output_file_var, width=40).grid(row=2, column=1, padx=5, pady=5, sticky=tk.W)
        ttk.Label(settings_frame, text="(leave blank for timestamped file)", font=("Segoe UI", 8)).grid(row=2, column=2, sticky=tk.W)

        ttk.Label(settings_frame, text="Output Directory:").grid(row=3, column=0, sticky=tk.W)
        self.output_dir_var = tk.StringVar(value=".")
        ttk.Entry(settings_frame, textvariable=self.output_dir_var, width=40).grid(row=3, column=1, padx=5, pady=5, sticky=tk.W)
        ttk.Button(settings_frame, text="Browse", command=self.browse_output_dir).grid(row=3, column=2, sticky=tk.W)

        self.dry_run_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(settings_frame, text="Dry run (do not write CSV/progress)", variable=self.dry_run_var).grid(row=4, column=1, padx=5, pady=5, sticky=tk.W)

        self.call_sheet_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(settings_frame, text="Create call sheet", variable=self.call_sheet_var).grid(row=5, column=1, padx=5, pady=5, sticky=tk.W)

        ttk.Label(settings_frame, text="Sources:").grid(row=6, column=0, sticky=tk.W)
        source_frame = ttk.Frame(settings_frame)
        source_frame.grid(row=6, column=1, padx=5, pady=5, sticky=tk.W)
        self.google_source_var = tk.BooleanVar(value=True)
        self.yelp_source_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(source_frame, text="Google Maps", variable=self.google_source_var).pack(side=tk.LEFT)
        ttk.Checkbutton(source_frame, text="Yelp", variable=self.yelp_source_var).pack(side=tk.LEFT, padx=(10, 0))

        # Categories Editor
        cat_frame = ttk.LabelFrame(main_frame, text="Categories", padding="10")
        cat_frame.pack(fill=tk.X, pady=5)

        list_frame = ttk.Frame(cat_frame)
        list_frame.pack(fill=tk.X)

        self.cat_listbox = tk.Listbox(list_frame, height=6, selectmode=tk.SINGLE, font=("Consolas", 9))
        self.cat_listbox.pack(side=tk.LEFT, fill=tk.X, expand=True)
        cat_scroll = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.cat_listbox.yview)
        cat_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.cat_listbox.configure(yscrollcommand=cat_scroll.set)
        for cat in CATEGORIES:
            self.cat_listbox.insert(tk.END, cat)

        entry_frame = ttk.Frame(cat_frame)
        entry_frame.pack(fill=tk.X, pady=(5, 0))

        self.new_cat_var = tk.StringVar()
        ttk.Entry(entry_frame, textvariable=self.new_cat_var, width=40).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(entry_frame, text="Add", command=self.add_category).pack(side=tk.LEFT, padx=2)
        ttk.Button(entry_frame, text="Remove Selected", command=self.remove_category).pack(side=tk.LEFT, padx=2)
        ttk.Button(entry_frame, text="Reset to Default", command=self.reset_categories).pack(side=tk.LEFT, padx=2)

        # Controls
        ctrl_frame = ttk.Frame(main_frame)
        ctrl_frame.pack(fill=tk.X, pady=10)

        self.start_btn = ttk.Button(ctrl_frame, text="Start Scraping", command=self.start_scraping)
        self.start_btn.pack(side=tk.LEFT, padx=5)

        self.stop_btn = ttk.Button(ctrl_frame, text="Stop", command=self.stop_scraping, state=tk.DISABLED)
        self.stop_btn.pack(side=tk.LEFT, padx=5)

        self.restart_btn = ttk.Button(ctrl_frame, text="Save & Restart", command=self.save_and_restart, state=tk.DISABLED)
        self.restart_btn.pack(side=tk.LEFT, padx=5)

        ttk.Button(ctrl_frame, text="Load Preset", command=self.load_preset_file).pack(side=tk.LEFT, padx=5)
        ttk.Button(ctrl_frame, text="Save Preset", command=self.save_preset_file).pack(side=tk.LEFT, padx=5)
        ttk.Button(ctrl_frame, text="Clear Logs", command=self.clear_logs).pack(side=tk.LEFT, padx=5)
        
        # Log Area
        log_frame = ttk.LabelFrame(main_frame, text="Logs", padding="5")
        log_frame.pack(fill=tk.BOTH, expand=True)

        self.log_area = tk.Text(log_frame, height=15, font=("Consolas", 9))
        self.log_area.pack(fill=tk.BOTH, expand=True)
        
        scrollbar = ttk.Scrollbar(self.log_area, orient=tk.VERTICAL, command=self.log_area.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_area.configure(yscrollcommand=scrollbar.set)

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
        self.log_area.delete(1.0, tk.END)

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
        print("\nStopping... please wait for the current category to finish.")

    def save_and_restart(self):
        """Stop the current run (progress is saved) then automatically restart."""
        self._restart_after_stop = True
        self.stop_requested = True
        self.stop_btn.config(state=tk.DISABLED)
        self.restart_btn.config(state=tk.DISABLED)
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
            loop.run_until_complete(run_scraper(locations, limit, output_dir, concurrency, stop_check=lambda: self.stop_requested, categories=categories, output_file=output_file, dry_run=dry_run, call_sheet=call_sheet, sources=sources))
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
        if getattr(self, '_restart_after_stop', False):
            self._restart_after_stop = False
            print("\nRestarting scraper...")
            self.start_scraping()
        else:
            msg = "Scraping task stopped." if self.stop_requested else "Scraping task completed."
            messagebox.showinfo("Finished", msg)

if __name__ == "__main__":
    root = tk.Tk()
    app = ScraperGUI(root)
    root.mainloop()

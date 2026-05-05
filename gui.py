import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import asyncio
import threading
import sys
import os
from scraper import run_scraper, CATEGORIES

class StreamToQueue:
    def __init__(self, text_widget):
        self.text_widget = text_widget

    def write(self, str):
        self.text_widget.after(0, self._insert_text, str)

    def _insert_text(self, str):
        self.text_widget.insert(tk.END, str)
        self.text_widget.see(tk.END)

    def flush(self):
        pass

class ScraperGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Google Maps Lead Generator")
        self.root.geometry("700x600")
        
        # Style
        style = ttk.Style()
        style.configure("TButton", padding=6)
        style.configure("TLabel", font=("Segoe UI", 10))
        
        self.stop_requested = False
        self.create_widgets()
        
        # Redirect stdout
        sys.stdout = StreamToQueue(self.log_area)

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

    def clear_logs(self):
        self.log_area.delete(1.0, tk.END)

    def stop_scraping(self):
        self.stop_requested = True
        self.stop_btn.config(state=tk.DISABLED)
        print("\nStopping... please wait for the current category to finish.")

    def start_scraping(self):
        location = self.location_var.get().strip()
        file_path = self.file_var.get().strip()
        limit = self.limit_var.get()
        concurrency = self.concurrency_var.get()

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

        categories = list(self.cat_listbox.get(0, tk.END))
        if not categories:
            messagebox.showerror("Error", "Please add at least one category.")
            return

        self.stop_requested = False
        self.start_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)
        thread = threading.Thread(target=self.run_async_task, args=(locations, limit, concurrency, categories), daemon=True)
        thread.start()

    def run_async_task(self, locations, limit, concurrency, categories):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(run_scraper(locations, limit, ".", concurrency, stop_check=lambda: self.stop_requested, categories=categories))
        except Exception as e:
            print(f"\nError occurred: {e}")
        finally:
            loop.close()
            self.root.after(0, self.on_scraping_finished)

    def on_scraping_finished(self):
        self.start_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)
        msg = "Scraping task stopped." if self.stop_requested else "Scraping task completed."
        messagebox.showinfo("Finished", msg)

if __name__ == "__main__":
    root = tk.Tk()
    app = ScraperGUI(root)
    root.mainloop()

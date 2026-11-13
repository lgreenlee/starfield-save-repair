"""Offline Windows desktop interface for the existing targeted repair engine."""
from datetime import datetime
import os
from pathlib import Path
import queue
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk

from . import __version__
from .application import create_repaired_slot, inspect_save, latest_save
from .windows import default_save_directory


class RepairWindow:
    def __init__(self, root, initial=None):
        self.root, self.busy, self.report, self.completed = root, False, None, None
        self.events = queue.Queue()
        self.source = tk.StringVar()
        self.subtitle = tk.StringVar(value="Choose a save, then check whether the Anchorpoint position repair applies.")
        root.title("Starfield Save Repair")
        root.geometry("920x670")
        root.minsize(780, 580)
        root.protocol("WM_DELETE_WINDOW", self.close)
        style = ttk.Style(root)
        if "vista" in style.theme_names():
            style.theme_use("vista")
        frame = ttk.Frame(root, padding=24)
        frame.grid(sticky="nsew")
        root.columnconfigure(0, weight=1)
        root.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(5, weight=1)
        ttk.Label(frame, text="Starfield Save Repair", font=("Segoe UI", 22, "bold")).grid(sticky="w")
        ttk.Label(frame, text="Anchorpoint position repair  •  " + __version__, font=("Segoe UI", 11)).grid(sticky="w", pady=(4, 18))
        ttk.Label(frame, text="Creates a separate save slot and keeps a verified original backup.",
                  font=("Segoe UI", 11)).grid(sticky="w", pady=(0, 14))

        selection = ttk.LabelFrame(frame, text="1. Choose your save", padding=12)
        selection.grid(row=3, sticky="ew")
        selection.columnconfigure(0, weight=1)
        ttk.Entry(selection, textvariable=self.source, state="readonly").grid(row=0, column=0, sticky="ew", padx=(0, 10))
        self.browse_button = ttk.Button(selection, text="Browse…", command=self.browse)
        self.browse_button.grid(row=0, column=1)
        self.latest_button = ttk.Button(selection, text="Use latest save", command=self.use_latest)
        self.latest_button.grid(row=1, column=1, pady=(8, 0))
        ttk.Label(selection, text="PC .sfs saves only. Xbox WGS containers are not supported.").grid(row=1, column=0, sticky="w", pady=(8, 0))

        actions = ttk.Frame(frame)
        actions.grid(row=4, sticky="ew", pady=16)
        self.check_button = ttk.Button(actions, text="2. Check save", command=self.check)
        self.check_button.pack(side="left")
        self.repair_button = ttk.Button(actions, text="3. Create repaired save", command=self.repair, state="disabled")
        self.repair_button.pack(side="left", padx=10)
        self.progress = ttk.Progressbar(actions, mode="indeterminate", length=130)
        self.progress.pack(side="right")

        self.details = scrolledtext.ScrolledText(frame, height=15, wrap="word", font=("Segoe UI", 10),
                                               relief="solid", borderwidth=1, padx=12, pady=10, state="disabled")
        self.details.grid(row=5, sticky="nsew")
        ttk.Label(frame, textvariable=self.subtitle, wraplength=830).grid(row=6, sticky="w", pady=(12, 10))
        footer = ttk.Frame(frame)
        footer.grid(row=7, sticky="ew")
        self.folder_button = ttk.Button(footer, text="Open save folder", command=self.open_saves)
        self.folder_button.pack(side="left")
        self.backup_button = ttk.Button(footer, text="Open backup & report", command=self.open_backup, state="disabled")
        self.backup_button.pack(side="left", padx=10)
        ttk.Label(footer, text="Offline • No account or game plugin required").pack(side="right")
        self.show("This repair restores a severely displaced Anchorpoint station to its original position.\n\n"
                  "It changes only the station’s three position coordinates. Other save data stays unchanged.\n\n"
                  "Save and quit Starfield before creating the repaired copy. Afterward, load the new slot, "
                  "visit Anchorpoint, then save and reload to check that the position holds.")
        if initial:
            self.select(Path(initial))
        else:
            self.use_latest(quiet=True)
        root.after(100, self.poll)

    def show(self, text):
        self.details.configure(state="normal")
        self.details.delete("1.0", "end")
        self.details.insert("1.0", text)
        self.details.configure(state="disabled")

    def select(self, path):
        self.source.set(str(path))
        self.report, self.completed = None, None
        self.repair_button.configure(state="disabled")
        self.backup_button.configure(state="disabled")
        try:
            saved = datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
            self.subtitle.set("Selected save last written: " + saved + ". Check it before repairing.")
        except OSError:
            self.subtitle.set("Choose an existing .sfs save file.")

    def browse(self):
        folder = Path(self.source.get()).parent if self.source.get() else default_save_directory()
        chosen = filedialog.askopenfilename(parent=self.root, title="Choose a Starfield save",
                                           initialdir=folder, filetypes=[("Starfield saves", "*.sfs")])
        if chosen:
            self.select(Path(chosen))

    def use_latest(self, quiet=False):
        folder = Path(self.source.get()).parent if self.source.get() else default_save_directory()
        try:
            path = latest_save(folder)
            if path:
                self.select(path)
            elif not quiet:
                messagebox.showinfo("Choose a save", "No .sfs saves were found here. Use Browse to choose your save.", parent=self.root)
        except OSError as exc:
            self.show(str(exc))

    def work(self, operation, task):
        self.busy = True
        for button in (self.browse_button, self.latest_button, self.check_button, self.repair_button):
            button.configure(state="disabled")
        self.progress.start(12)
        self.subtitle.set("Checking the save…" if operation == "check" else "Backing up, repairing and verifying the new save…")
        def run():
            try:
                self.events.put((operation, task(), None))
            except Exception as exc:
                self.events.put((operation, None, str(exc)))
        threading.Thread(target=run, daemon=False).start()

    def check(self):
        if not self.source.get():
            self.browse()
            if not self.source.get(): return
        self.report, self.completed = None, None
        self.backup_button.configure(state="disabled")
        source = Path(self.source.get())
        self.work("check", lambda: inspect_save(source))

    def repair(self):
        if not self.report or self.report["status"] != "eligible": return
        source, expected = Path(self.source.get()), self.report["inputSha256"]
        self.work("repair", lambda: create_repaired_slot(source, expected))

    def poll(self):
        try:
            operation, result, error = self.events.get_nowait()
        except queue.Empty:
            self.root.after(100, self.poll)
            return
        self.busy = False
        self.progress.stop()
        for button in (self.browse_button, self.latest_button, self.check_button):
            button.configure(state="normal")
        if error:
            self.report = None
            self.show("Could not complete this operation\n\n" + error +
                      "\n\nYour original save was not overwritten. Check the save again before retrying.")
            self.subtitle.set("No successful repair has been confirmed.")
        elif operation == "check":
            self.report = result
            messages = {
                "eligible": ("Displaced Anchorpoint found", "This save matches the repair. Close Starfield, then choose Create repaired save."),
                "alreadyAtDesiredPosition": ("Anchorpoint is already at the repair position", "No coordinate repair is needed. No save was written."),
                "belowDisplacementThreshold": ("No severe displacement found", "This repair does not apply to the selected save. No save was written."),
            }
            heading, explanation = messages[result["status"]]
            self.show(heading + "\n\n" + explanation + "\n\nSelected file: " + result["fileName"] +
                      "\nGame version: " + result["gameVersion"] +
                      "\n\nThe repair preserves all decoded data outside the 12-byte position field. "
                      "The original and its backup remain available.")
            self.subtitle.set(heading)
            if result["status"] == "eligible": self.repair_button.configure(state="normal")
        else:
            self.completed, self.report = result, None
            receipt = result["receipt"]
            self.show(f"Repaired save created — Save{receipt['testSlot']}\n\n" +
                      "New save:\n" + result["installedPath"] + "\n\nOriginal backup:\n" + result["backupPath"] +
                      "\n\nStart Starfield and use Load to choose the new slot. Visit Anchorpoint, test docking, "
                      "then save to another slot and reload. Keep the original until you are satisfied with the result.\n\n"
                      "Verification passed: all decoded bytes outside the station position are unchanged.")
            self.subtitle.set("Finished. The original was preserved; the new slot is ready to test in Starfield.")
            self.backup_button.configure(state="normal")
        self.root.after(100, self.poll)

    def open_saves(self):
        folder = Path(self.source.get()).parent if self.source.get() else default_save_directory()
        self.open_folder(folder)

    def open_backup(self):
        if self.completed: self.open_folder(Path(self.completed["workDirectory"]))

    def open_folder(self, folder):
        try:
            os.startfile(str(folder))
        except OSError as exc:
            messagebox.showerror("Could not open folder", str(exc), parent=self.root)

    def close(self):
        if self.busy:
            self.subtitle.set("Please wait for the current operation to finish before closing.")
        else:
            self.root.destroy()


def main():
    if os.name == "nt":
        import ctypes
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except (AttributeError, OSError):
            pass
    root = tk.Tk()
    RepairWindow(root, sys.argv[1] if len(sys.argv) == 2 else None)
    root.mainloop()


if __name__ == "__main__":
    main()

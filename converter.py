import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import ffmpeg
import os
import platform
import subprocess
import re
import threading
import time

progress = None
progress_var = None
progress_label = None
start_time = None
eta_label = None
elapsed_label = None
stop_button = None
process = None
stop_requested = False
end_action_menu = None
end_action_label = None

def is_amf_available():
    try:
        result = subprocess.run(["ffmpeg", "-encoders"], capture_output=True, text=True, check=True)
        encoders = result.stdout
        # Keresünk AMF támogatott kódolókat
        return ("h264_amf" in encoders) or ("hevc_amf" in encoders)
    except Exception:
        return False

def browse_input():
    filename = filedialog.askopenfilename(title="Válaszd ki a videót",
                                          filetypes=[("Videófájlok", "*.mp4;*.avi;*.mov;*.mkv;*.wmv;*.flv;*.webm"), 
                                                     ("Összes fájl", "*.*")
                                                    ])

    if filename:
        input_entry.delete(0, tk.END)
        input_entry.insert(0, filename)

def browse_output():
    filename = filedialog.asksaveasfilename(title="Kimeneti fájl helye és neve",
                                            defaultextension=".mp4",
                                            filetypes=[ ("MP4 fájl", "*.mp4"),
                                                        ("WEBM fájl", "*.webm"),
                                                        ("AVI fájl", "*.avi"),
                                                        ("MKV fájl", "*.mkv"), 
                                                        ("MOV fájl", "*.mov"), 
                                                        ("Összes fájl", "*.*")
                                                    ])
    
    if filename:
        output_entry.delete(0, tk.END)
        output_entry.insert(0, filename)

def get_video_duration(filename):
    try:
        probe = ffmpeg.probe(filename)
        duration = float(probe['format']['duration'])
        return duration
    except Exception as e:
        return None

def format_time(seconds):
    seconds = int(max(0, seconds))
    hours = seconds // 3600
    mins = (seconds % 3600) // 60
    secs = seconds % 60
    if hours > 0:
        return f"{hours}:{mins:02d}:{secs:02d}"
    else:
        return f"{mins}:{secs:02d}"

def stop_conversion():
    global process, stop_requested
    if process and process.poll() is None:
        stop_requested = True
        process.terminate()


def run_conversion_with_progress(input_path, output_path, total_duration):
    global progress, process, stop_requested

    #Kimeneti fájl kiterjesztésének vizsgálata
    ext= os.path.splitext(output_path)[1].lower()

    amf_supported = is_amf_available()

    if ext == ".webm":
        audio_codec = "libopus"
        video_codec = "libvpx-vp9"
    elif ext == ".mp4":
        if amf_supported:
            video_codec = "h264_amf"
        else:
            video_codec = "libx264"
        audio_codec = "aac"

    else:
        audio_codec = "aac"
        video_codec = "libx264"
    
    command = [
        "ffmpeg",
        "-i", input_path,
        "-map", "0:v:0",
        "-map", "0:a:0",
        "-c:v", video_codec,
        "-b:v", "4M",
        "-crf", "27",
        "-c:a", audio_codec,
        "-ac", "2",
        "-b:a", "192k",
        "-y", output_path
    ]

    max_percent = 0
    stderr_output = ""
    time_pattern = re.compile(r'time=(\d+):(\d+):(\d+\.\d+)')
    last_update = 0
    min_interval = 1
    try:
        creationflags = 0
        if os.name == "nt":
            creationflags = subprocess.CREATE_NO_WINDOW
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            bufsize=1,
            creationflags=creationflags
        )
        while True:
            line = process.stderr.readline()
            if not line:
                break
            stderr_output += line
            match = time_pattern.search(line)
            if match and total_duration:
                h, m, s = match.groups()
                secs = int(h)*3600 + int(m)*60 + float(s)
                percent = min(100, secs / total_duration * 100)
                current_time = time.time()
                if current_time - last_update >= min_interval and percent >= max_percent:
                    max_percent = percent
                    app.after(0, update_progress_safe, percent)
                    last_update = current_time
        process.wait()
        if stop_requested:
            app.after(0, hide_progress)
            app.after(0, lambda: messagebox.showinfo("Leállítva", "A konvertálás megszakítva."))
        elif process.returncode == 0:
            app.after(0, show_success_and_hide_progress)
        else:
            app.after(0, hide_progress)
            app.after(0, lambda: messagebox.showerror("Hiba", f"Hiba történt a konvertálás során:\n{stderr_output}"))
    except Exception as e:
        app.after(0, hide_progress)
        app.after(0, lambda: messagebox.showerror("Hiba", f"Hiba történt a konvertálás során:\n{e}"))
    finally:
        if progress:
            app.after(0, progress.stop)

def update_progress_safe(value):
    global start_time, progress, progress_label, progress_var, eta_label, elapsed_label
    if value >= progress_var.get():
        progress_var.set(value)
        if progress_label:
            progress_label.config(text=f"{value:.1f}% kész")
        if value > 0 and value < 100 and start_time:
            elapsed = time.time() - start_time
            total_estimated = elapsed / (value / 100)
            remaining = total_estimated - elapsed
            if elapsed_label:
                elapsed_label.config(text=f"Eltelt idő: {format_time(elapsed)}")
            if eta_label:
                eta_label.config(text=f"Várható hátralévő idő: {format_time(remaining)}")
        elif value >= 100:
            if elapsed_label:
                elapsed_label.config(text=f"Konvertálás ideje: {format_time(time.time()-start_time)}")
            if eta_label:
                eta_label.config(text="Kész!")
        if progress:
            progress.update()
    

def convert_video():
    global progress, progress_var, progress_label, eta_label, start_time, elapsed_label, stop_button, stop_requested, end_action_menu, end_action_label
    stop_requested = False
    input_path = input_entry.get()
    output_path = output_entry.get()
    if not input_path or not output_path:
        messagebox.showwarning("Hiányzó adat", "Kérlek válassz ki bemenetet és kimenetet!")
        return
    total_duration = get_video_duration(input_path)
    if total_duration is None:
        messagebox.showerror("Hiba", "Nem sikerült lekérdezni a videó hosszát!")
        return
    hide_progress()
    start_time = time.time()
    
    progress_var = tk.DoubleVar()
    progress = ttk.Progressbar(app, orient="horizontal",length=300, mode="determinate",variable=progress_var, maximum=100)    
    progress.grid(row=3, column=0, columnspan=3, pady=10)
    progress_var.set(0)
    
    progress_label = tk.Label(app, text="0% kész")
    progress_label.grid(row=4, column=0, columnspan=3)
    
    elapsed_label = tk.Label(app, text="Eltelt idő: 0:00")
    elapsed_label.grid(row=5, column=0, columnspan=3, sticky="w")

    eta_label = tk.Label(app, text="")
    eta_label.grid(row=6, column=0, columnspan=3, sticky="w")

    end_action_frame = tk.Frame(app)
    end_action_frame.grid(row=7, column=0, columnspan=2, sticky="w", pady=5)

    end_action_label = tk.Label(end_action_frame, text="Befejezéskor:")
    end_action_label.pack(side="left")

    end_action_menu = ttk.Combobox(end_action_frame, textvariable=end_action, values=actions, state="readonly", width=15)
    end_action_menu.pack(side="left", padx=(3,0))

    stop_button = tk.Button(app, text="Leállítás", command=stop_conversion, width=7)
    stop_button.grid(row=7, column=2, padx=5, pady=10)

    threading.Thread(
        target=run_conversion_with_progress,
        args=(input_path, output_path, total_duration),
        daemon=True
    ).start()

def show_success_and_hide_progress():
    action = end_action.get()
    if action == "Leállítás":
        handle_end_action()
        hide_progress()
    elif action == "Alvás":
        handle_end_action()
        hide_progress()
    else:
        messagebox.showinfo("Siker", "A videó konvertálása sikeresen befejeződött!")
        handle_end_action()
        hide_progress()

def handle_end_action():
    action = end_action.get()
    if action == "Leállítás":
        shutdown_computer()
    elif action == "Alvás":
        sleep_computer()

def shutdown_computer():
    if platform.system() == "Windows":
        os.system("shutdown /s /t 0")
    elif platform.system() == "Linux":
        os.system("shutdown now")

def sleep_computer():
    if platform.system() == "Windows":
        os.system("rundll32.exe powrprof.dll,SetSuspendState 0,1,0")
    elif platform.system() == "Linux":
        os.system("systemctl suspend")

def hide_progress():
    global progress, progress_label, eta_label, elapsed_label, stop_button, end_action_menu, end_action_label
    if progress:
        progress.grid_remove()
        progress = None
    if progress_label:
        progress_label.destroy()
        progress_label = None
    if eta_label:
        eta_label.destroy()
        eta_label = None
    if elapsed_label:
        elapsed_label.destroy()
        elapsed_label = None
    if stop_button:
        stop_button.destroy()
        stop_button = None
    if end_action_menu:
        end_action_menu.destroy()
        end_action_menu = None
    if end_action_label:
        end_action_label.destroy()
        end_action_label = None

app = tk.Tk()
app.title("Video Converter")
#app.iconbitmap("converter/converter_logo.ico")

tk.Label(app, text="Bemeneti videó:").grid(row=0, column=0, sticky='e', pady=10)
input_entry = tk.Entry(app, width=50)
input_entry.grid(row=0, column=1)
tk.Button(app, text="Tallózás", command=browse_input).grid(row=0, column=2)

tk.Label(app, text="Kimeneti hely (fájl):").grid(row=1, column=0, sticky='e')
output_entry = tk.Entry(app, width=50)
output_entry.grid(row=1, column=1)
tk.Button(app, text="Tallózás", command=browse_output).grid(row=1, column=2)

tk.Button(app, text="Konvertálás", command=convert_video, width=30).grid(row=2, column=0, columnspan=3, pady=15)

end_action = tk.StringVar(value="Semmit")
actions = ["Semmit", "Alvás", "Leállítás"]

app.mainloop()
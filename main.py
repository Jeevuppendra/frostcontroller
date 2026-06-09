import tkinter as tk
from tkinter import messagebox
from PIL import Image, ImageTk
import cv2
import requests
import threading
import queue
import json
import os
import time

# ---------- Persistent configuration ----------
CONFIG_FILE = "config.json"

def load_config():
    """Load settings from JSON file, or use defaults."""
    default = {
        "camera_index": 0,                     # USB camera device index
        "controller_ip": "192.168.1.101",
        "controller_port": "80",
        "heartbeat_enabled": False,
        "heartbeat_interval": 5
    }
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                cfg = json.load(f)
            default.update(cfg)
        except:
            pass
    return default

def save_config():
    """Write current global settings to JSON."""
    cfg = {
        "camera_index": camera_index_value,
        "controller_ip": controller_ip_value,
        "controller_port": controller_port_value,
        "heartbeat_enabled": heartbeat_enabled,
        "heartbeat_interval": heartbeat_interval
    }
    with open(CONFIG_FILE, "w") as f:
        json.dump(cfg, f, indent=2)

# Load saved settings at startup
config = load_config()
camera_index_value = config["camera_index"]
controller_ip_value = config["controller_ip"]
controller_port_value = config["controller_port"]
heartbeat_enabled = config["heartbeat_enabled"]
heartbeat_interval = config["heartbeat_interval"]

PRIVATE_KEY = "1234"

# ---------- Global variables ----------
cap = None
camera_running = False
camera_thread = None
frame_queue = queue.Queue(maxsize=1)   # only keep latest frame

heartbeat_running = False
heartbeat_after_id = None

# ---------- Thread‑safe bottle commands ----------
def send_bottle_command(cmd):
    def task():
        url = f"http://{controller_ip_value}:{controller_port_value}/control?cmd={cmd}"
        try:
            resp = requests.get(url, timeout=5)
            root.after(0, lambda: update_bottle_status(resp.ok, cmd, resp.text))
        except Exception as e:
            root.after(0, lambda e=e: show_network_error(e))
    threading.Thread(target=task, daemon=True).start()

def update_bottle_status(success, cmd, message):
    if success:
        if cmd == "1":
            bottle_status.config(text="Bottle Placed ✅", bg="green")
        else:
            bottle_status.config(text="Bottle Removed ❌", bg="orange")
    else:
        bottle_status.config(text="Command Failed ❌", bg="red")

def show_network_error(e):
    messagebox.showerror("Network Error", f"Cannot reach bottle controller:\n{e}")

def place_bottle():
    send_bottle_command("1")

def remove_bottle():
    send_bottle_command("0")

# ---------- Heartbeat ----------
def start_heartbeat():
    global heartbeat_running, heartbeat_after_id
    if heartbeat_running:
        return
    heartbeat_running = True
    do_heartbeat()

def stop_heartbeat():
    global heartbeat_running, heartbeat_after_id
    heartbeat_running = False
    if heartbeat_after_id:
        root.after_cancel(heartbeat_after_id)
        heartbeat_after_id = None
    heartbeat_status.config(text="Heartbeat: OFF", bg="gray")

def do_heartbeat():
    global heartbeat_after_id
    if not heartbeat_running:
        return

    def check():
        url = f"http://{controller_ip_value}:{controller_port_value}/"
        try:
            resp = requests.get(url, timeout=2)
            root.after(0, lambda: heartbeat_status.config(text="Heartbeat: OK ✅", bg="green"))
        except:
            root.after(0, lambda: heartbeat_status.config(text="Heartbeat: FAIL ❌", bg="red"))

    threading.Thread(target=check, daemon=True).start()
    heartbeat_after_id = root.after(heartbeat_interval * 1000, do_heartbeat)

# ---------- USB webcam reader thread (non‑blocking) ----------
def camera_reader_thread():
    global cap, camera_running
    # Use the configured camera index (e.g. 0 for first USB webcam)
    while camera_running:
        if cap is None or not cap.isOpened():
            cap = cv2.VideoCapture(camera_index_value)
            if not cap.isOpened():
                root.after(0, lambda: camera_status.config(text="Reconnecting... 🔄", bg="orange"))
                root.after(0, lambda: camera_placeholder.config(image="", text="NO CAMERA\nCheck index & connection"))
                cap = None
                time.sleep(3)
                continue
            else:
                root.after(0, lambda: camera_status.config(text="Camera: ON 📷", bg="green"))
                root.after(0, lambda: camera_placeholder.config(text=""))

        ret, frame = cap.read()
        if not ret:
            cap.release()
            cap = None
            root.after(0, lambda: camera_status.config(text="Reconnecting... 🔄", bg="orange"))
            root.after(0, lambda: camera_placeholder.config(image="", text="RECONNECTING..."))
            continue

        # Optional: flip horizontally if your webcam is mirrored
        # frame = cv2.flip(frame, 1)

        frame = cv2.resize(frame, (480, 360))
        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        if frame_queue.full():
            try:
                frame_queue.get_nowait()
            except queue.Empty:
                pass
        frame_queue.put(frame)

    if cap:
        cap.release()
        cap = None

def start_camera():
    global camera_running, camera_thread
    if camera_running:
        return
    camera_running = True
    camera_thread = threading.Thread(target=camera_reader_thread, daemon=True)
    camera_thread.start()
    update_frame_display()

def stop_camera():
    global camera_running
    camera_running = False
    camera_status.config(text="Camera: OFF", bg="red")
    camera_placeholder.config(image="", text="CAMERA OUTPUT")

def update_frame_display():
    if not camera_running:
        return
    try:
        frame = frame_queue.get_nowait()
        img = Image.fromarray(frame)
        imgtk = ImageTk.PhotoImage(image=img)
        camera_placeholder.imgtk = imgtk
        camera_placeholder.config(image=imgtk)
        camera_placeholder.image = imgtk
    except queue.Empty:
        pass
    if camera_running:
        root.after(30, update_frame_display)

# ---------- Admin panel ----------
def open_admin_login():
    login = tk.Toplevel(root)
    login.title("Admin Login")
    login.geometry("300x180")
    login.configure(bg="#101820")
    login.grab_set()
    tk.Label(login, text="Enter Private Key", bg="#101820", fg="white",
             font=("Arial", 14)).pack(pady=15)
    key_entry = tk.Entry(login, show="*", font=("Arial", 14))
    key_entry.pack(pady=5)
    key_entry.focus()

    def check_key(event=None):
        if key_entry.get() == PRIVATE_KEY:
            login.destroy()
            open_admin_panel()
        else:
            messagebox.showerror("Access Denied", "Wrong Private Key")
            key_entry.delete(0, tk.END)

    key_entry.bind("<Return>", check_key)
    tk.Button(login, text="Login", command=check_key, width=12).pack(pady=15)

def open_admin_panel():
    admin = tk.Toplevel(root)
    admin.title("FROST Admin Settings")
    admin.geometry("400x550")
    admin.configure(bg="#101820")
    admin.grab_set()

    tk.Label(admin, text="ADMIN SETTINGS", bg="#101820", fg="cyan",
             font=("Arial", 20, "bold")).pack(pady=15)

    # USB Camera Index instead of IP
    tk.Label(admin, text="USB Camera Index (0,1,2,…)", bg="#101820", fg="white",
             font=("Arial", 12)).pack()
    camera_index_entry = tk.Entry(admin, font=("Arial", 12), width=10)
    camera_index_entry.insert(0, str(camera_index_value))
    camera_index_entry.pack(pady=5)

    tk.Label(admin, text="Bottle Controller IP", bg="#101820", fg="white",
             font=("Arial", 12)).pack()
    controller_ip = tk.Entry(admin, font=("Arial", 12), width=25)
    controller_ip.insert(0, controller_ip_value)
    controller_ip.pack(pady=5)

    tk.Label(admin, text="Bottle Controller Port", bg="#101820", fg="white",
             font=("Arial", 12)).pack()
    controller_port = tk.Entry(admin, font=("Arial", 12), width=25)
    controller_port.insert(0, controller_port_value)
    controller_port.pack(pady=5)

    tk.Label(admin, text="HEARTBEAT SETTINGS", bg="#101820", fg="cyan",
             font=("Arial", 14, "bold")).pack(pady=(15,5))

    hb_enable_var = tk.IntVar(value=1 if heartbeat_enabled else 0)
    hb_enable_cb = tk.Checkbutton(admin, text="Enable Heartbeat", variable=hb_enable_var,
                                  bg="#101820", fg="white", selectcolor="#101820",
                                  font=("Arial", 11))
    hb_enable_cb.pack(pady=5)

    tk.Label(admin, text="Heartbeat Interval (seconds)", bg="#101820", fg="white",
             font=("Arial", 12)).pack()
    hb_interval_entry = tk.Entry(admin, font=("Arial", 12), width=10)
    hb_interval_entry.insert(0, str(heartbeat_interval))
    hb_interval_entry.pack(pady=5)

    def save_settings():
        global camera_index_value, controller_ip_value, controller_port_value
        global heartbeat_enabled, heartbeat_interval

        try:
            new_cam_idx = int(camera_index_entry.get().strip())
        except ValueError:
            messagebox.showerror("Error", "Camera index must be an integer (0,1,2,…)")
            return

        new_ctrl_ip = controller_ip.get().strip()
        new_ctrl_port = controller_port.get().strip()
        new_hb_enabled = bool(hb_enable_var.get())
        new_hb_interval = hb_interval_entry.get().strip()

        if not new_ctrl_ip or not new_ctrl_port:
            messagebox.showerror("Error", "All fields are required")
            return
        if not new_ctrl_port.isdigit():
            messagebox.showerror("Error", "Controller port must be a number")
            return
        if not new_hb_interval.isdigit() or int(new_hb_interval) < 1:
            messagebox.showerror("Error", "Heartbeat interval must be a positive number")
            return

        camera_index_value = new_cam_idx
        controller_ip_value = new_ctrl_ip
        controller_port_value = new_ctrl_port
        heartbeat_enabled = new_hb_enabled
        heartbeat_interval = int(new_hb_interval)

        save_config()

        stop_heartbeat()
        if heartbeat_enabled:
            start_heartbeat()

        if camera_running:
            stop_camera()
            start_camera()

        settings_label.config(
            text=f"Cam idx: {camera_index_value} | Ctrl: {controller_ip_value}:{controller_port_value}"
        )
        messagebox.showinfo("Saved", "Settings saved successfully")
        admin.destroy()

    tk.Button(admin, text="Save Settings", command=save_settings,
              width=18, height=2).pack(pady=20)

def close_app():
    stop_camera()
    stop_heartbeat()
    root.destroy()

# ---------- Build main UI ----------
root = tk.Tk()
root.title("FROST Controller")
root.geometry("800x560")
root.configure(bg="#101820")
root.protocol("WM_DELETE_WINDOW", close_app)

title = tk.Label(root, text="FROST CONTROLLER",
                 font=("Arial", 24, "bold"),
                 fg="cyan", bg="#101820")
title.pack(pady=15)

main_frame = tk.Frame(root, bg="#101820")
main_frame.pack(fill="both", expand=True)

left_panel = tk.Frame(main_frame, bg="#101820")
left_panel.pack(side="left", padx=20)

bottle_status = tk.Label(left_panel, text="Bottle Status",
                         font=("Arial", 14),
                         fg="white", bg="gray", width=22)
bottle_status.pack(pady=10)

camera_status = tk.Label(left_panel, text="Camera: OFF",
                         font=("Arial", 14),
                         fg="white", bg="red", width=22)
camera_status.pack(pady=10)

heartbeat_status = tk.Label(left_panel, text="Heartbeat: OFF",
                            font=("Arial", 14),
                            fg="white", bg="gray", width=22)
heartbeat_status.pack(pady=10)

tk.Button(left_panel, text="Place Bottle", width=20, height=2,
          font=("Arial", 12), command=place_bottle).pack(pady=5)

tk.Button(left_panel, text="Remove Bottle", width=20, height=2,
          font=("Arial", 12), command=remove_bottle).pack(pady=5)

tk.Button(left_panel, text="Camera ON", width=20, height=2,
          font=("Arial", 12), command=start_camera).pack(pady=5)

tk.Button(left_panel, text="Camera OFF", width=20, height=2,
          font=("Arial", 12), command=stop_camera).pack(pady=5)

tk.Button(left_panel, text="GUI Settings", width=20, height=2,
          font=("Arial", 12), command=open_admin_login).pack(pady=5)

settings_label = tk.Label(left_panel,
                           text=f"Cam idx: {camera_index_value} | Ctrl: {controller_ip_value}:{controller_port_value}",
                           font=("Arial", 10),
                           fg="white", bg="#101820",
                           wraplength=200)
settings_label.pack(pady=10)

right_panel = tk.Frame(main_frame, bg="#101820")
right_panel.pack(side="right", padx=20)

camera_placeholder = tk.Label(
    right_panel,
    bg="black",
    width=480,
    height=360,
    relief="ridge",
    bd=5,
    text="CAMERA OUTPUT",
    fg="white",
    font=("Arial", 14)
)
camera_placeholder.pack()
camera_placeholder.pack_propagate(False)

if heartbeat_enabled:
    root.after(500, start_heartbeat)

root.mainloop()
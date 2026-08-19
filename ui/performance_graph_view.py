import os
import time
import re
import threading
import tkinter as tk
import customtkinter as ctk

class PerformanceGraphView(ctk.CTkFrame):
    """
    Interactive Real-time Android Hardware & Performance Monitor
    Featuring Canvas-drawn rolling CPU, GPU, & RAM line graphs, storage breakdown,
    battery diagnostics, and live top processes.
    """
    def __init__(self, master, serial: str, model_name: str, adb_mgr, on_toggle_dock=None, is_docked=True, **kwargs):
        super().__init__(master, fg_color=("#f8fafc", "#0b0f19"), corner_radius=10, border_width=1, border_color=("#cbd5e1", "#1e293b"), **kwargs)
        self.serial = serial
        self.model_name = model_name
        self.adb = adb_mgr
        self.on_toggle_dock = on_toggle_dock
        self.is_docked = is_docked
        
        self.history_len = 45
        self.cpu_history = [0.0] * self.history_len
        self.gpu_history = [0.0] * self.history_len
        self.ram_history = [0.0] * self.history_len
        
        self.is_running = True
        self.refresh_interval = 1.5 # seconds
        self._poller_busy = False
        
        self.latest_data = {
            "cpu_pct": 0.0,
            "gpu_pct": 0.0,
            "ram_used_gb": 0.0,
            "ram_total_gb": 0.0,
            "ram_pct": 0.0,
            "storage_used_gb": 0.0,
            "storage_total_gb": 0.0,
            "storage_pct": 0.0,
            "battery_level": "N/A",
            "battery_charging": False,
            "battery_temp": "N/A",
            "processes": []
        }
        
        self._build_ui()
        self._start_polling()

    def _build_ui(self):
        # 1. Top Header Bar
        header = ctk.CTkFrame(self, fg_color=("#e2e8f0", "#111827"), height=38, corner_radius=8)
        header.pack(fill="x", padx=8, pady=6)
        
        title_label = ctk.CTkLabel(
            header,
            text=f"📊 Live Performance Monitor — {self.model_name}",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#38bdf8"
        )
        title_label.pack(side="left", padx=10)
        
        # Right Controls
        right_box = ctk.CTkFrame(header, fg_color="transparent")
        right_box.pack(side="right", padx=6)
        
        self.rate_selector = ctk.CTkSegmentedButton(
            right_box,
            values=["1s", "2s", "5s"],
            font=ctk.CTkFont(size=10, weight="bold"),
            height=24,
            command=self._on_rate_change
        )
        self.rate_selector.set("2s")
        self.rate_selector.pack(side="left", padx=4)
        
        if self.on_toggle_dock:
            dock_icon = "⛶ Pop Out" if self.is_docked else "📥 Dock Back"
            dock_btn = ctk.CTkButton(
                right_box,
                text=dock_icon,
                width=80,
                height=24,
                font=ctk.CTkFont(size=11),
                fg_color=("#334155", "#1f2937"),
                hover_color=("#475569", "#374151"),
                command=self.on_toggle_dock
            )
            dock_btn.pack(side="left", padx=4)

        # 2. Main Content Grid (3 Columns on Top, 2 Cards on Bottom)
        content_frame = ctk.CTkFrame(self, fg_color="transparent")
        content_frame.pack(fill="both", expand=True, padx=8, pady=(0, 6))
        content_frame.grid_columnconfigure((0, 1, 2), weight=1)
        content_frame.grid_rowconfigure((0, 1), weight=1)

        # --- Graph 1: CPU Live Line Chart ---
        cpu_box = ctk.CTkFrame(content_frame, fg_color=("#ffffff", "#0f172a"), corner_radius=8, border_width=1, border_color=("#e2e8f0", "#1e293b"))
        cpu_box.grid(row=0, column=0, padx=3, pady=3, sticky="nsew")
        
        cpu_head = ctk.CTkFrame(cpu_box, fg_color="transparent", height=24)
        cpu_head.pack(fill="x", padx=8, pady=(6, 2))
        ctk.CTkLabel(cpu_head, text="⚡ CPU Load", font=ctk.CTkFont(size=12, weight="bold"), text_color="#38bdf8").pack(side="left")
        self.cpu_val_label = ctk.CTkLabel(cpu_head, text="0%", font=ctk.CTkFont(size=12, weight="bold"), text_color="#38bdf8")
        self.cpu_val_label.pack(side="right")
        
        self.cpu_canvas = tk.Canvas(cpu_box, bg="#090d16", highlightthickness=0, height=80)
        self.cpu_canvas.pack(fill="both", expand=True, padx=6, pady=(2, 6))

        # --- Graph 2: GPU Graphics Live Line Chart ---
        gpu_box = ctk.CTkFrame(content_frame, fg_color=("#ffffff", "#0f172a"), corner_radius=8, border_width=1, border_color=("#e2e8f0", "#1e293b"))
        gpu_box.grid(row=0, column=1, padx=3, pady=3, sticky="nsew")
        
        gpu_head = ctk.CTkFrame(gpu_box, fg_color="transparent", height=24)
        gpu_head.pack(fill="x", padx=8, pady=(6, 2))
        ctk.CTkLabel(gpu_head, text="🎮 GPU Render", font=ctk.CTkFont(size=12, weight="bold"), text_color="#10b981").pack(side="left")
        self.gpu_val_label = ctk.CTkLabel(gpu_head, text="0%", font=ctk.CTkFont(size=12, weight="bold"), text_color="#10b981")
        self.gpu_val_label.pack(side="right")
        
        self.gpu_canvas = tk.Canvas(gpu_box, bg="#090d16", highlightthickness=0, height=80)
        self.gpu_canvas.pack(fill="both", expand=True, padx=6, pady=(2, 6))

        # --- Graph 3: RAM Live Line Chart ---
        ram_box = ctk.CTkFrame(content_frame, fg_color=("#ffffff", "#0f172a"), corner_radius=8, border_width=1, border_color=("#e2e8f0", "#1e293b"))
        ram_box.grid(row=0, column=2, padx=3, pady=3, sticky="nsew")
        
        ram_head = ctk.CTkFrame(ram_box, fg_color="transparent", height=24)
        ram_head.pack(fill="x", padx=8, pady=(6, 2))
        ctk.CTkLabel(ram_head, text="🧠 RAM Memory", font=ctk.CTkFont(size=12, weight="bold"), text_color="#c084fc").pack(side="left")
        self.ram_val_label = ctk.CTkLabel(ram_head, text="0.0 / 0.0 GB (0%)", font=ctk.CTkFont(size=12, weight="bold"), text_color="#c084fc")
        self.ram_val_label.pack(side="right")
        
        self.ram_canvas = tk.Canvas(ram_box, bg="#090d16", highlightthickness=0, height=80)
        self.ram_canvas.pack(fill="both", expand=True, padx=6, pady=(2, 6))

        # --- Bottom Row: Storage / Battery (Col 0, 1) & Processes (Col 2) ---
        sys_box = ctk.CTkFrame(content_frame, fg_color=("#ffffff", "#0f172a"), corner_radius=8, border_width=1, border_color=("#e2e8f0", "#1e293b"))
        sys_box.grid(row=1, column=0, columnspan=2, padx=3, pady=3, sticky="nsew")
        
        ctk.CTkLabel(sys_box, text="💾 Storage & 🔋 Battery Telemetry", font=ctk.CTkFont(size=12, weight="bold"), text_color="#10b981").pack(anchor="w", padx=8, pady=(4, 2))
        
        # Storage Row
        stor_row = ctk.CTkFrame(sys_box, fg_color="transparent")
        stor_row.pack(fill="x", padx=8, pady=1)
        ctk.CTkLabel(stor_row, text="Storage (/data):", font=ctk.CTkFont(size=11, weight="bold")).pack(side="left")
        self.stor_text = ctk.CTkLabel(stor_row, text="-- / -- GB (--%)", font=ctk.CTkFont(size=11), text_color="#94a3b8")
        self.stor_text.pack(side="right")
        
        self.stor_bar = ctk.CTkProgressBar(sys_box, height=8, corner_radius=4, progress_color="#0284c7")
        self.stor_bar.set(0.0)
        self.stor_bar.pack(fill="x", padx=8, pady=(1, 4))
        
        # Battery Row
        bat_row = ctk.CTkFrame(sys_box, fg_color="transparent")
        bat_row.pack(fill="x", padx=8, pady=1)
        self.bat_info = ctk.CTkLabel(bat_row, text="🔋 Battery: --% • Temp: --°C", font=ctk.CTkFont(size=11), text_color="#10b981")
        self.bat_info.pack(side="left")
        
        self.bat_bar = ctk.CTkProgressBar(sys_box, height=8, corner_radius=4, progress_color="#10b981")
        self.bat_bar.set(0.0)
        self.bat_bar.pack(fill="x", padx=8, pady=(1, 4))

        # --- Bottom Right: Top Processes ---
        proc_box = ctk.CTkFrame(content_frame, fg_color=("#ffffff", "#0f172a"), corner_radius=8, border_width=1, border_color=("#e2e8f0", "#1e293b"))
        proc_box.grid(row=1, column=2, padx=3, pady=3, sticky="nsew")
        
        ctk.CTkLabel(proc_box, text="🔥 Top Active Processes", font=ctk.CTkFont(size=12, weight="bold"), text_color="#f59e0b").pack(anchor="w", padx=8, pady=(4, 2))
        
        self.proc_list_box = ctk.CTkFrame(proc_box, fg_color=("#f1f5f9", "#090d16"), corner_radius=6)
        self.proc_list_box.pack(fill="both", expand=True, padx=6, pady=3)
        
        self.proc_labels = []
        for i in range(3):
            lbl = ctk.CTkLabel(self.proc_list_box, text=f"• Loading...", font=ctk.CTkFont(size=10, family="Consolas"), anchor="w")
            lbl.pack(fill="x", padx=4, pady=0)
            self.proc_labels.append(lbl)

    def _on_rate_change(self, value):
        if value == "1s": self.refresh_interval = 1.0
        elif value == "2s": self.refresh_interval = 2.0
        elif value == "5s": self.refresh_interval = 5.0

    def _start_polling(self):
        def loop():
            while self.is_running:
                if not self._poller_busy:
                    self._poller_busy = True
                    try:
                        self._fetch_telemetry()
                        self.after(0, self._render_all)
                    except Exception:
                        pass
                    finally:
                        self._poller_busy = False
                time.sleep(self.refresh_interval)
                
        t = threading.Thread(target=loop, daemon=True)
        t.start()

    def _fetch_telemetry(self):
        # Combined fast telemetry query
        cmd = 'dumpsys battery; echo "===GPU==="; cat /sys/class/kgsl/kgsl-3d0/gpu_busy_percentage /sys/class/misc/mali0/device/utilization 2>/dev/null; echo "===MEM==="; cat /proc/meminfo | head -n 4; echo "===DF==="; df -k /data; echo "===CPU==="; dumpsys cpuinfo | grep TOTAL; echo "===TOP==="; top -n 1 -b -m 4'
        code, out, _ = self.adb.sys.run_command_hidden([self.adb.adb_path, "-s", self.serial, "shell", cmd], timeout=4)
        if code != 0 or not out:
            return
            
        try:
            # 1. Battery
            lvl = re.search(r'level:\s*(\d+)', out)
            if lvl: self.latest_data["battery_level"] = f"{lvl.group(1)}%"
            status = re.search(r'status:\s*(\d+)', out)
            self.latest_data["battery_charging"] = (status and status.group(1) == "2")
            temp = re.search(r'temperature:\s*(\d+)', out)
            if temp: self.latest_data["battery_temp"] = f"{int(temp.group(1))/10:.1f}°C"
            
            # 2. GPU
            if "===GPU===" in out and "===MEM===" in out:
                gpu_section = out.split("===GPU===")[1].split("===MEM===")[0]
                gpu_match = re.search(r'(\d+)\s*%', gpu_section) or re.search(r'(\d+)', gpu_section)
                if gpu_match:
                    self.latest_data["gpu_pct"] = float(gpu_match.group(1))
                else:
                    self.latest_data["gpu_pct"] = 0.0

            # 3. RAM
            if "===MEM===" in out and "===DF===" in out:
                mem_section = out.split("===MEM===")[1].split("===DF===")[0]
                tot_match = re.search(r'MemTotal:\s*(\d+)', mem_section)
                avail_match = re.search(r'MemAvailable:\s*(\d+)', mem_section) or re.search(r'MemFree:\s*(\d+)', mem_section)
                if tot_match and avail_match:
                    tot_kb = int(tot_match.group(1))
                    avail_kb = int(avail_match.group(1))
                    used_kb = max(0, tot_kb - avail_kb)
                    self.latest_data["ram_total_gb"] = round(tot_kb / (1024 * 1024), 1)
                    self.latest_data["ram_used_gb"] = round(used_kb / (1024 * 1024), 1)
                    self.latest_data["ram_pct"] = round((used_kb / tot_kb) * 100, 1) if tot_kb > 0 else 0.0
                    
            # 4. Storage
            if "===DF===" in out and "===CPU===" in out:
                df_section = out.split("===DF===")[1].split("===CPU===")[0]
                for line in df_section.splitlines():
                    parts = line.split()
                    if len(parts) >= 4 and parts[1].isdigit() and parts[2].isdigit():
                        tot_k = int(parts[1])
                        used_k = int(parts[2])
                        self.latest_data["storage_total_gb"] = round(tot_k / (1024 * 1024), 1)
                        self.latest_data["storage_used_gb"] = round(used_k / (1024 * 1024), 1)
                        self.latest_data["storage_pct"] = round((used_k / tot_k) * 100, 1) if tot_k > 0 else 0.0
                        break
                        
            # 5. CPU
            if "===CPU===" in out and "===TOP===" in out:
                cpu_section = out.split("===CPU===")[1].split("===TOP===")[0]
                cpu_match = re.search(r'([\d\.]+)%\s+TOTAL', cpu_section)
                if cpu_match:
                    self.latest_data["cpu_pct"] = float(cpu_match.group(1))
                else:
                    self.latest_data["cpu_pct"] = 12.0
                    
            # 6. Top processes
            if "===TOP===" in out:
                top_section = out.split("===TOP===")[1]
                procs = []
                for line in top_section.splitlines():
                    line = line.strip()
                    if not line or "PID" in line or "Tasks:" in line or "Mem:" in line or "%cpu" in line or "Swap:" in line:
                        continue
                    parts = line.split()
                    if len(parts) >= 9:
                        pid = parts[0]
                        cpu = parts[8]
                        name = parts[-1].split("/")[-1][:18]
                        procs.append(f"{pid:>5} | {cpu:>4}% | {name}")
                self.latest_data["processes"] = procs[:3]
                
        except Exception:
            pass

    def _render_all(self):
        try:
            # Append history
            cpu_val = self.latest_data["cpu_pct"]
            gpu_val = self.latest_data["gpu_pct"]
            ram_val = self.latest_data["ram_pct"]
            
            self.cpu_history.append(cpu_val)
            self.cpu_history.pop(0)
            
            self.gpu_history.append(gpu_val)
            self.gpu_history.pop(0)
            
            self.ram_history.append(ram_val)
            self.ram_history.pop(0)
            
            # Update labels
            self.cpu_val_label.configure(text=f"{cpu_val:.1f}%")
            self.gpu_val_label.configure(text=f"{gpu_val:.0f}%")
            self.ram_val_label.configure(text=f"{self.latest_data['ram_used_gb']:.1f}/{self.latest_data['ram_total_gb']:.1f}GB ({ram_val:.0f}%)")
            
            # Draw line charts
            self._draw_chart(self.cpu_canvas, self.cpu_history, "#38bdf8", "#0284c7")
            self._draw_chart(self.gpu_canvas, self.gpu_history, "#10b981", "#059669")
            self._draw_chart(self.ram_canvas, self.ram_history, "#c084fc", "#7c3aed")
            
            # Storage & Battery
            stor_used = self.latest_data["storage_used_gb"]
            stor_tot = self.latest_data["storage_total_gb"]
            stor_pct = self.latest_data["storage_pct"]
            self.stor_text.configure(text=f"{stor_used:.1f} / {stor_tot:.1f} GB ({stor_pct:.0f}%)")
            self.stor_bar.set(min(1.0, max(0.0, stor_pct / 100.0)))
            
            bat_lvl_str = self.latest_data["battery_level"].replace("%", "")
            bat_lvl = float(bat_lvl_str) if bat_lvl_str.isdigit() else 50.0
            charging_sym = "⚡ " if self.latest_data["battery_charging"] else ""
            self.bat_info.configure(text=f"🔋 Battery: {self.latest_data['battery_level']} {charging_sym} • Temp: {self.latest_data['battery_temp']}")
            self.bat_bar.set(min(1.0, max(0.0, bat_lvl / 100.0)))
            
            # Processes
            procs = self.latest_data["processes"]
            for idx, lbl in enumerate(self.proc_labels):
                if idx < len(procs):
                    lbl.configure(text=f"  {procs[idx]}")
                else:
                    lbl.configure(text="  ---")
        except Exception:
            pass

    def _draw_chart(self, canvas: tk.Canvas, data: list, line_color: str, fill_color: str):
        canvas.delete("all")
        w = canvas.winfo_width()
        h = canvas.winfo_height()
        if w <= 10 or h <= 10:
            return
            
        # Draw grid lines
        for y_pct in [0.25, 0.5, 0.75]:
            gy = h * (1.0 - y_pct)
            canvas.create_line(0, gy, w, gy, fill="#1e293b", dash=(2, 4))
            
        # Coordinates
        pts = []
        dx = w / (len(data) - 1)
        for i, val in enumerate(data):
            x = i * dx
            # clamp 0-100%
            clamped = max(0.0, min(100.0, val))
            y = h - (clamped / 100.0 * (h - 8)) - 4
            pts.append((x, y))
            
        if len(pts) >= 2:
            # Fill polygon below line
            poly_pts = [(0, h)] + pts + [(w, h)]
            canvas.create_polygon(poly_pts, fill=fill_color, stipple="gray25", outline="")
            
            # Smooth line
            flat_pts = [coord for pt in pts for coord in pt]
            canvas.create_line(flat_pts, fill=line_color, width=2, smooth=True)
            
            # Highlight latest point
            last_x, last_y = pts[-1]
            canvas.create_oval(last_x - 3, last_y - 3, last_x + 3, last_y + 3, fill=line_color, outline="#ffffff")

    def destroy(self):
        self.is_running = False
        super().destroy()

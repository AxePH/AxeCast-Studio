import os
import psutil
import threading
import time

class ResourceMonitor:
    """Monitors CPU, RAM, and Disk usage of AxeCast and its sub-processes in real-time."""
    
    def __init__(self, update_interval: float = 1.5):
        self.interval = update_interval
        self.is_running = False
        self.thread = None
        
        self.cpu_pct = 0.0
        self.ram_mb = 0.0
        self.disk_mb = 0.0
        self.gpu_str = "< 1%"
        
        self.process = psutil.Process(os.getpid())
        # Prime cpu measurement
        self.process.cpu_percent()

    def start(self, on_update=None):
        if self.is_running:
            return
        self.is_running = True
        
        def loop():
            while self.is_running:
                try:
                    # Gather current process + children (adb, mirror engine, etc.)
                    procs = [self.process]
                    try:
                        procs.extend(self.process.children(recursive=True))
                    except Exception:
                        pass
                        
                    total_cpu = 0.0
                    total_ram = 0.0
                    total_io = 0
                    
                    for p in procs:
                        try:
                            total_cpu += p.cpu_percent()
                            total_ram += p.memory_info().rss
                            if hasattr(p, "io_counters"):
                                io = p.io_counters()
                                if io:
                                    total_io += (io.read_bytes + io.write_bytes)
                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                            pass
                            
                    # Normalized CPU for system cores
                    cpu_count = psutil.cpu_count() or 1
                    norm_cpu = total_cpu / cpu_count
                    
                    self.cpu_pct = max(0.1, norm_cpu)
                    # GPU activity estimation based on active hardware rendering and video decoding subprocesses
                    has_active_engine = len(procs) > 1
                    base_gpu = 1.2 if has_active_engine else 0.4
                    self.gpu_pct = min(100.0, max(0.2, (norm_cpu * 0.8) + base_gpu))
                    
                    self.ram_mb = total_ram / (1024 * 1024)
                    self.disk_mb = total_io / (1024 * 1024)
                    
                    if on_update:
                        on_update(self.cpu_pct, self.gpu_pct, self.ram_mb, self.disk_mb)
                except Exception:
                    pass
                    
                time.sleep(self.interval)
                
        self.thread = threading.Thread(target=loop, daemon=True)
        self.thread.start()

    def stop(self):
        self.is_running = False

    def get_stats(self) -> dict:
        return {
            "cpu": f"{self.cpu_pct:.1f}%",
            "ram": f"{self.ram_mb:.0f} MB",
            "disk": f"{self.disk_mb:.1f} MB"
        }

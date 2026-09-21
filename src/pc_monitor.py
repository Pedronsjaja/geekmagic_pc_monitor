from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import os
import platform
import re
import socket
import subprocess
import sys
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

import psutil
import requests
from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config.json"
EXAMPLE_CONFIG_PATH = ROOT / "config.example.json"
STATE_PATH = ROOT / ".pcmon_state.json"
PREVIEW_PATH = ROOT / "preview.jpg"


DEFAULT_PERFORMANCE_PROCESSES = {
    # Autodesk / CAD / CAE
    "inventor.exe",
    "inventorserverhost.exe",
    "fusion360.exe",
    "fusion.exe",
    "acad.exe",
    "revit.exe",
    "3dsmax.exe",

    # 3D / rendering
    "blender.exe",
    "freecad.exe",
    "sldworks.exe",
    "maya.exe",
    "keyshot.exe",
    "unrealeditor.exe",
    "unity.exe",
    "godot.exe",

    # Slicers / impressão 3D
    "ultimaker-cura.exe",
    "cura.exe",
    "prusaslicer.exe",
    "orcaslicer.exe",
    "bambu-studio.exe",
    "bambustudio.exe",
    "superslicer.exe",

    # Vídeo / criação
    "resolve.exe",
    "premierepro.exe",
    "afterfx.exe",
}


@dataclass
class Stats:
    cpu: float
    ram: float
    battery: Optional[float]
    charging: Optional[bool]
    ping_ms: Optional[float]
    cpu_temp: Optional[float]
    gpu_load: Optional[float]
    gpu_temp: Optional[float]
    rx_kbps: float
    tx_kbps: float
    local_ip: str
    uptime_hours: float
    os_label: str


class NetRate:
    def __init__(self):
        now = time.monotonic()
        io_stats = psutil.net_io_counters()
        self.t = now
        self.rx = io_stats.bytes_recv
        self.tx = io_stats.bytes_sent

    def sample(self):
        now = time.monotonic()
        io_stats = psutil.net_io_counters()
        dt = max(now - self.t, 0.001)
        rx_kbps = (io_stats.bytes_recv - self.rx) * 8 / dt / 1000
        tx_kbps = (io_stats.bytes_sent - self.tx) * 8 / dt / 1000
        self.t = now
        self.rx = io_stats.bytes_recv
        self.tx = io_stats.bytes_sent
        return max(rx_kbps, 0), max(tx_kbps, 0)


def load_config():
    path = CONFIG_PATH if CONFIG_PATH.exists() else EXAMPLE_CONFIG_PATH
    if not path.exists():
        raise FileNotFoundError("config.example.json nao encontrado.")
    cfg = json.loads(path.read_text(encoding="utf-8"))
    return cfg


def save_state(state):
    STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")


def load_state():
    if STATE_PATH.exists():
        try:
            return json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"frames": []}


def local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("1.1.1.1", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "0.0.0.0"


def ping_ms(host: str) -> Optional[float]:
    system = platform.system().lower()
    if system == "windows":
        cmd = ["ping", "-n", "1", "-w", "1200", host]
    else:
        cmd = ["ping", "-c", "1", "-W", "1", host]

    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=3)
        text = (p.stdout or "") + (p.stderr or "")
        # Windows PT/EN and common Unix output
        patterns = [
            r"[=<]\s*(\d+)\s*ms",
            r"time[=<]?\s*(\d+(?:\.\d+)?)\s*ms",
            r"tempo[=<]?\s*(\d+(?:\.\d+)?)\s*ms",
        ]
        for pattern in patterns:
            m = re.search(pattern, text, re.I)
            if m:
                return float(m.group(1))
    except Exception:
        pass
    return None


def windows_nvidia_stats():
    """
    NVIDIA fallback for Windows.
    RTX 3050 and most modern NVIDIA cards expose load/temp through nvidia-smi
    when the NVIDIA driver is installed.
    """
    try:
        p = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=utilization.gpu,temperature.gpu",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=2,
        )
        if p.returncode != 0:
            return None, None

        line = next((x.strip() for x in p.stdout.splitlines() if x.strip()), "")
        if not line:
            return None, None

        parts = [x.strip() for x in line.split(",")]
        gpu_load = float(parts[0]) if len(parts) >= 1 and parts[0] else None
        gpu_temp = float(parts[1]) if len(parts) >= 2 and parts[1] else None
        return gpu_temp, gpu_load
    except Exception:
        return None, None


def windows_hardware_stats():
    """
    Read CPU/GPU sensors on Windows.

    Priority:
      1) LibreHardwareMonitor via WMI
      2) nvidia-smi fallback for NVIDIA GPU load/temp

    This means RTX 3050 activity can still trigger Performance mode even
    if LibreHardwareMonitor is not open.
    """
    cpu_temp = gpu_temp = gpu_load = None
    if platform.system() != "Windows":
        return cpu_temp, gpu_temp, gpu_load

    # LibreHardwareMonitor is optional.
    try:
        import wmi
        c = wmi.WMI(namespace=r"root\LibreHardwareMonitor")
        sensors = c.Sensor()

        cpu_candidates = []
        gpu_temp_candidates = []
        gpu_load_candidates = []

        for s in sensors:
            try:
                name = str(s.Name)
                stype = str(s.SensorType)
                value = float(s.Value)
                parent = str(getattr(s, "Parent", ""))
                lname = (name + " " + parent).lower()

                if stype == "Temperature":
                    if any(k in lname for k in ("cpu", "package", "tctl", "tdie", "core")):
                        cpu_candidates.append(value)
                    if "gpu" in lname:
                        gpu_temp_candidates.append(value)

                if stype == "Load" and "gpu" in lname:
                    gpu_load_candidates.append(value)
            except Exception:
                continue

        if cpu_candidates:
            cpu_temp = max(cpu_candidates)
        if gpu_temp_candidates:
            gpu_temp = max(gpu_temp_candidates)
        if gpu_load_candidates:
            gpu_load = max(gpu_load_candidates)

    except Exception:
        pass

    # NVIDIA driver fallback: especially useful for the RTX 3050.
    if gpu_temp is None or gpu_load is None:
        nv_temp, nv_load = windows_nvidia_stats()
        if gpu_temp is None:
            gpu_temp = nv_temp
        if gpu_load is None:
            gpu_load = nv_load

    return cpu_temp, gpu_temp, gpu_load

def _read_float(path: Path, divisor=1.0):
    try:
        return float(path.read_text().strip()) / divisor
    except Exception:
        return None


def _linux_psutil_cpu_temp():
    """Prefer CPU-related thermal zones exposed through psutil/sysfs."""
    try:
        all_t = psutil.sensors_temperatures(fahrenheit=False)
    except Exception:
        return None

    preferred = ("k10temp", "coretemp", "zenpower", "cpu_thermal", "acpitz")
    candidates = []

    for chip, entries in all_t.items():
        chip_l = chip.lower()
        for entry in entries:
            try:
                value = float(entry.current)
            except Exception:
                continue

            label = (entry.label or "").lower()
            priority = 0
            if any(p in chip_l for p in preferred):
                priority += 3
            if any(k in label for k in ("package", "tctl", "tdie", "cpu", "core")):
                priority += 2
            # Ignore obviously bogus values occasionally exposed by EC drivers.
            if -10 <= value <= 125:
                candidates.append((priority, value))

    if not candidates:
        return None

    best_prio = max(p for p, _ in candidates)
    vals = [v for p, v in candidates if p == best_prio]
    return max(vals)


def _linux_nvidia_stats():
    """Use nvidia-smi when an NVIDIA GPU/driver is present."""
    try:
        p = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=utilization.gpu,temperature.gpu",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=2,
        )
        if p.returncode != 0:
            return None, None
        line = next((x.strip() for x in p.stdout.splitlines() if x.strip()), "")
        if not line:
            return None, None
        parts = [x.strip() for x in line.split(",")]
        load = float(parts[0]) if len(parts) >= 1 and parts[0] else None
        temp = float(parts[1]) if len(parts) >= 2 and parts[1] else None
        return temp, load
    except Exception:
        return None, None


def _linux_drm_gpu_stats():
    """
    Best-effort AMD/Intel GPU telemetry via /sys/class/drm.
    AMD commonly exposes gpu_busy_percent and hwmon temperatures.
    """
    best_temp = None
    best_load = None

    for card in sorted(Path("/sys/class/drm").glob("card[0-9]*")):
        device = card / "device"
        if not device.exists():
            continue

        load = _read_float(device / "gpu_busy_percent")
        if load is not None and 0 <= load <= 100:
            best_load = max(best_load or 0, load)

        for hwmon in device.glob("hwmon/hwmon*"):
            for temp_input in hwmon.glob("temp*_input"):
                temp = _read_float(temp_input, 1000.0)
                if temp is not None and -10 <= temp <= 125:
                    best_temp = max(best_temp or temp, temp)

    return best_temp, best_load


def linux_hardware_stats(cfg):
    """Native Ubuntu/Linux backend. No extra service is required for the basic sensors."""
    if platform.system() != "Linux":
        return None, None, None

    cpu_temp = _linux_psutil_cpu_temp()
    gpu_temp = gpu_load = None

    if cfg.get("enable_nvidia_smi", True):
        gpu_temp, gpu_load = _linux_nvidia_stats()

    if gpu_temp is None or gpu_load is None:
        drm_temp, drm_load = _linux_drm_gpu_stats()
        if gpu_temp is None:
            gpu_temp = drm_temp
        if gpu_load is None:
            gpu_load = drm_load

    return cpu_temp, gpu_temp, gpu_load


def fallback_cpu_temperature():
    """Generic fallback used on non-Linux platforms too."""
    try:
        all_t = psutil.sensors_temperatures(fahrenheit=False)
    except Exception:
        return None

    vals = []
    for entries in all_t.values():
        for entry in entries:
            try:
                value = float(entry.current)
            except Exception:
                continue
            if -10 <= value <= 125:
                vals.append(value)
    return max(vals) if vals else None


def operating_system_label():
    system = platform.system()
    if system == "Windows":
        release = platform.release()
        return f"WIN {release}".upper()
    if system == "Linux":
        # Prefer distro name, e.g. Ubuntu 24.04.
        try:
            os_release = {}
            for line in Path("/etc/os-release").read_text(encoding="utf-8").splitlines():
                if "=" in line:
                    key, value = line.split("=", 1)
                    os_release[key] = value.strip().strip('"')
            name = os_release.get("NAME", "Linux")
            version = os_release.get("VERSION_ID", "")
            if name.lower() == "ubuntu" and version:
                return f"UBUNTU {version}"
            return f"{name} {version}".strip().upper()
        except Exception:
            return "LINUX"
    return system.upper()

def collect_stats(cfg, net_rate: NetRate) -> Stats:
    cpu = psutil.cpu_percent(interval=None)
    ram = psutil.virtual_memory().percent

    battery = None
    charging = None
    try:
        b = psutil.sensors_battery()
        if b:
            battery = float(b.percent)
            charging = bool(b.power_plugged)
    except Exception:
        pass

    cpu_temp = gpu_temp = gpu_load = None
    system = platform.system()

    if system == "Windows":
        if cfg.get("enable_librehardwaremonitor", True):
            cpu_temp, gpu_temp, gpu_load = windows_hardware_stats()

    elif system == "Linux":
        if cfg.get("enable_linux_hwmon", True):
            cpu_temp, gpu_temp, gpu_load = linux_hardware_stats(cfg)

    if cpu_temp is None:
        cpu_temp = fallback_cpu_temperature()

    rx, tx = net_rate.sample()
    uptime_h = (time.time() - psutil.boot_time()) / 3600

    return Stats(
        cpu=cpu,
        ram=ram,
        battery=battery,
        charging=charging,
        ping_ms=ping_ms(cfg.get("ping_host", "1.1.1.1")),
        cpu_temp=cpu_temp,
        gpu_load=gpu_load,
        gpu_temp=gpu_temp,
        rx_kbps=rx,
        tx_kbps=tx,
        local_ip=local_ip(),
        uptime_hours=uptime_h,
        os_label=operating_system_label(),
    )

def bucket(value, step):
    if value is None:
        return None
    step = max(float(step), 0.0001)
    return round(value / step) * step


def bucket_stats(stats: Stats, cfg):
    d = asdict(stats)
    d["cpu"] = bucket(stats.cpu, cfg.get("bucket_cpu", 5))
    d["ram"] = bucket(stats.ram, cfg.get("bucket_ram", 5))
    d["cpu_temp"] = bucket(stats.cpu_temp, cfg.get("bucket_temp", 2))
    d["gpu_temp"] = bucket(stats.gpu_temp, cfg.get("bucket_temp", 2))
    d["gpu_load"] = bucket(stats.gpu_load, cfg.get("bucket_cpu", 5))
    d["ping_ms"] = bucket(stats.ping_ms, cfg.get("bucket_ping", 5))
    d["battery"] = bucket(stats.battery, cfg.get("bucket_battery", 5))
    # Network rates vary wildly. Quantize logarithmically enough to avoid a new image every sample.
    d["rx_kbps"] = round(stats.rx_kbps / 250) * 250
    d["tx_kbps"] = round(stats.tx_kbps / 250) * 250
    d["uptime_hours"] = round(stats.uptime_hours)
    return d


def find_font(size, bold=False):
    candidates = []
    if platform.system() == "Windows":
        win = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
        candidates += [
            win / ("segoeuib.ttf" if bold else "segoeui.ttf"),
            win / ("arialbd.ttf" if bold else "arial.ttf"),
        ]
    candidates += [
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else
             "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
    ]
    for p in candidates:
        if p.exists():
            return ImageFont.truetype(str(p), size=size)
    return ImageFont.load_default()


def text(draw, xy, value, font, fill=(235, 240, 245), anchor=None):
    draw.text(xy, str(value), font=font, fill=fill, anchor=anchor)


def bar(draw, x, y, w, h, value, fill):
    value = max(0, min(100, float(value or 0)))
    draw.rounded_rectangle((x, y, x+w, y+h), radius=h//2, fill=(38, 43, 48))
    fw = int(w * value / 100)
    if fw > 0:
        draw.rounded_rectangle((x, y, x+fw, y+h), radius=h//2, fill=fill)


def fmt_temp(v):
    return "--°" if v is None else f"{int(round(v))}°"


def fmt_ping(v):
    return "--" if v is None else str(int(round(v)))


def fmt_rate(kbps):
    if kbps >= 1000:
        return f"{kbps/1000:.1f}M"
    return f"{int(kbps)}k"


def render_frame(stats_dict, cfg):
    img = Image.new("RGB", (240, 240), (5, 7, 10))
    d = ImageDraw.Draw(img)

    f10 = find_font(10)
    f12 = find_font(12)
    f13b = find_font(13, True)
    f16b = find_font(16, True)
    f24b = find_font(24, True)

    cyan = (55, 205, 235)
    green = (80, 220, 130)
    orange = (255, 175, 60)
    red = (255, 90, 90)
    dim = (140, 150, 160)
    white = (238, 242, 246)

    # Header
    text(d, (12, 8), cfg.get("display_name", "PC MONITOR"), f16b, white)
    os_label = stats_dict.get("os_label", "")
    if cfg.get("show_os_label", True) and os_label:
        text(d, (12, 27), os_label, f10, dim)
    d.ellipse((210, 13, 218, 21), fill=green)
    text(d, (224, 12), "ON", f10, green, anchor="ma")

    cpu = stats_dict.get("cpu") or 0
    ram = stats_dict.get("ram") or 0
    temp = stats_dict.get("cpu_temp")
    gpu = stats_dict.get("gpu_load")
    gpu_temp = stats_dict.get("gpu_temp")

    # CPU
    text(d, (12, 45), "CPU", f13b, cyan)
    text(d, (228, 43), f"{int(cpu)}%", f16b, white, anchor="ra")
    bar(d, 12, 65, 216, 9, cpu, cyan)

    # RAM
    text(d, (12, 84), "RAM", f13b, green)
    text(d, (228, 82), f"{int(ram)}%", f16b, white, anchor="ra")
    bar(d, 12, 104, 216, 9, ram, green)

    # Sensors / network
    text(d, (12, 121), "CPU TEMP", f10, dim)
    text(d, (12, 134), fmt_temp(temp), f24b, orange)

    text(d, (95, 121), "PING", f10, dim)
    text(d, (95, 136), fmt_ping(stats_dict.get("ping_ms")), f16b, white)
    text(d, (126, 139), "ms", f10, dim)

    bat = stats_dict.get("battery")
    text(d, (166, 121), "BATERIA", f10, dim)
    bat_text = "--%" if bat is None else f"{int(bat)}%"
    text(d, (228, 135), bat_text, f16b, green if (bat or 100) > 25 else red, anchor="ra")

    # GPU row if available, otherwise uptime
    if gpu is not None or gpu_temp is not None:
        text(d, (12, 172), "GPU", f10, dim)
        val = "--" if gpu is None else f"{int(gpu)}%"
        text(d, (42, 170), val, f13b, white)
        text(d, (80, 170), fmt_temp(gpu_temp), f13b, orange)
    else:
        text(d, (12, 172), "UPTIME", f10, dim)
        text(d, (58, 170), f"{int(stats_dict.get('uptime_hours', 0))}h", f13b, white)

    text(d, (12, 194), "REDE", f10, dim)
    text(d, (46, 192), f"↓ {fmt_rate(stats_dict.get('rx_kbps', 0))}", f12, cyan)
    text(d, (112, 192), f"↑ {fmt_rate(stats_dict.get('tx_kbps', 0))}", f12, green)

    # Footer
    d.line((12, 215, 228, 215), fill=(40, 45, 50), width=1)
    text(d, (12, 220), stats_dict.get("local_ip", "0.0.0.0"), f10, dim)
    text(d, (228, 220), time.strftime("%H:%M"), f10, dim, anchor="ra")

    return img


class SmallTV:
    def __init__(self, host, timeout=5):
        self.host = host.replace("http://", "").replace("https://", "").strip("/")
        self.base = f"http://{self.host}"
        self.timeout = timeout
        self.s = requests.Session()

    def get(self, path, **kwargs):
        return self.s.get(self.base + path, timeout=self.timeout, **kwargs)

    def info(self):
        result = {}
        for ep in ("/v.json", "/app.json"):
            try:
                r = self.get(ep)
                result[ep] = r.json() if r.ok else {"http": r.status_code}
            except Exception as e:
                result[ep] = {"error": str(e)}
        return result

    def set_theme(self, n):
        return self.get(f"/set?theme={int(n)}")

    def set_brightness(self, value):
        # Stock firmwares differ between 0-100 and 0-255.
        return self.get(f"/set?brt={int(value)}")

    def show_image(self, filename):
        path = f"/image/{filename}"
        return self.get("/set", params={"img": path})

    def delete_image(self, filename):
        path = f"/image/{filename}"
        try:
            return self.get("/delete", params={"file": path})
        except Exception:
            return None

    def filelist(self):
        try:
            return self.get("/filelist?dir=/image").text
        except Exception:
            return ""

    def upload_jpeg(self, filename, jpeg_bytes):
        files = {"file": (filename, jpeg_bytes, "image/jpeg")}
        return self.s.post(
            self.base + "/doUpload?dir=/image/",
            files=files,
            timeout=max(self.timeout, 15),
        )


def jpeg_bytes(img: Image.Image, quality=88):
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality, optimize=True)
    return buf.getvalue()


def digest_for(stats_dict):
    raw = json.dumps(stats_dict, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha1(raw).hexdigest()[:12]


def test_device(tv: SmallTV):
    print(f"Testando http://{tv.host}/")
    try:
        r = tv.get("/")
        print("HTTP /:", r.status_code)
    except Exception as e:
        print("Falha:", e)
        return False

    info = tv.info()
    print(json.dumps(info, indent=2, ensure_ascii=False))
    return True


def discover_one(ip):
    try:
        r = requests.get(f"http://{ip}/v.json", timeout=0.6)
        text = r.text.lower()
        if r.ok and ("ultra" in text or "geekmagic" in text or "smalltv" in text):
            return ip, r.text[:200]
    except Exception:
        pass
    try:
        r = requests.get(f"http://{ip}/app.json", timeout=0.6)
        text = r.text.lower()
        if r.ok and ("ultra" in text or "geekmagic" in text or "smalltv" in text):
            return ip, r.text[:200]
    except Exception:
        pass
    return None


def discover():
    ip = local_ip()
    if ip == "0.0.0.0":
        print("Nao consegui descobrir a rede local.")
        return
    prefix = ".".join(ip.split(".")[:3])
    print(f"Procurando SmallTV em {prefix}.0/24 ...")
    found = []
    with ThreadPoolExecutor(max_workers=32) as ex:
        futs = [ex.submit(discover_one, f"{prefix}.{i}") for i in range(1, 255)]
        for f in as_completed(futs):
            result = f.result()
            if result:
                found.append(result)
                print("Encontrado:", result[0], result[1])
    if not found:
        print("Nenhum SmallTV detectado automaticamente.")
        print("Veja o IP no roteador ou na interface do relogio.")


def cleanup(tv: SmallTV, state):
    frames = state.get("frames", [])
    for item in list(frames):
        fn = item.get("filename")
        if fn and fn.startswith("pcmon_"):
            tv.delete_image(fn)
            print("Removido:", fn)
    state["frames"] = []
    save_state(state)


def trim_cache(tv: SmallTV, state, max_frames: int):
    frames = state.get("frames", [])
    while len(frames) > max_frames:
        item = frames.pop(0)
        fn = item.get("filename")
        if fn:
            tv.delete_image(fn)
    state["frames"] = frames
    save_state(state)



def configured_performance_processes(cfg):
    """
    Built-in heavy apps + user additions from config.json.
    Unknown heavy apps are still detected by CPU/GPU thresholds.
    """
    wanted = set(DEFAULT_PERFORMANCE_PROCESSES)
    for item in cfg.get("performance_processes", []):
        name = str(item).strip().lower()
        if name:
            wanted.add(name)
    return wanted

def active_process_names():
    """Return lower-case executable/process names currently running."""
    names = set()
    try:
        for proc in psutil.process_iter(["name"]):
            try:
                name = (proc.info.get("name") or "").strip().lower()
                if name:
                    names.add(name)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
    except Exception:
        pass
    return names


def performance_trigger(stats: Stats, cfg):
    """
    Decide whether the PC looks 'active enough' to enter Performance mode.

    Triggers:
      - CPU above threshold
      - GPU above threshold (when GPU telemetry is available)
      - configured process is running (e.g. Inventor.exe)
    """
    reasons = []

    cpu_threshold = float(cfg.get("performance_cpu_enter_percent", 20))
    gpu_threshold = float(cfg.get("performance_gpu_enter_percent", 12))

    if stats.cpu >= cpu_threshold:
        reasons.append(f"CPU {stats.cpu:.0f}%")

    if stats.gpu_load is not None and stats.gpu_load >= gpu_threshold:
        reasons.append(f"GPU {stats.gpu_load:.0f}%")

    wanted = configured_performance_processes(cfg)
    if wanted:
        running = active_process_names()
        matched = sorted(wanted & running)
        if matched:
            reasons.append("APP " + ", ".join(matched[:2]))

    return bool(reasons), reasons


def performance_can_exit(stats: Stats, cfg):
    """
    Return True when CPU/GPU are calm and none of the configured
    performance applications is still running.
    """
    cpu_exit = float(cfg.get("performance_cpu_exit_percent", 8))
    gpu_exit = float(cfg.get("performance_gpu_exit_percent", 5))

    if stats.cpu > cpu_exit:
        return False

    if stats.gpu_load is not None and stats.gpu_load > gpu_exit:
        return False

    wanted = configured_performance_processes(cfg)
    if wanted:
        running = active_process_names()
        if wanted & running:
            return False

    return True

def main():
    parser = argparse.ArgumentParser(description="GeekMagic SmallTV Ultra - PC Monitor")
    parser.add_argument("--discover", action="store_true")
    parser.add_argument("--test", action="store_true")
    parser.add_argument("--preview", action="store_true")
    parser.add_argument("--stock", action="store_true")
    parser.add_argument("--clean", action="store_true")
    args = parser.parse_args()

    if args.discover:
        discover()
        return

    cfg = load_config()
    host = cfg.get("device_host", "").strip()
    if not host:
        print("Defina device_host em config.json")
        raise SystemExit(2)

    tv = SmallTV(host, cfg.get("request_timeout_seconds", 5))
    state = load_state()

    if args.test:
        test_device(tv)
        return

    if args.stock:
        r = tv.set_theme(cfg.get("stock_theme", 1))
        print("Tema original solicitado:", getattr(r, "status_code", "?"))
        return

    if args.clean:
        cleanup(tv, state)
        return

    net = NetRate()
    # Warm-up cpu_percent and network rate
    psutil.cpu_percent(interval=None)
    time.sleep(1)
    stats = collect_stats(cfg, net)
    bstats = bucket_stats(stats, cfg)
    img = render_frame(bstats, cfg)

    if args.preview:
        img.save(PREVIEW_PATH, "JPEG", quality=92)
        print("Preview salvo em:", PREVIEW_PATH)
        return

    print("Iniciando PC Monitor")
    print("Sistema:", operating_system_label())
    if platform.system() == "Linux":
        print("Backend de sensores: Linux sysfs/psutil + nvidia-smi quando disponivel")
    elif platform.system() == "Windows":
        print("Backend de sensores: psutil + LibreHardwareMonitor quando disponivel")
    print("SmallTV:", host)
    print("Ctrl+C para encerrar")

    auto_mode = bool(cfg.get("auto_performance_mode", True))
    print("Modo automatico:", "ATIVO" if auto_mode else "DESATIVADO")
    if auto_mode:
        print(
            "Entrada desempenho: CPU >=",
            cfg.get("performance_cpu_enter_percent", 20),
            "% | GPU >=",
            cfg.get("performance_gpu_enter_percent", 12),
            "%"
        )
        print(
            "Saida desempenho apos",
            cfg.get("performance_exit_cooldown_seconds", 12),
            "s em baixa carga."
        )

    last_digest = None
    last_push = 0.0

    # State machine:
    # clock -> stock SmallTV clock/weather theme
    # performance -> our PC performance dashboard
    mode = "clock" if auto_mode else "performance"
    enter_since = None
    exit_since = None

    try:
        if mode == "clock":
            tv.set_theme(cfg.get("stock_theme", 1))
            print("Tela atual: RELOGIO")
        else:
            tv.set_theme(cfg.get("photo_theme", 3))
            tv.set_brightness(cfg.get("brightness", 80))
            print("Tela atual: DESEMPENHO")

        while True:
            stats = collect_stats(cfg, net)
            now = time.monotonic()

            if auto_mode:
                wants_perf, reasons = performance_trigger(stats, cfg)

                if mode == "clock":
                    exit_since = None
                    if wants_perf:
                        if enter_since is None:
                            enter_since = now
                            print("Atividade detectada:", " | ".join(reasons))
                        hold = float(cfg.get("performance_enter_hold_seconds", 4))
                        if now - enter_since >= hold:
                            mode = "performance"
                            enter_since = None
                            last_digest = None
                            last_push = 0.0
                            tv.set_theme(cfg.get("photo_theme", 3))
                            tv.set_brightness(cfg.get("brightness", 80))
                            print(">>> Tela: DESEMPENHO")
                    else:
                        enter_since = None

                elif mode == "performance":
                    enter_since = None
                    if performance_can_exit(stats, cfg):
                        if exit_since is None:
                            exit_since = now
                        cooldown = float(
                            cfg.get("performance_exit_cooldown_seconds", 12)
                        )
                        if now - exit_since >= cooldown:
                            mode = "clock"
                            exit_since = None
                            last_digest = None
                            tv.set_theme(cfg.get("stock_theme", 1))
                            print("<<< Tela: RELOGIO")
                    else:
                        exit_since = None

            if mode == "performance":
                bstats = bucket_stats(stats, cfg)
                dg = digest_for(bstats)
                min_interval = float(cfg.get("push_interval_seconds", 60))

                if dg != last_digest and (
                    now - last_push >= min_interval or last_digest is None
                ):
                    filename = f"pcmon_{dg}.jpg"

                    known = {
                        x.get("digest"): x
                        for x in state.get("frames", [])
                    }

                    if dg in known:
                        print("Reutilizando frame:", known[dg]["filename"])
                        tv.set_theme(cfg.get("photo_theme", 3))
                        tv.show_image(known[dg]["filename"])
                    else:
                        img = render_frame(bstats, cfg)
                        data = jpeg_bytes(img, quality=88)

                        print(
                            f"Atualizando desempenho | CPU {bstats['cpu']}% "
                            f"RAM {bstats['ram']}% GPU {bstats.get('gpu_load')} "
                            f"ping {bstats['ping_ms']} ms"
                        )
                        r = tv.upload_jpeg(filename, data)

                        if not r.ok:
                            print(
                                "Upload falhou:",
                                r.status_code,
                                r.text[:200]
                            )
                        else:
                            tv.set_theme(cfg.get("photo_theme", 3))
                            tv.show_image(filename)
                            state.setdefault("frames", []).append({
                                "digest": dg,
                                "filename": filename,
                                "time": time.time()
                            })
                            trim_cache(
                                tv,
                                state,
                                int(cfg.get("max_cached_frames", 25))
                            )

                    last_digest = dg
                    last_push = now

            time.sleep(float(cfg.get("sample_interval_seconds", 2)))

    except KeyboardInterrupt:
        print("\nEncerrando...")
    finally:
        if cfg.get("return_to_stock_on_exit", True):
            try:
                tv.set_theme(cfg.get("stock_theme", 1))
                print("Tema original solicitado.")
            except Exception as e:
                print("Nao consegui restaurar o tema automaticamente:", e)


if __name__ == "__main__":
    main()

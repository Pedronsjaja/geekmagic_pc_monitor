import sys
import json
import time
from pathlib import Path
import requests

ENDPOINTS = [
    "app.json", "v.json", "brt.json", "city.json", "config.json",
    "day.json", "delay.json", "dst.json", "font.json", "hour12.json",
    "ntp.json", "space.json", "theme_list.json", "timebrt.json",
    "timecolor.json", "unit.json", "wifi.json"
]

def main():
    if len(sys.argv) != 2:
        print("Uso: python backup_device.py 192.168.1.42")
        raise SystemExit(2)

    host = sys.argv[1].replace("http://", "").replace("https://", "").strip("/")
    base = f"http://{host}"
    out = Path(time.strftime("backup_%Y%m%d_%H%M%S"))
    out.mkdir()

    session = requests.Session()

    for endpoint in ENDPOINTS:
        try:
            r = session.get(f"{base}/{endpoint}", timeout=4)
            if r.ok:
                (out / endpoint.replace("/", "_")).write_bytes(r.content)
                print(f"[OK] {endpoint}")
            else:
                print(f"[--] {endpoint}: HTTP {r.status_code}")
        except Exception as e:
            print(f"[ERRO] {endpoint}: {e}")

    try:
        r = session.get(f"{base}/filelist?dir=/image", timeout=6)
        if r.ok:
            (out / "filelist_image.html").write_bytes(r.content)
            print("[OK] filelist?dir=/image")
    except Exception as e:
        print(f"[ERRO] filelist: {e}")

    print(f"\nBackup salvo em: {out.resolve()}")
    print("Obs.: isto NAO e um dump do firmware/flash.")

if __name__ == "__main__":
    main()

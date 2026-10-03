# probe_ble.py - 检查 BLE 支持
import sys

print("MicroPython:", sys.version)
print("-" * 40)
try:
    import bluetooth
    print("bluetooth module: OK")
    print("  attrs:", [n for n in dir(bluetooth) if not n.startswith("_")])
except ImportError as e:
    print("bluetooth module: MISSING ->", e)
except Exception as e:
    print("bluetooth import error:", repr(e))

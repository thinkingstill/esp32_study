# probe_temp.py - 排查 CPU 温度读取
import esp32
import machine

print("esp32 module attrs with 'temp':")
for name in dir(esp32):
    if "temp" in name.lower():
        print("  -", name)

print("-" * 40)
try:
    v = esp32.raw_temperature()
    print("raw_temperature() =", v)
except Exception as e:
    print("raw_temperature() ERROR:", repr(e))

print("-" * 40)
try:
    v = esp32.mcu_temperature()
    print("mcu_temperature() =", v)
except Exception as e:
    print("mcu_temperature() ERROR:", repr(e))

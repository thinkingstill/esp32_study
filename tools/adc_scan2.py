# adc_scan2.py - 扩展扫描 GPIO11..20，寻找电池采样引脚
# ESP32-S3 的 ADC1 理论上可映射到 GPIO1..10，但部分引脚(11..20)可能复用
import machine
import time

def read_adc(gpio):
    adc = machine.ADC(machine.Pin(gpio))
    adc.atten(machine.ADC.ATTN_11DB)
    total = 0
    n = 16
    for _ in range(n):
        total += adc.read_u16()
        time.sleep_ms(5)
    raw = total // n
    return raw, raw / 65535 * 3.3

print("=" * 50)
print("ADC Extended Scan (GPIO11..20)")
print("=" * 50)

for gpio in range(11, 21):
    try:
        raw, volt = read_adc(gpio)
        flag = ""
        if raw == 65535:
            flag = " (full/pullup)"
        elif raw == 0:
            flag = " (gnd)"
        elif 10000 < raw < 60000:
            flag = "  <-- MID, suspect battery!"
        print("GPIO%-3d: raw=%-5d  approx=%.3fV%s" % (gpio, raw, volt, flag))
    except Exception as e:
        print("GPIO%-3d: SKIP (%s)" % (gpio, e))

print("=" * 50)

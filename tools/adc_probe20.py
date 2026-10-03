# adc_probe20.py - 连续采样 GPIO20，观察是否随供电状态变化
import machine
import time

adc = machine.ADC(machine.Pin(20))
adc.atten(machine.ADC.ATTN_11DB)

print("GPIO20 continuous sampling (every 1s)")
print("-" * 40)
for i in range(10):
    total = 0
    for _ in range(8):
        total += adc.read_u16()
        time.sleep_ms(10)
    raw = total // 8
    volt = raw / 65535 * 3.3
    print("t=%ds  raw=%-5d  %.3fV" % (i, raw, volt))
    time.sleep(1)

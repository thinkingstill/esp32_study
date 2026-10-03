# adc_scan.py - 遍历 ESP32-S3 ADC1 所有通道，读取原始值并换算电压
# 用于定位电池电压采样引脚
import machine
import time

try:
    from esp32 import ADC
except ImportError:
    ADC = None

def scan():
    print("=" * 50)
    print("ADC1 Channel Scan")
    print("=" * 50)

    # 直接遍历 ADC1 通道 0..9，使用 machine.ADC 指定引脚
    # ESP32-S3 ADC1: GPIO1..10 (部分被占用)
    pins = {
        "CH0": 1, "CH1": 2, "CH2": 3, "CH3": 4, "CH4": 5,
        "CH5": 6, "CH6": 7, "CH7": 8, "CH8": 9, "CH9": 10,
    }

    for name, gpio in pins.items():
        try:
            adc = machine.ADC(machine.Pin(gpio))
            adc.atten(machine.ADC.ATTN_11DB)  # 最大量程 ~3.3V
            # 多次采样取平均，稳定读数
            total = 0
            n = 16
            for _ in range(n):
                total += adc.read_u16()
                time.sleep_ms(5)
            raw = total // n
            voltage = raw / 65535 * 3.3  # 粗略换算，11DB 衰减约 3.1V 满量程
            print("GPIO%-2d (%s): raw=%-5d  approx=%.3fV" % (gpio, name, raw, voltage))
        except Exception as e:
            print("GPIO%-2d (%s): SKIP (%s)" % (gpio, name, e))

    print("=" * 50)

scan()

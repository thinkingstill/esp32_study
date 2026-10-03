# probe_ble_adv.py - 让板子广播，验证 BLE 外设模式是否正常
import bluetooth
import time

BLE_FLAG_READ = 0x0002
BLE_FLAG_NOTIFY = 0x0010

_IRQ_CENTRAL_CONNECT = 1
_IRQ_CENTRAL_DISCONNECT = 2

# 一个简单的 GATT 服务 + 特征
_SERVICE_UUID = bluetooth.UUID("6E400001-B5A3-F393-E0A9-E50E24DCCA9E")
_CHAR_UUID = bluetooth.UUID("6E400002-B5A3-F393-E0A9-E50E24DCCA9E")

ble = bluetooth.BLE()
ble.active(True)

connected = False

def irq(event, data):
    global connected
    if event == _IRQ_CENTRAL_CONNECT:
        connected = True
        print("central connected:", data)
    elif event == _IRQ_CENTRAL_DISCONNECT:
        connected = False
        print("central disconnected:", data)

ble.irq(irq)

# 注册服务
char = (_CHAR_UUID, BLE_FLAG_READ | BLE_FLAG_NOTIFY,)
service = (_SERVICE_UUID, (char,),)
((handle_char,),) = ble.gatts_register_services((service,))
print("service registered, char handle =", handle_char)

# 设置广播数据(名称 + 服务 UUID)
name = "ESP32S3-D1"
adv_payload = bytearray(b"\x02\x01\x06")  # flags: LE General Discoverable
name_bytes = name.encode()
adv_payload += bytes([len(name_bytes) + 1, 0x09]) + name_bytes  # 0x09 = complete local name

ble.gap_advertise(100000, adv_data=adv_payload)
print("advertising as '%s' ..." % name)

print("scan me with your phone now. press Ctrl+C to stop.")
try:
    while True:
        time.sleep(1)
        print("  advertising... connected=%s" % connected)
except KeyboardInterrupt:
    ble.gap_advertise(None)
    print("stopped advertising")

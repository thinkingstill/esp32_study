# probe_ble_scan5.py - 打印所有 IRQ 事件，确认事件是否送达
import bluetooth
import time

ble = bluetooth.BLE()

def irq(event, data):
    print("IRQ event=%d data=%r" % (event, data))

ble.active(True)
print("active =", ble.active())

ble.irq(irq)
print("irq registered after active")

time.sleep(1)

print("gap_scan(4000) ...")
ble.gap_scan(4000, 30000, 30000, True)
print("gap_scan returned")

time.sleep(1)
print("done. (if you saw NO 'IRQ event=' lines, irq dispatch is broken)")

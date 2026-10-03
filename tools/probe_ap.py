import network
ap = network.WLAN(network.AP_IF)
print("AP active:", ap.active())
try:
    print("AP config:", ap.config("essid"))
except Exception as e:
    print("AP config err:", repr(e))
try:
    print("AP ifconfig:", ap.ifconfig())
except Exception as e:
    print("AP ifconfig err:", repr(e))
try:
    s = ap.status("stations")
    print("AP stations:", s, "type:", type(s))
except Exception as e:
    print("AP stations err:", repr(e))

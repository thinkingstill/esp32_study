"""
阿尔法蛋 D1 -> ESP32-S3 开发板 · WiFi + WebSocket 控制服务端 (uasyncio 并发版)
运行环境: MicroPython (ESP32_GENERIC_S3, 8MB PSRAM)
配置: 改 WIFI_SSID / WIFI_PASS；刷入存为 /main.py 开机自启。
"""
import network
import socket
import gc
import time
import json
import binascii
import hashlib
import machine
import uasyncio as asyncio

# ============ 配置区 ============
# 刷入前请改成你自己的 WiFi 名称和密码
WIFI_SSID = "YOUR_WIFI_SSID"
WIFI_PASS = "YOUR_WIFI_PASSWORD"
PORT = 80
# AP 热点默认配置（2.4GHz）
AP_SSID = "ESP32S3-D1"
AP_PASS = "12345678"  # 至少 8 位，建议自行修改
# ================================

sta = None
ap = None


def ws_accept_key(key):
    MAGIC = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
    return binascii.b2a_base64(hashlib.sha1((key + MAGIC).encode()).digest()).decode().strip()


def ws_send(w, data, opcode=0x1):
    """同步写一帧(不含 drain, 由调用方 await writer.drain())"""
    if isinstance(data, str):
        data = data.encode()
    n = len(data)
    if n < 126:
        w.write(bytes([0x80 | opcode, n]) + data)
    elif n < 65536:
        w.write(bytes([0x80 | opcode, 126]) + n.to_bytes(2, "big") + data)
    else:
        w.write(bytes([0x80 | opcode, 127]) + n.to_bytes(8, "big") + data)


async def ws_read(w):
    """读一个帧，返回 (opcode, payload_bytes) 或 (None, None)"""
    try:
        h = await w.read(2)
    except Exception:
        return None, None
    if not h or len(h) < 2:
        return None, None
    b0, b1 = h[0], h[1]
    opcode = b0 & 0x0F
    masked = (b1 & 0x80) != 0
    length = b1 & 0x7F
    if length == 126:
        ext = await w.read(2)
        length = int.from_bytes(ext, "big")
    elif length == 127:
        ext = await w.read(8)
        length = int.from_bytes(ext, "big")
    mask = await w.read(4) if masked else None
    payload = b""
    while len(payload) < length:
        chunk = await w.read(min(1024, length - len(payload)))
        if not chunk:
            break
        payload += chunk
    if masked:
        payload = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
    return opcode, payload


def reply(msg_type, payload):
    return json.dumps({"type": msg_type, "data": payload, "ts": time.ticks_ms()})


def get_flash_space():
    """查内置 flash 文件系统空间"""
    try:
        import os as _os
        st = _os.statvfs("/")
        total = st[0] * st[2]      # f_bsize * f_blocks
        free = st[0] * st[3]       # f_bsize * f_bfree
        return {"total": total, "free": free, "used": total - free}
    except Exception as e:
        return {"error": repr(e)}


# 电池采样引脚：GPIO20 (ADC1)，经分压接入，采样值在 2.8~3.3V 间波动
BAT_PIN = 20
_bat_adc = None


def get_battery():
    """读 GPIO20 电池采样，多次采样取平均，返回采样电压(未经分压换算)"""
    global _bat_adc
    try:
        if _bat_adc is None:
            _bat_adc = machine.ADC(machine.Pin(BAT_PIN))
            _bat_adc.atten(machine.ADC.ATTN_11DB)
        total = 0
        n = 16
        for _ in range(n):
            total += _bat_adc.read_u16()
            time.sleep_ms(3)
        raw = total // n
        volt = raw / 65535 * 3.3
        return {
            "pin": BAT_PIN,
            "raw": raw,
            "adc_v": round(volt, 3),
            "note": "采样值(未换算真实电压)",
        }
    except Exception as e:
        return {"error": repr(e)}


def scan_wifi():
    """扫描周边 WiFi AP。注意：会短暂影响当前连接，扫完自动恢复。"""
    try:
        import network as _net
        w = _net.WLAN(_net.STA_IF)
        aps = w.scan()  # 阻塞式，返回 [(ssid, bssid, channel, rssi, authmode, hidden), ...]
        out = []
        for ap in aps:
            try:
                ssid = ap[0].decode("utf-8", "replace")
            except Exception:
                ssid = str(ap[0])
            out.append({
                "ssid": ssid,
                "rssi": ap[3],
                "channel": ap[2],
                "authmode": ap[4],
                "hidden": bool(ap[5]),
            })
        # 按 RSSI 降序排序
        out.sort(key=lambda x: x["rssi"], reverse=True)
        return {"count": len(out), "aps": out}
    except Exception as e:
        return {"error": repr(e)}


_IRQ_SCAN_RESULT = 5
_IRQ_SCAN_DONE = 6
_ble = None
_ble_results = []
_ble_scanning = False


def _ble_irq(event, data):
    global _ble_scanning
    if event == _IRQ_SCAN_RESULT:
        try:
            addr_type, addr, adv_type, rssi, adv_data = data
            # addr 和 adv_data 可能是 memoryview，转 bytes
            addr = bytes(addr)
            adv = bytes(adv_data)
            mac = ":".join("%02X" % b for b in addr)
            # 解析名字（0x08 短名 / 0x09 完整名）
            name = ""
            i = 0
            while i < len(adv):
                length = adv[i]
                if length == 0:
                    break
                if i + 1 < len(adv):
                    typ = adv[i + 1]
                    if typ in (0x08, 0x09):
                        try:
                            name = adv[i + 2:i + 1 + length].decode("utf-8", "replace")
                        except Exception:
                            name = ""
                        break
                i += length + 1
            _ble_results.append({
                "name": name,
                "mac": mac,
                "rssi": rssi,
                "adv_type": adv_type,
            })
        except Exception:
            pass
    elif event == _IRQ_SCAN_DONE:
        _ble_scanning = False


def _ble_start_scan():
    """非阻塞启动 BLE 无限扫描，返回 True 或错误信息字符串"""
    global _ble, _ble_results
    import bluetooth
    try:
        if _ble is None:
            _ble = bluetooth.BLE()
            _ble.active(True)
            _ble.irq(_ble_irq)
        _ble_results = []
        _ble.gap_scan(0, 30000, 30000, True)  # 0 = 无限扫描，非阻塞返回
        return True
    except Exception as e:
        return repr(e)


def _ble_stop_scan():
    global _ble
    if _ble is None:
        return
    try:
        _ble.gap_scan(None)
    except Exception:
        pass


def _ble_collect():
    """从 _ble_results 去重合并，返回设备列表"""
    merged = {}
    for r in _ble_results:
        mac = r["mac"]
        if mac not in merged:
            merged[mac] = {"mac": mac, "name": "", "rssi": r["rssi"]}
        if r["name"]:
            merged[mac]["name"] = r["name"]
        if r["rssi"] > merged[mac]["rssi"]:
            merged[mac]["rssi"] = r["rssi"]
    out = list(merged.values())
    out.sort(key=lambda x: x["rssi"], reverse=True)
    return out


async def async_scan_ble():
    """异步 BLE 扫描：非阻塞启动，让事件循环继续跑（IRQ 才能派发），4 秒后停止收集"""
    r = _ble_start_scan()
    if r is not True:
        return {"error": str(r)}
    await asyncio.sleep(4)
    _ble_stop_scan()
    await asyncio.sleep_ms(100)
    out = _ble_collect()
    return {"count": len(out), "devices": out}


_ADV_STATE = {"running": False, "name": "ESP32S3-D1"}


def adv_start(name=None):
    """开始 BLE 广播（广播设备名，可被手机扫描发现）"""
    global _ble
    import bluetooth
    if name and isinstance(name, str) and name.strip():
        _ADV_STATE["name"] = name.strip()
    name_b = _ADV_STATE["name"].encode()
    if _ble is None:
        _ble = bluetooth.BLE()
        _ble.active(True)
    try:
        payload = bytearray(b"\x02\x01\x06")  # flags: LE General Discoverable
        payload += bytes([len(name_b) + 1, 0x09]) + name_b  # complete local name
        _ble.gap_advertise(100000, adv_data=bytes(payload))
        _ADV_STATE["running"] = True
        return {"running": True, "name": _ADV_STATE["name"]}
    except Exception as e:
        return {"error": repr(e)}


def adv_stop():
    global _ble
    if _ble is None:
        _ADV_STATE["running"] = False
        return {"running": False}
    try:
        _ble.gap_advertise(None)
    except Exception:
        pass
    _ADV_STATE["running"] = False
    return {"running": False}


def get_status():
    gc.collect()
    try:
        import esp32
        temp_c = esp32.mcu_temperature()
    except Exception:
        temp_c = -1
    return {
        "uptime_s": int(time.ticks_ms() / 1000),
        "free_heap": gc.mem_free(),
        "alloc_heap": gc.mem_alloc(),
        "cpu_temp_c": temp_c,
        "freq_mhz": machine.freq() // 1000000,
        "ip": sta.ifconfig()[0] if sta.isconnected() else None,
        "rssi": sta.status("rssi") if sta.isconnected() else None,
        "flash": get_flash_space(),
        "battery": get_battery(),
        "ap": get_ap_status(),
    }


def handle(cmd, args):
    cmd = (cmd or "").lower()
    if cmd == "status":
        return reply("status", get_status())
    if cmd == "ping":
        return reply("pong", {"echo": args})
    if cmd == "hello":
        return reply("hello", {"board": "ESP32-S3", "mcu": "alphagg-d1"})
    if cmd == "gc":
        gc.collect()
        return reply("gc", {"free_heap": gc.mem_free()})
    if cmd == "df":
        return reply("df", get_flash_space())
    if cmd == "wifiscan":
        return reply("wifiscan", scan_wifi())
    if cmd == "adv_start":
        return reply("adv", adv_start(args.get("name") if isinstance(args, dict) else None))
    if cmd == "adv_stop":
        return reply("adv", adv_stop())
    if cmd == "adv_status":
        return reply("adv", {"running": _ADV_STATE["running"], "name": _ADV_STATE["name"]})
    if cmd == "ap_start":
        return reply("ap", ap_start(args.get("ssid") if isinstance(args, dict) else None,
                                     args.get("password") if isinstance(args, dict) else None))
    if cmd == "ap_stop":
        return reply("ap", ap_stop())
    if cmd == "ls":
        return reply("ls", do_ls())
    if cmd == "upload":
        return reply("upload", do_upload(args))
    return reply("error", {"msg": "unknown command: %s" % cmd})


def do_ls():
    """列出板子根目录文件"""
    import os as _os
    try:
        files = []
        for name in _os.listdir("/"):
            try:
                st = _os.stat("/" + name)
                files.append({"name": name, "size": st[6]})
            except Exception:
                files.append({"name": name, "size": 0})
        return {"files": files}
    except Exception as e:
        return {"error": repr(e)}


def do_upload(args):
    """通过 base64 上传文件到板子 flash。args: {name, data(base64)}"""
    import binascii
    import os as _os
    if not isinstance(args, dict):
        return {"error": "args must be object"}
    name = args.get("name", "")
    data_b64 = args.get("data", "")
    if not name or not data_b64:
        return {"error": "name or data missing"}
    # 安全：只允许简单文件名，禁止路径穿越
    if "/" in name or "\\" in name or name in (".", ".."):
        return {"error": "invalid filename"}
    try:
        raw = binascii.a2b_base64(data_b64)
    except Exception as e:
        return {"error": "base64 decode failed: %s" % repr(e)}
    if len(raw) > 100 * 1024:  # 限制 100KB
        return {"error": "file too large (max 100KB)"}
    try:
        with open(name, "wb") as f:
            f.write(raw)
        # 如果上传的是 index.html，清缓存让它重新加载
        global _index_cache
        if name == "index.html":
            _index_cache = None
        gc.collect()
        return {"ok": True, "name": name, "size": len(raw)}
    except Exception as e:
        return {"error": "write failed: %s" % repr(e)}


def get_flash_space():
    """查内置 flash 文件系统空间"""
    try:
        import os as _os
        st = _os.statvfs("/")
        total = st[0] * st[2]      # f_bsize * f_blocks
        free = st[0] * st[3]       # f_bsize * f_bfree
        return {
            "total": total,
            "free": free,
            "used": total - free,
        }
    except Exception as e:
        return {"error": repr(e)}


_index_cache = None


def read_index():
    """读板子上的 index.html 返回 bytes。缓存起来避免每次读文件。"""
    global _index_cache
    if _index_cache is not None:
        return _index_cache
    try:
        with open("index.html", "rb") as f:
            _index_cache = f.read()
        return _index_cache
    except Exception:
        return None


async def client_handler(reader, writer):
    try:
        # 读 HTTP 握手
        line = await asyncio.wait_for(reader.readline(), 3)
        if not line:
            return
        headers = {}
        first = line.decode("utf-8", "replace").strip()
        while True:
            l = await asyncio.wait_for(reader.readline(), 3)
            if not l or l in (b"\r\n", b"\n"):
                break
            try:
                k, v = l.decode("utf-8", "replace").split(":", 1)
                headers[k.strip().lower()] = v.strip()
            except Exception:
                pass
        if headers.get("upgrade", "").lower() != "websocket":
            html = read_index()
            if html is not None:
                writer.write(b"HTTP/1.1 200 OK\r\nContent-Type: text/html; charset=utf-8\r\nContent-Length: %d\r\nConnection: close\r\n\r\n" % len(html))
                writer.write(html)
            else:
                body = "index.html not found. Upload board_console.html as index.html to the board."
                writer.write(("HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nContent-Length: %d\r\nConnection: close\r\n\r\n%s" % (len(body), body)).encode())
            await writer.drain()
            return
        key = headers.get("sec-websocket-key", "")
        accept = ws_accept_key(key)
        writer.write(("HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Accept: %s\r\n\r\n" % accept).encode())
        await writer.drain()
        # 握手成功，发 hello
        ws_send(writer, reply("hello", {"board": "ESP32-S3", "free_heap": gc.mem_free()}))
        await writer.drain()
        # 消息循环
        while True:
            op, payload = await ws_read(reader)
            if op is None:
                break
            if op == 0x8:
                break
            if op == 0x9:  # ping -> pong
                ws_send(writer, b"", opcode=0xA)
                await writer.drain()
                continue
            if op == 0x1:
                try:
                    obj = json.loads(payload.decode("utf-8", "replace"))
                    cmd = obj.get("cmd", "")
                    args = obj.get("args", {})
                except Exception:
                    cmd, args = payload.decode("utf-8", "replace").strip(), {}
                if cmd == "blescan":
                    ws_send(writer, reply("blescan", await async_scan_ble()))
                else:
                    ws_send(writer, handle(cmd, args))
                await writer.drain()
    except Exception as e:
        print("[ws] handler error:", repr(e))
        try:
            import sys
            sys.print_exception(e)
        except Exception:
            pass
    finally:
        try:
            writer.close()
        except Exception:
            pass
        gc.collect()


def connect_wifi():
    global sta
    sta = network.WLAN(network.STA_IF)
    sta.active(True)
    if not sta.isconnected():
        print("[board] connecting to", WIFI_SSID)
        sta.connect(WIFI_SSID, WIFI_PASS)
        t0 = time.time()
        while not sta.isconnected() and time.time() - t0 < 20:
            time.sleep(0.3)
    if sta.isconnected():
        print("[board] WiFi OK, IP =", sta.ifconfig()[0])
    else:
        print("[board] WiFi FAILED")


_AP_CURRENT_SSID = AP_SSID


def ap_start(ssid=None, password=None):
    """开启 AP 热点模式。返回热点信息。"""
    global ap, sta, _AP_CURRENT_SSID
    if ssid and isinstance(ssid, str) and ssid.strip():
        ssid = ssid.strip()
    else:
        ssid = AP_SSID
    if password and isinstance(password, str) and password.strip():
        password = password.strip()
    else:
        password = AP_PASS
    try:
        ap = network.WLAN(network.AP_IF)
        # 先关闭再配置再开启，确保 essid/password 真正生效
        ap.active(False)
        ap.active(True)
        ap.config(essid=ssid, password=password, authmode=network.AUTH_WPA_WPA2_PSK)
        # 稍等 AP 起来
        time.sleep(1)
        _AP_CURRENT_SSID = ssid
        ip = ap.ifconfig()[0]
        return {
            "running": True,
            "ssid": ssid,
            "ip": ip,
            "channel": 2.4,
            "clients": "查看不可用",
        }
    except Exception as e:
        return {"error": repr(e)}


def ap_stop():
    global ap
    try:
        if ap is not None:
            ap.active(False)
        ap = None
    except Exception as e:
        return {"error": repr(e)}
    return {"running": False}


def get_ap_status():
    """返回 AP 热点状态 + 已连接设备列表"""
    global ap, _AP_CURRENT_SSID
    try:
        if ap is None or not ap.active():
            return {"running": False}
        stations = ap.status("stations")  # 返回已连接设备的 MAC 列表
        if stations is None:
            stations = ()
        macs = []
        for item in stations:
            # 兼容两种格式：可能是 (mac_bytes,) 的 tuple，或直接是 bytes
            if isinstance(item, (tuple, list)):
                for sub in item:
                    if isinstance(sub, (bytes, bytearray)):
                        macs.append(":".join("%02X" % b for b in sub))
            elif isinstance(item, (bytes, bytearray)):
                macs.append(":".join("%02X" % b for b in item))
        return {
            "running": True,
            "ssid": _AP_CURRENT_SSID,
            "ip": ap.ifconfig()[0],
            "stations": macs,
            "station_count": len(macs),
        }
    except Exception as e:
        return {"error": repr(e)}


async def main():
    connect_wifi()
    # 开机自动开启 AP 热点（STA + AP 共存），手机可随时连入
    r = ap_start()
    if isinstance(r, dict) and r.get("running"):
        print("[board] AP started: %s ip=%s" % (r["ssid"], r["ip"]))
    else:
        print("[board] AP start failed:", r)
    server = await asyncio.start_server(client_handler, "0.0.0.0", PORT, backlog=2)
    sta_ip = sta.ifconfig()[0] if sta.isconnected() else "?"
    ap_ip = ap.ifconfig()[0] if (ap is not None and ap.active()) else "?"
    print("[board] WebSocket server on :%d, sta_ip=%s ap_ip=%s" % (PORT, sta_ip, ap_ip))
    while True:
        await asyncio.sleep(3600)


def run():
    asyncio.run(main())


if __name__ == "__main__":
    run()

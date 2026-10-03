# esp32_study

基于一块**阿尔法蛋 D1 AI 词典笔（碎屏/故障机）改造的 ESP32-S3 开发板**的学习项目。

原设备因屏幕损坏、TF 卡损坏、电池供电链路故障等原因无法正常使用，经排查后将其**废物利用为一块 ESP32-S3 开发板**，刷入 MicroPython，并开发了一套「WiFi + WebSocket」网页控制台。

> ⚠️ 本项目仅供个人学习、硬件研究使用，不含任何原厂固件、逆向产物或私有数据。

## 硬件信息

| 项目 | 内容 |
|------|------|
| 主控 | ESP32-S3（原词典笔主板） |
| Flash | 16MB |
| PSRAM | 8MB |
| 无线 | WiFi（2.4GHz）+ BLE 5.0 |
| 固件 | MicroPython v1.28.0（ESP32_GENERIC_S3） |
| 供电 | USB 供电（原电池供电链路已损坏，仅扫描头一侧有电池） |

> 原设备为「双芯片」架构：ESP32-S3（主控）+ CSK（扫描头 OCR 芯片）。TF 卡、扫描头、电池监测均在 CSK 一侧，与主控无关。

## 目录结构

```
esp32_study/
├── board_server.py       # 板端服务端（WiFi + WebSocket，刷为 /main.py 开机自启）
├── board_console.html    # 网页控制台（单文件，内联 CSS/JS）
├── README.md
└── tools/                # 调试用探针脚本（非必需，仅学习参考）
    ├── adc_scan.py       # ADC1 通道扫描
    ├── adc_scan2.py      # ADC1 扩展扫描（GPIO11~20）
    ├── adc_probe20.py    # GPIO20 电池采样连续采样
    ├── probe_temp.py     # CPU 温度读取探针
    ├── probe_ble.py      # BLE 模块检测
    ├── probe_ble_adv.py  # BLE 广播测试
    ├── probe_ble_scan5.py# BLE 扫描（正确的 irq 用法）
    └── probe_ap.py       # AP 热点状态探测
```

## 快速开始

### 1. 配置 WiFi

编辑 `board_server.py` 顶部的配置区：

```python
WIFI_SSID = "YOUR_WIFI_SSID"
WIFI_PASS = "YOUR_WIFI_PASSWORD"
AP_SSID   = "ESP32S3-D1"     # AP 热点名称
AP_PASS   = "12345678"       # AP 密码（建议修改）
```

### 2. 刷入板子

使用 `mpremote` 刷入（板子通过 USB 串口连接，以 COM6 为例）：

```powershell
# 刷入服务端（存为 main.py 开机自启）
mpremote connect COM6 cp board_server.py :main.py

# 上传网页控制台（板端返回此页面）
mpremote connect COM6 cp board_console.html :index.html

# 复位
mpremote connect COM6 reset
```

> 若报 `could not enter raw repl`：main.py 的循环会占用 REPL，需**拔插 USB**，在板子刚亮起的 1~2 秒内执行 `cp` 命令抢启动窗口。

### 3. 访问控制台

两种方式任选：

- **电脑**：浏览器打开本地 `board_console.html`，输入板子 IP 连接
- **手机**：连板子 AP 热点 `ESP32S3-D1`（密码 `12345678`），浏览器访问 `http://192.168.4.1`（板端已内置网页）

## 功能清单

| 功能 | 说明 |
|------|------|
| 系统状态 | 运行时间 / 内存 / Flash 存储 / CPU 温度 / 主频 / WiFi 信号 |
| 电池采样 | GPIO20 ADC 采样电压（原电池监测在 CSK 侧，此处为分压采样值） |
| WiFi 扫描 | 扫描周边 AP（SSID / 信道 / 加密 / 信号） |
| BLE 扫描 | 扫描周边 BLE 设备（名称 / MAC / 信号） |
| BLE 广播 | 板子广播自定义名称，可被手机扫描 |
| AP 热点 | 2.4GHz 热点，开机自启，手机可直连 |
| 文件管理 | 通过网页上传文件到板子 flash |

## 关键技术笔记

- **CPU 温度**：ESP32-S3 用 `esp32.mcu_temperature()`，非 `raw_temperature()`（后者老 ESP32 才有）
- **BLE 扫描**：必须 `ble.active(True)` 之后**再** `ble.irq(handler)`；`gap_scan` 的 `active` 参数须**位置传参**；在 uasyncio 中须用非阻塞 `gap_scan(0)` + `await asyncio.sleep()` 避免卡死事件循环
- **AP 设备列表**：`ap.status('stations')` 返回 `[(mac_bytes,), ...]` 结构，需正确解包 MAC

## 免责声明

本项目仅为个人学习 ESP32-S3 与 MicroPython 的产物，不包含任何原厂固件、逆向工具或私有数据。请勿将其用于任何违法违规用途。

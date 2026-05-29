# HTTP Interface

本文档描述 `scripts/sim_server.py` 暴露的 HTTP 接口。接口用于局域网内程序启动/停止仿真、读取无人机状态、控制无人机和获取相机图像。

## 基本信息

启动服务：

```bash
python3 scripts/sim_server.py --host 0.0.0.0 --port 18080
```

本机访问：

```text
http://127.0.0.1:18080
```

局域网访问示例：

```text
http://10.246.1.94:18080
```

接口分层：

- `/health`：HTTP 服务健康检查
- `/sim/*`：仿真进程管理
- `/uav/*`：无人机状态、控制和相机

无人机相关接口必须使用 `/uav` 前缀。旧的根路径接口例如 `/state`、`/camera/info`、`/takeoff` 已移除。

除图像接口外，接口返回 `application/json`。POST 请求使用 `Content-Type: application/json`。

## 坐标和单位

局部位置使用 NED 坐标系：

- `n`：North，北向/初始前方，单位 m
- `e`：East，东向/右方，单位 m
- `d`：Down，向下，单位 m
- 高度可用正数 `altitude` 表示，服务端会转换为 `d = -altitude`

机体系速度使用 BODY_NED：

- `vx > 0`：前进，单位 m/s
- `vy > 0`：右移，单位 m/s
- `vz > 0`：下降，单位 m/s
- `vz < 0`：上升，单位 m/s

角度使用弧度，除非字段名明确说明为度。

## 通用错误

未匹配路径返回：

```json
{
  "error": "not_found",
  "path": "/bad/path"
}
```

运行时异常返回：

```json
{
  "error": "RuntimeError",
  "message": "error detail"
}
```

## Health

### GET `/health`

检查 HTTP 服务是否运行，并触发 MAVLink 客户端初始化。

示例：

```bash
curl http://127.0.0.1:18080/health
```

响应：

```json
{
  "ok": true,
  "mavlink_connected": true
}
```

## Simulation

### POST `/sim/start`

启动 PX4 SITL、AirSimNH 和本机 QGC UDP sink。

请求体：

```json
{
  "wait": true,
  "timeout": 120
}
```

字段：

- `wait`：是否等待 PX4 和 AirSim 连接完成，默认 `true`
- `timeout`：等待超时时间，单位 s，默认 `90`

示例：

```bash
curl -X POST http://127.0.0.1:18080/sim/start \
  -H 'Content-Type: application/json' \
  -d '{"wait": true, "timeout": 120}'
```

响应主要字段：

```json
{
  "started": true,
  "ready": true,
  "output": "launcher output",
  "status": {}
}
```

如果仿真已经运行：

```json
{
  "started": false,
  "reason": "already_running",
  "status": {}
}
```

### POST `/sim/stop`

停止 PX4、AirSim 和 QGC UDP sink。

示例：

```bash
curl -X POST http://127.0.0.1:18080/sim/stop
```

响应主要字段：

```json
{
  "stopped": true,
  "returncode": 0,
  "output": "Stopped PX4 and AirSim Blocks if they were running.",
  "status": {}
}
```

### GET `/sim/status`

读取仿真进程、日志和 MAVLink 状态。

示例：

```bash
curl http://127.0.0.1:18080/sim/status
```

响应主要字段：

```json
{
  "running": {
    "px4": [],
    "airsim": [],
    "qgc_udp_sink": []
  },
  "logs": {
    "px4": "logs/px4_*.log",
    "airsim": "logs/airsim_*.log",
    "qgc_udp_sink": "logs/qgc_udp_sink_*.log"
  },
  "mavlink": {}
}
```

## UAV State

### GET `/uav/state`

读取无人机状态、姿态、电池、当前控制 keepalive 和当前位置任务。

示例：

```bash
curl http://127.0.0.1:18080/uav/state
```

响应主要字段：

```json
{
  "connected": true,
  "heartbeat_age_s": 0.12,
  "position_ned": {
    "n": 0.0,
    "e": 0.0,
    "d": -3.0,
    "vx": 0.0,
    "vy": 0.0,
    "vz": 0.0,
    "time": 1780051033.05
  },
  "attitude": {
    "roll": 0.0,
    "pitch": 0.0,
    "yaw": 0.0,
    "rollspeed": 0.0,
    "pitchspeed": 0.0,
    "yawspeed": 0.0,
    "time": 1780051033.08
  },
  "sys_status": {
    "voltage_battery_mv": 16200,
    "current_battery_ca": -100,
    "battery_remaining": 100,
    "time": 1780051031.86
  },
  "offboard_keepalive": false,
  "keepalive_mode": "velocity",
  "position_cmd_ned": null,
  "velocity_cmd_body_ned": [0.0, 0.0, 0.0],
  "command": {}
}
```

### GET `/uav/cmd/current`

读取当前异步位置任务状态。

示例：

```bash
curl http://127.0.0.1:18080/uav/cmd/current
```

状态字段：

- `idle`：无任务
- `active`：任务执行中
- `reached`：已到达目标
- `timeout`：超时未到达
- `canceled`：被新任务或其他控制取消
- `stopped`：被 `/uav/cmd/stop` 停止

响应示例：

```json
{
  "id": 3,
  "type": "goto",
  "status": "active",
  "target": {"n": 5.0, "e": 0.0, "d": -3.0},
  "error_m": 1.2,
  "timeout": 30.0,
  "acceptance": 0.5,
  "speed_mps": 1.0,
  "acceleration_mps2": 0.5,
  "setpoint": {"n": 3.8, "e": 0.0, "d": -3.0},
  "message": "goto running",
  "position_ned": {}
}
```

## UAV Control

### POST `/uav/arm`

解锁无人机。

示例：

```bash
curl -X POST http://127.0.0.1:18080/uav/arm
```

响应：

```json
{"ok": true}
```

### POST `/uav/takeoff`

起飞到指定高度并进入 Offboard 位置保持。

请求体：

```json
{
  "altitude": 3.0,
  "timeout": 30.0
}
```

字段：

- `altitude`：目标高度，正数，单位 m，默认 `3.0`
- `timeout`：等待到达超时时间，单位 s，默认 `30.0`

示例：

```bash
curl -X POST http://127.0.0.1:18080/uav/takeoff \
  -H 'Content-Type: application/json' \
  -d '{"altitude": 3}'
```

响应主要字段：

```json
{
  "ok": true,
  "altitude": 3.0,
  "target": {"n": 0.0, "e": 0.0, "d": -3.0},
  "reached": true,
  "position_ned": {}
}
```

### POST `/uav/land`

切换 PX4 AUTO.LAND 降落。

示例：

```bash
curl -X POST http://127.0.0.1:18080/uav/land
```

响应：

```json
{"ok": true}
```

### POST `/uav/cmd/velocity`

发送机体系速度控制，并维持 Offboard keepalive。

请求体：

```json
{
  "vx": 1.0,
  "vy": 0.0,
  "vz": 0.0,
  "duration": 2.0
}
```

字段：

- `vx`：前后速度，`> 0` 前进，单位 m/s
- `vy`：左右速度，`> 0` 右移，单位 m/s
- `vz`：上下速度，`> 0` 下降，`< 0` 上升，单位 m/s
- `duration`：持续时间，单位 s；大于 0 时执行后自动把速度置 0

示例：

```bash
curl -X POST http://127.0.0.1:18080/uav/cmd/velocity \
  -H 'Content-Type: application/json' \
  -d '{"vx": 1, "vy": 0, "vz": 0, "duration": 2}'
```

响应：

```json
{
  "ok": true,
  "vx": 1.0,
  "vy": 0.0,
  "vz": 0.0,
  "duration": 2.0
}
```

### POST `/uav/cmd/goto`

异步位置控制。接口收到请求后立即返回任务状态，后台持续发送位置 setpoint。

请求体支持绝对目标：

```json
{
  "n": 5.0,
  "e": 0.0,
  "d": -3.0,
  "timeout": 30.0,
  "acceptance": 0.5
}
```

也支持相对位移：

```json
{
  "dn": 5.0,
  "de": 0.0,
  "dd": 0.0,
  "timeout": 30.0,
  "acceptance": 0.5
}
```

也可以用正高度：

```json
{
  "n": 0.0,
  "e": 0.0,
  "altitude": 3.0,
  "timeout": 30.0
}
```

平滑速度曲线：

```json
{
  "dn": 5.0,
  "de": 0.0,
  "dd": 0.0,
  "speed": 1.0,
  "acceleration": 0.5,
  "timeout": 30.0
}
```

字段：

- `n/e/d`：绝对局部 NED 目标，单位 m
- `dn/de/dd`：相对当前局部 NED 位移，单位 m
- `altitude`：正高度，单位 m；提供后优先转换为目标 `d = -altitude`
- `timeout`：任务超时时间，单位 s，默认 `30.0`
- `acceptance`：到达判定半径，单位 m，默认 `0.5`
- `speed`：可选，最大 setpoint 推进速度，单位 m/s
- `acceleration`：可选，setpoint 加减速，单位 m/s^2；传 `speed` 后默认 `0.5`

行为：

- 新的 `/uav/cmd/goto` 会取消旧的 active goto，只保留最新目标
- 不传 `speed` 时直接保持最终目标 setpoint，由 PX4 位置控制器追踪
- 传 `speed` 时服务端使用梯形速度曲线推进 setpoint，可减少起步和到点时姿态晃动

示例：

```bash
curl -X POST http://127.0.0.1:18080/uav/cmd/goto \
  -H 'Content-Type: application/json' \
  -d '{"dn": 5, "de": 0, "dd": 0, "speed": 1.0, "acceleration": 0.5, "timeout": 30}'
```

响应主要字段：

```json
{
  "ok": true,
  "id": 4,
  "type": "goto",
  "status": "active",
  "target": {"n": 5.0, "e": 0.0, "d": -3.0},
  "timeout": 30.0,
  "acceptance": 0.5,
  "speed_mps": 1.0,
  "acceleration_mps2": 0.5,
  "message": "goto accepted",
  "position_ned": {}
}
```

### POST `/uav/cmd/stop`

取消当前位置任务，并在当前位置悬停。

示例：

```bash
curl -X POST http://127.0.0.1:18080/uav/cmd/stop
```

响应主要字段：

```json
{
  "ok": true,
  "type": "stop",
  "status": "stopped",
  "message": "canceled command 4",
  "position_ned": {}
}
```

## UAV Camera

可用相机：

- `front_center`
- `front_right`
- `front_left`
- `bottom_center`
- `back_center`
- `front_down`
- `0` 到 `4`：AirSim 默认相机编号

当前 Scene 图像默认分辨率为 `640x480`。`front_down` 是前下视相机，相对机体俯角 `-35` 度。

### GET `/uav/camera/info`

抓取一帧 Scene 图像并返回元信息。

查询参数：

- `camera`：相机名或编号，默认 `0`
- `vehicle`：AirSim vehicle name，默认 `PX4`

示例：

```bash
curl "http://127.0.0.1:18080/uav/camera/info?camera=front_down"
```

响应：

```json
{
  "ok": true,
  "width": 640,
  "height": 480,
  "camera": "front_down",
  "vehicle_name": "PX4",
  "time": 1780051185.16,
  "bytes": 528096
}
```

### GET `/uav/camera/scene.png`

抓取一帧 Scene PNG 图像。

查询参数：

- `camera`：相机名或编号，默认 `0`
- `vehicle`：AirSim vehicle name，默认 `PX4`

示例：

```bash
curl "http://127.0.0.1:18080/uav/camera/scene.png?camera=front_down" \
  --output logs/front_down.png
```

响应头包含：

- `Content-Type: image/png`
- `X-Image-Width`
- `X-Image-Height`
- `X-Camera`
- `X-Vehicle-Name`

### GET `/uav/camera/stream.mjpg`

MJPEG 视频流接口。服务端持续抓取 AirSim PNG 图像，并转换为 JPEG multipart stream。

查询参数：

- `camera`：相机名或编号，默认 `0`
- `vehicle`：AirSim vehicle name，默认 `PX4`
- `fps`：帧率，范围 `1` 到 `30`，默认 `10`
- `quality`：JPEG 质量，范围 `1` 到 `95`，默认 `80`

示例：

```text
http://127.0.0.1:18080/uav/camera/stream.mjpg?camera=front_down&fps=10&quality=80
```

浏览器可以直接打开该 URL。OpenCV、ffmpeg 或其他 HTTP client 也可以消费该 multipart stream。

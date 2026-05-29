# PX4 + AirSim 仿真部署

这个目录作为 PX4 AirSim 仿真环境的部署入口。当前先只处理仿真环境，不接接口代码。

## 当前机器状态

- 系统：Ubuntu 22.04
- 已存在 AirSim：`/home/uav/DataDisk/PAB/AirSim`
- 已存在 Unreal Engine：`/home/uav/DataDisk/PAB/UnrealEngine`
- 已存在 AirSim Blocks 4.27 工程：`/home/uav/DataDisk/PAB/AirSim/Unreal/Environments/Blocks 4.27/Blocks.uproject`
- PX4 源码和 SITL 构建产物位于本目录的 `PX4-Autopilot/`

## 部署顺序

先检查环境：

```bash
scripts/check_env.sh
```

下载 PX4 源码。默认使用 AirSim 文档中较保守的 `v1.11.3`，如果要切换版本，可以设置 `PX4_REF`：

```bash
scripts/setup_px4.sh
```

如果 PX4 依赖还没装过，运行 PX4 自带的 Ubuntu 依赖脚本：

```bash
bash PX4-Autopilot/Tools/setup/ubuntu.sh --no-nuttx --no-sim-tools
```

构建 PX4 SITL：

```bash
scripts/build_px4_sitl.sh
```

在 Ubuntu 22.04 上构建 PX4 `v1.11.3` 时，`platforms/common/px4_work_queue/WorkQueueManager.cpp` 需要一个类型兼容补丁；本目录已经对已下载的 PX4 源码做了最小修改，把 `PTHREAD_STACK_MIN` 和 `PX4_STACK_ADJUSTED(...)` 都转为 `size_t`。

安装 AirSim 的 PX4 SITL 配置到 `~/Documents/AirSim/settings.json`：

```bash
scripts/install_settings.sh
```

修改无人机仿真出生位置：

```bash
scripts/set_spawn_pose.py --x 20 --y 5 --z 0 --yaw 0
```

坐标使用 AirSim NED：`X` 北向/前方，`Y` 东向/右方，`Z` 向下，`Yaw` 为初始航向角度。`Z: 0` 表示地面出生，`Z: -2` 表示空中 2 米。只查看当前配置可以不传参数：

```bash
scripts/set_spawn_pose.py
```

修改后安装到 AirSim 实际读取的 `~/Documents/AirSim/settings.json`：

```bash
scripts/set_spawn_pose.py --x 20 --y 5 --z 0 --yaw 0 --install
```

安装后需要重启仿真才会生效。

## 标准启动/停止流程

阶段 3 之后推荐使用统一脚本启动、检查和停止仿真。

启动完整仿真：

```bash
scripts/run_sim.sh
```

这个脚本会：

- 后台启动 PX4 SITL
- 等待几秒后启动 AirSim Blocks
- 默认把 AirSim 显示到 `:0`
- 默认使用 NVIDIA GPU index 0
- 将日志写入 `logs/`

检查当前状态：

```bash
scripts/status_sim.sh
```

停止完整仿真：

```bash
scripts/stop_sim.sh
```

如果需要调试，也可以继续使用手动两终端方式。第一个终端启动 PX4 SITL：

```bash
scripts/run_px4_sitl.sh
```

看到类似下面的输出后，PX4 正在等待 AirSim：

```text
INFO  [simulator] Waiting for simulator to connect on TCP port 4560
```

第二个终端启动 AirSim Blocks：

```bash
scripts/run_blocks.sh
```

`scripts/run_blocks.sh` 默认在 `:0` 上使用 NVIDIA PRIME offload，并固定到 nvidia-smi 的 GPU index 0。当前映射为：

- GPU 0：`NVIDIA-G0`
- GPU 1：`NVIDIA-G1`

如果要临时关闭 NVIDIA offload：

```bash
USE_NVIDIA_OFFLOAD=0 scripts/run_blocks.sh
```

如果要临时切到 1 卡：

```bash
NVIDIA_OFFLOAD_PROVIDER=NVIDIA-G1 UE_GRAPHICS_ADAPTER=1 scripts/run_blocks.sh
```

如果是在纯 SSH 终端里运行，UE 可能报 `Could not initialize SDL: No available video device`。这表示当前会话没有 X/Wayland 图形显示。当前只要求在本机已有图形桌面 `:0` 上运行仿真，因此使用：

本机当前存在 X11 屏幕 `:0`，脚本会在未设置 `DISPLAY` 时自动使用：

```bash
DISPLAY=:0 XAUTHORITY=/run/user/1000/gdm/Xauthority scripts/run_blocks.sh
```

如果是在 `:0` 的 NoMachine/桌面终端里执行，通常直接运行下面命令即可：

```bash
scripts/run_blocks.sh
```

需要真实窗口和 GPU 加速时，统一使用本机桌面、NoMachine 或其他连接到 `:0` 的图形会话。

如果只是临时验证“没有显示设备时能否启动”，可以安装 `xvfb` 后尝试：

```bash
scripts/run_blocks_xvfb.sh
```

注意：`xvfb` 只解决“没有显示设备”的问题，不等同于完整 GPU 渲染能力。

连接成功后，PX4 终端通常会出现：

```text
INFO  [simulator] Simulator connected on TCP port 4560.
INFO  [ecl/EKF] GPS checks passed
INFO  [ecl/EKF] starting GPS fusion
```

AirSim 日志通常会出现：

```text
Connected to SITL over TCP.
received first heartbeat
Got GPS lock
```

停止 PX4：

```bash
scripts/stop_px4.sh
```

停止 AirSim Blocks：

```bash
scripts/stop_blocks.sh
```

## 地图选择

当前稳定可直接运行的是 AirSim 官方 Blocks 4.27 环境：

```text
/home/uav/DataDisk/PAB/AirSim/Unreal/Environments/Blocks 4.27/Blocks.uproject
/Game/FlyingCPP/Maps/FlyingExampleMap
```

原因是它已经包含 AirSim 插件、AirSim GameMode 和 PX4 SITL 桥接，适合先验证无人机仿真链路。之前临时创建的 `LowAltitudeInspection` 自建地图工程已经删除，避免继续出现自建 GameMode、Lighting rebuild 等问题。

园区巡检优先使用官方预编译的 Neighborhood 环境。AirSim 官方 Linux release 里对应名称是 `AirSimNH`，说明为 small urban neighborhood block。下载 `AirSimNH.zip` 后建议解压到：

```text
/home/uav/DataDisk/PAB/AirSimPrebuilt/AirSimNH/
```

解压后目录里应该有类似 `AirSimNH.sh` 的启动脚本；官方包可能会解压成 `AirSimNH/AirSimNH/LinuxNoEditor/AirSimNH.sh` 这种内层结构，脚本会自动查找。单独启动 Neighborhood：

```bash
scripts/run_neighborhood.sh
```

如果启动脚本放在其他位置，可以传路径：

```bash
AIRSIM_ENV=/path/to/AirSimNH.sh scripts/run_neighborhood.sh
```

完整 PX4 + Neighborhood 联动启动：

```bash
START_QGC_UDP_SINK=1 AIRSIM_LAUNCHER=scripts/run_neighborhood.sh AIRSIM_NAME=AirSimNH scripts/run_sim.sh
```

`START_QGC_UDP_SINK=1` 会启动一个本机 UDP `14550` 占位监听器。旧版官方 `AirSimNH` 在没有 QGroundControl 监听 `14550` 时可能因为 UDP `ECONNREFUSED` 崩溃；这个占位监听器只丢弃发往 QGC 的数据，不影响 AirSim 和 PX4 的 TCP/UDP 控制链路。

之前临时创建的 `LowAltitudeInspection` 自建地图工程已经删除，避免继续出现自建 GameMode、Lighting rebuild 等问题。

## 端口配置

`configs/settings_px4_sitl.json` 使用 AirSim PX4 SITL 的常见端口：

- TCP `4560`：AirSim 等待 PX4 simulator 连接
- UDP local `14540` / remote `14580`：PX4 控制通道
- UDP `14550`：QGroundControl 默认端口

单机部署保持 `127.0.0.1` 即可。如果 PX4 和 AirSim 分机器运行，再修改 `LocalHostIp`、`ControlIp` 和 PX4 的 `PX4_SIM_HOST_ADDR`。

## 手动控制

起飞、降落可以在 PX4 控制台 `pxh>` 中输入：

```bash
commander arm
commander takeoff
commander land
```

前后左右移动建议使用 MAVLink Offboard 速度控制。安装 `pymavlink` 后运行：

```bash
python3 scripts/keyboard_offboard_control.py
```

默认连接 PX4 的 `14280 -> 14030` MAVLink Onboard 通道，不占用 AirSim 的 `14540/14580` 控制链路。

自动巡检矩形航线：

```bash
python3 scripts/auto_inspection_route.py
```

默认起飞到 3 米，按 NED 坐标飞一个 `8m x 5m` 的矩形，每个航点悬停 2 秒，最后自动降落。飞行日志会保存到 `logs/inspection_route_*.csv`。

## 本地仿真服务

HTTP 服务用于通过局域网启动/停止仿真、读取无人机状态、控制无人机和获取相机图像。完整接口说明见 [interface.md](interface.md)。

启动服务：

```bash
python3 scripts/sim_server.py --host 0.0.0.0 --port 18080
```

局域网其他机器访问时，把 `127.0.0.1` 换成服务器 IP，例如 `http://10.246.1.94:18080`。

最小验证：

```bash
curl http://127.0.0.1:18080/health
curl http://127.0.0.1:18080/sim/status
curl http://127.0.0.1:18080/uav/state
```

接口分层：`/sim/*` 管仿真进程，`/uav/*` 管无人机状态、控制和相机。无人机相关接口必须使用 `/uav` 前缀。

按键：

- `w`：前进
- `s`：后退
- `a`：左移
- `d`：右移
- `r`：上升
- `f`：下降
- 空格：悬停
- `l`：降落
- `q`：退出控制

## 先不做接口时的验证标准

完成仿真环境部署后，先只验证这三点：

1. PX4 SITL 可以构建并进入等待 simulator 的状态。
2. AirSim Blocks 可以启动并读取 `settings.json`。
3. PX4 终端出现 simulator connected 和 GPS/EKF fusion 相关日志。

这三点通过后，再考虑 Python/C++/ROS2 接口。

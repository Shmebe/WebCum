# RK3399 USB Camera Stream

Minimal LAN-only live video streaming for an Armbian-based RK3399 device.
It captures a V4L2 USB webcam that emits H.264 natively and publishes it
through [MediaMTX](https://mediamtx.org/) without re-encoding.

The browser endpoint uses WebRTC for low latency. No video is recorded and no
object detection is enabled. A separate, resource-limited gesture-recognizer
container tracks up to two hands and logs gesture events as JSON.

## Requirements

- Armbian/Linux on RK3399, Docker Engine, and Docker Compose plugin.
- A UVC webcam visible as a `/dev/video*` V4L2 device.
- Ports `8554`, `8888`, and `8889` available on the server. Host networking is
  used so WebRTC and RTSP work reliably on the local network.

## Install

```bash
git clone https://github.com/YOUR_GITHUB_USER/rk3399-camera-stream.git
cd rk3399-camera-stream
cp .env.example .env
```

Edit `.env` and set `SERVER_IP` to the LAN address of this server:

```bash
hostname -I
```

Confirm the camera device and available formats before starting:

```bash
v4l2-ctl --list-devices
v4l2-ctl -d /dev/video5 --list-formats-ext
```

The defaults match the tested UVC camera: H.264 from `/dev/video5` at 1920x1080
and 15 FPS. Change `CAMERA_DEVICE` in `.env` if needed. To change format,
resolution, or frame rate, edit the matching values in `mediamtx.yml`.

Start the stream:

```bash
docker compose up -d
docker compose logs -f
```

Watch recognized gesture events:

```bash
docker compose logs -f gesture-recognizer
```

View the annotated gesture stream, with hand landmarks, tracking points, and
gesture labels drawn over the video:

```text
http://SERVER_IP:8889/gestures
```

The recognizer reads the local RTSP stream, downscales it to 640 px wide, and
processes five frames per second by default. It publishes that annotated stream
with the RK3399 VPU encoder. It recognizes `Closed_Fist`,
`Open_Palm`, `Pointing_Up`, `Thumb_Up`, `Thumb_Down`, `Victory`, and `ILoveYou`.
Each event also contains normalized wrist and index-finger-tip coordinates for
tracking. Tune `ANALYSIS_FPS`, `ANALYSIS_MAX_WIDTH`, and `GESTURE_MIN_SCORE` in
`.env` if needed; keep the defaults until CPU and Bluetooth audio are stable.

Open this address from a device on the same LAN:

```text
http://SERVER_IP:8889/cam
```

For RTSP clients such as VLC, use:

```text
rtsp://SERVER_IP:8554/cam
```

The HLS playlist is available at `http://SERVER_IP:8888/cam/index.m3u8`; it
has higher latency than WebRTC.

## Troubleshooting

### FFmpeg reports an unsupported input format

Set `CAMERA_INPUT_FORMAT` to one shown by `v4l2-ctl --list-formats-ext`.
Typical values are `mjpeg`, `yuyv422`, and `h264`.

### Browser page opens but playback fails

Verify that `SERVER_IP` exactly matches the LAN address used in the browser,
and that no firewall blocks TCP port 8889 or UDP traffic used by WebRTC.

## Security

This is intentionally unauthenticated for a trusted home LAN. Do not expose
its ports to the internet. Add MediaMTX authentication before using it beyond
your local network.

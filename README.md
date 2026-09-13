# RK3399 USB Camera Stream

Minimal LAN-only live video streaming for an Armbian-based RK3399 device.
It captures a V4L2 USB webcam, encodes H.264 through the Rockchip VPU, and
publishes the result through [MediaMTX](https://mediamtx.org/).

The browser endpoint uses WebRTC for low latency. No video is recorded and no
object or gesture detection is enabled.

## Requirements

- Armbian/Linux on RK3399, Docker Engine, and Docker Compose plugin.
- A UVC webcam visible as a `/dev/video*` V4L2 device.
- Rockchip VPU encoder nodes (usually `/dev/video3` and `/dev/video4`).
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

The defaults expect an MJPEG UVC stream from `/dev/video5` at 1280x720 and 15
FPS. Adjust `CAMERA_DEVICE`, `CAMERA_INPUT_FORMAT`, `CAMERA_SIZE`, and
`CAMERA_FPS` in `.env` to match the output above.

Start the stream:

```bash
docker compose up -d
docker compose logs -f
```

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

### VPU encoder does not start

Check that the VPU nodes exist and are mapped:

```bash
ls -l /dev/video3 /dev/video4
docker compose logs camera-stream
```

If the container image's FFmpeg lacks a compatible RK3399 V4L2 encoder, the
log will identify it. Do not silently fall back to `libx264`: on this host it
can compete with Bluetooth audio. Use the native host FFmpeg build or add an
RKMPP-enabled FFmpeg image instead.

### Browser page opens but playback fails

Verify that `SERVER_IP` exactly matches the LAN address used in the browser,
and that no firewall blocks TCP port 8889 or UDP traffic used by WebRTC.

## Security

This is intentionally unauthenticated for a trusted home LAN. Do not expose
its ports to the internet. Add MediaMTX authentication before using it beyond
your local network.

#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import time
from pathlib import Path
from typing import Any, Dict

import requests


TIKTOK_ACCESS_TOKEN = os.environ.get("TIKTOK_ACCESS_TOKEN")

TIKTOK_VIDEO_INIT_URL = "https://open.tiktokapis.com/v2/post/publish/inbox/video/init/"
TIKTOK_VIDEO_STATUS_URL = "https://open.tiktokapis.com/v2/post/publish/status/fetch/"
TIKTOK_USER_INFO_URL = "https://open.tiktokapis.com/v2/user/info/"


def require_env(name: str, value: str | None) -> None:
    if not value:
        print(f"[FATAL] env {name} is not set", file=sys.stderr)
        sys.exit(1)


def tiktok_user_info() -> Dict[str, Any]:
    headers = {
        "Authorization": f"Bearer {TIKTOK_ACCESS_TOKEN}",
        "Content-Type": "application/json; charset=UTF-8",
    }
    body = {"fields": ["open_id", "display_name", "avatar_url"]}
    resp = requests.post(TIKTOK_USER_INFO_URL, headers=headers, json=body, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    if data.get("error") and data["error"].get("code") != "ok":
        raise RuntimeError(f"TikTok user.info error: {data['error']}")
    user = (data.get("data") or {}).get("user") or {}
    return user  # type: ignore[return-value]


def tiktok_init_upload(video_size: int) -> Dict[str, Any]:
    headers = {
        "Authorization": f"Bearer {TIKTOK_ACCESS_TOKEN}",
        "Content-Type": "application/json; charset=UTF-8",
    }
    body = {
        "source_info": {
            "source": "FILE_UPLOAD",
            "video_size": video_size,
            "chunk_size": video_size,
            "total_chunk_count": 1,
        }
    }
    resp = requests.post(TIKTOK_VIDEO_INIT_URL, headers=headers, json=body, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    if data.get("error") and data["error"].get("code") != "ok":
        raise RuntimeError(f"TikTok init upload error: {data['error']}")
    return data["data"]


def tiktok_upload_file(upload_url: str, path: Path, size: int) -> None:
    headers = {
        "Content-Range": f"bytes 0-{size-1}/{size}",
        "Content-Type": "video/mp4",
    }
    with path.open("rb") as f:
        resp = requests.put(upload_url, headers=headers, data=f, timeout=300)
    resp.raise_for_status()


def tiktok_check_status(publish_id: str) -> Dict[str, Any]:
    headers = {
        "Authorization": f"Bearer {TIKTOK_ACCESS_TOKEN}",
        "Content-Type": "application/json; charset=UTF-8",
    }
    body = {"publish_id": publish_id}
    resp = requests.post(TIKTOK_VIDEO_STATUS_URL, headers=headers, json=body, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    if data.get("error") and data["error"].get("code") != "ok":
        raise RuntimeError(f"TikTok status error: {data['error']}")
    return data["data"]


def run(video_path: str) -> None:
    require_env("TIKTOK_ACCESS_TOKEN", TIKTOK_ACCESS_TOKEN)

    path = Path(video_path)
    if not path.is_file():
        print(f"[FATAL] Video file not found: {path}", file=sys.stderr)
        sys.exit(1)

    size = path.stat().st_size
    print(f"Using video file: {path} ({size} bytes)")

    print("\n[1] Checking user.info.basic ...")
    user = tiktok_user_info()
    print(f"[OK] TikTok user: open_id={user.get('open_id')} display_name={user.get('display_name')}")

    print("\n[2] Initializing video upload ...")
    init_data = tiktok_init_upload(size)
    publish_id = init_data.get("publish_id")
    upload_url = init_data.get("upload_url")
    if not upload_url:
        raise RuntimeError(f"No upload_url in init response: {init_data}")
    print(f"[OK] Init done. publish_id={publish_id}")

    print("\n[3] Uploading video bytes ...")
    tiktok_upload_file(upload_url, path, size)
    print("[OK] Upload request sent")

    print("\n[4] Polling status ...")
    for _ in range(10):
        status = tiktok_check_status(publish_id)
        stage = status.get("stage")
        status_code = status.get("status")
        print(f"status: stage={stage} status={status_code}")
        if status_code in ("PUBLISH_SUCCESS", "SUCCESS"):
            print("[OK] TikTok reports publish success (draft in inbox)")
            break
        time.sleep(5)
    else:
        print("[WARN] Video upload did not reach SUCCESS state within polling limit")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python tiktok_upload_test.py <path_to_video.mp4>")
        sys.exit(1)
    run(sys.argv[1])

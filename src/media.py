"""Download call recordings and convert them to mp3.

The challenge requires audio in ogg or mp3. Vapi records as wav by default, so we
download the recording and transcode with the ffmpeg binary bundled by
`imageio-ffmpeg` — no system ffmpeg install required.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import requests


def _ffmpeg_exe() -> str:
    import imageio_ffmpeg

    return imageio_ffmpeg.get_ffmpeg_exe()


def download(url: str, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with requests.get(url, stream=True, timeout=120) as r:
        r.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
    return dest


def to_mp3(src: Path, dest: Path) -> Path:
    """Transcode any audio file to mp3. Returns dest."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        _ffmpeg_exe(),
        "-y",
        "-i", str(src),
        "-codec:a", "libmp3lame",
        "-qscale:a", "2",  # ~190 kbps VBR, plenty for speech
        str(dest),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {proc.stderr[-800:]}")
    return dest


def fetch_recording_as_mp3(url: str, out_dir: Path, stem: str = "recording") -> Path | None:
    """Download a recording URL and return the path to an mp3.

    If the source is already mp3, we keep it; otherwise transcode. The raw download
    is named with a `_raw_` prefix so .gitignore can keep it out of the repo.
    """
    if not url:
        return None
    ext = ".mp3" if url.lower().split("?")[0].endswith(".mp3") else ".wav"
    raw = out_dir / f"_raw_{stem}{ext}"
    download(url, raw)
    if ext == ".mp3":
        final = out_dir / f"{stem}.mp3"
        raw.replace(final)
        return final
    final = out_dir / f"{stem}.mp3"
    to_mp3(raw, final)
    try:
        raw.unlink()  # remove the temp wav; mp3 is the deliverable
    except OSError:
        pass
    return final

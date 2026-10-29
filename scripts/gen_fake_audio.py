"""Генерация тестовых аудиофайлов для FakeProvider (SPEC §7.3).

Каждый трек: тихий фоновый тон своей частоты (чтобы треки различались на слух) + короткий щелчок
в начале каждой секунды; на каждой 10-й секунде щелчок выше и громче. Два браузера, играющие
рассинхронно, сразу слышны как «двойные щелчки».

    python scripts/gen_fake_audio.py            # в backend/fake_media/
    python scripts/gen_fake_audio.py --force    # перегенерировать

Требуется ffmpeg в PATH. Формат — MP3 CBR 96 кбит/с, моно, 44.1 кГц: играет во всех браузерах.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "backend" / "fake_media"

# id, длительность (с), частота фонового тона (Гц). Должно совпадать с app/providers/fake_catalog.py.
TRACKS: list[tuple[str, int, int]] = [
    ("fake-1", 30, 220),
    ("fake-2", 45, 247),
    ("fake-3", 60, 262),
    ("fake-4", 75, 294),
    ("fake-5", 90, 330),
    ("fake-6", 120, 349),
    ("fake-7", 150, 392),
    ("fake-8", 180, 440),
    ("fake-9", 240, 494),
    ("fake-10", 20, 523),
]


def expression(base_hz: int) -> str:
    # Щелчок: 15 мс синуса 1 кГц (2 кГц на каждой 10-й секунде) с экспоненциальным затуханием.
    click = (
        "if(lt(mod(t,1),0.015),"
        "if(lt(mod(t,10),1),0.9*sin(2*PI*2000*t),0.6*sin(2*PI*1000*t))*exp(-mod(t,1)*200),0)"
    )
    tone = f"0.12*sin(2*PI*{base_hz}*t)"
    return f"{click}+{tone}"


def generate(force: bool) -> int:
    if shutil.which("ffmpeg") is None:
        print("ffmpeg не найден в PATH", file=sys.stderr)
        return 1
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for track_id, duration, base_hz in TRACKS:
        target = OUT_DIR / f"{track_id}.mp3"
        if target.exists() and not force:
            continue
        cmd = [
            "ffmpeg", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", f"aevalsrc='{expression(base_hz)}':s=44100:d={duration}",
            "-ac", "1", "-codec:a", "libmp3lame", "-b:a", "96k",
            str(target),
        ]  # fmt: skip
        subprocess.run(cmd, check=True)  # noqa: S603 — аргументы фиксированы
        print(f"  {target.relative_to(ROOT)}  {duration} с")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Генерация тестовых треков FakeProvider")
    parser.add_argument("--force", action="store_true")
    sys.exit(generate(parser.parse_args().force))

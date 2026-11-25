#!/usr/bin/env python3
"""
Tổng hợp âm báo chiptune nguyên bản bằng Python.

Các âm thanh trong tệp này được tạo hoàn toàn bằng code (sóng vuông,
sóng tam giác và bao âm tấn/công), không sử dụng bất kỳ tài sản âm thanh
có bản quyền hay tệp mẫu có sẵn.

Để tạo lại các tệp WAV cạnh thư mục chứa script này:
    python3 hypr/sounds/make-sounds.py

Để chạy tự kiểm tra (tạo tệp tạm rồi kiểm tra định dạng, thời lượng,
đỉnh âm lượng và đầu/cuối tệp không bị click):
    python3 hypr/sounds/make-sounds.py --selftest
"""

import math
import os
import struct
import sys
import wave

SAMPLE_RATE = 22050
ATTACK = 0.003
RELEASE = 0.025
MAX_VOL = 0.45

# Mỗi sự kiện là một tuple: ("note", tần_số, thời_lượng, duty, âm_lượng)
# hoặc ("gap", thời_lượng). Các tần số được làm tròn từ nốt nhạc tương ứng.
SOUNDS = {
    "alert-warn": [
        ("note", 659.26, 0.15, 0.50, MAX_VOL),  # E5
        ("gap", 0.025),
        ("note", 987.77, 0.15, 0.50, MAX_VOL),  # B5
        ("gap", 0.025),
    ],
    "alert-critical": [
        ("note", 880.00, 0.12, 0.40, MAX_VOL),  # A5
        ("gap", 0.025),
        ("note", 659.26, 0.12, 0.60, MAX_VOL),  # E5
        ("gap", 0.025),
        ("note", 440.00, 0.12, 0.40, MAX_VOL),  # A4
        ("gap", 0.080),
        ("note", 880.00, 0.12, 0.60, MAX_VOL),  # A5
        ("gap", 0.025),
        ("note", 659.26, 0.12, 0.40, MAX_VOL),  # E5
        ("gap", 0.025),
        ("note", 440.00, 0.12, 0.60, MAX_VOL),  # A4
    ],
    "alert-ok": [
        ("note", 523.25, 0.09, 0.50, MAX_VOL),  # C5
        ("gap", 0.025),
        ("note", 659.26, 0.09, 0.50, MAX_VOL),  # E5
        ("gap", 0.025),
        ("note", 783.99, 0.09, 0.50, MAX_VOL),  # G5
        ("gap", 0.025),
        ("note", 1046.50, 0.09, 0.50, MAX_VOL),  # C6
        ("gap", 0.015),
    ],
}

TARGETS = {
    "alert-warn": 0.35,
    "alert-critical": 0.90,
    "alert-ok": 0.45,
}


def note(freq, dur, duty=0.5, vol=0.45):
    """Trả về một nốt: sóng vuông + sóng tam giác thấp hơn một quãng tám."""
    count = max(1, int(round(dur * SAMPLE_RATE)))
    attack = min(max(1, int(round(ATTACK * SAMPLE_RATE))), max(1, count // 3))
    release = min(max(1, int(round(RELEASE * SAMPLE_RATE))), max(1, count - attack - 1))

    samples = []
    for i in range(count):
        t = i / SAMPLE_RATE

        # Độ rộng xung thay đổi nhẹ để tạo cảm giác gắt hơn ở âm báo khẩn cấp.
        pulse = duty + 0.06 * math.sin(2.0 * math.pi * 6.0 * t)
        pulse = min(0.85, max(0.15, pulse))
        square = 1.0 if (freq * t) % 1.0 < pulse else -1.0

        phase = ((freq * 0.5) * t) % 1.0
        triangle = 2.0 * abs(2.0 * phase - 1.0) - 1.0

        if i < attack:
            ramp = i / attack
        elif i >= count - release:
            ramp = (count - 1 - i) / release
        else:
            ramp = 1.0
        ramp = min(1.0, max(0.0, ramp))
        envelope = 0.5 - 0.5 * math.cos(math.pi * ramp)

        # Trọng số 0.78/0.22 đảm bảo tổng biên độ không vượt quá vol (0.45).
        samples.append(envelope * vol * (0.78 * square + 0.22 * triangle))
    return samples


def silence(dur):
    """Tạo đoạn im lặng ngắn giữa các nốt."""
    return [0.0] * max(0, int(round(dur * SAMPLE_RATE)))


def render(events):
    """Nối các nốt và khoảng im lặng thành một chuỗi mẫu."""
    samples = []
    for event in events:
        if event[0] == "note":
            _, freq, dur, duty, vol = event
            samples.extend(note(freq, dur, duty, vol))
        elif event[0] == "gap":
            samples.extend(silence(event[1]))
    return samples


def write_wav(path, samples):
    """Ghi mono 22050 Hz, 16-bit PCM."""
    pcm = [int(round(max(-1.0, min(1.0, s)) * 32767)) for s in samples]
    with wave.open(path, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(SAMPLE_RATE)
        wav.writeframes(struct.pack("<%dh" % len(pcm), *pcm))


def output_dir():
    """Thư mục chứa chính script này (theo đường dẫn thực sự của tệp)."""
    return os.path.dirname(os.path.realpath(__file__))


def main():
    folder = output_dir()
    for name, events in SOUNDS.items():
        samples = render(events)
        path = os.path.join(folder, name + ".wav")
        write_wav(path, samples)
        print("%s: %.3f s" % (os.path.basename(path), len(samples) / SAMPLE_RATE))
    return 0


def selftest():
    """Tạo các tệp trong thư mục tạm và kiểm tra toàn bộ tiêu chí định dạng."""
    import tempfile  # module chuẩn, chỉ cần cho chế độ tự kiểm tra

    with tempfile.TemporaryDirectory(prefix="make-sounds-") as folder:
        for name, events in SOUNDS.items():
            path = os.path.join(folder, name + ".wav")
            write_wav(path, render(events))

            assert os.path.isfile(path), name
            assert os.path.getsize(path) > 0, name
            assert os.path.getsize(path) < 60 * 1024, name

            with wave.open(path, "rb") as wav:
                assert wav.getnchannels() == 1, name
                assert wav.getsampwidth() == 2, name
                assert wav.getframerate() == SAMPLE_RATE, name
                frames = wav.readframes(wav.getnframes())

            assert len(frames) % 2 == 0, name
            values = struct.unpack("<%dh" % (len(frames) // 2), frames)
            assert values, name

            duration = len(values) / SAMPLE_RATE
            assert abs(duration - TARGETS[name]) <= 0.2 * TARGETS[name], name
            assert max(abs(v) for v in values) <= 0.46 * 32767, name
            assert abs(values[0]) < 300, name
            assert abs(values[-1]) < 300, name

    print("make-sounds.py selftest OK")
    return 0


if __name__ == "__main__":
    if len(sys.argv) == 1:
        sys.exit(main())
    if len(sys.argv) == 2 and sys.argv[1] == "--selftest":
        sys.exit(selftest())
    print("usage: make-sounds.py [--selftest]", file=sys.stderr)
    sys.exit(2)

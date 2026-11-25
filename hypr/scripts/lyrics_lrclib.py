#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Lấy lời bài hát từ LRCLIB cho popup nhạc của Kafka Hyprland.

Module chỉ dùng thư viện chuẩn của Python 3, có thể import từ media-popup.py:

    from lyrics_lrclib import fetch_lyrics, line_index_at

Hoặc chạy trực tiếp để thử nghiệm:

    python3 lyrics_lrclib.py --selftest
    python3 lyrics_lrclib.py "tên bài" "ca sĩ" [giây]
"""

import bisect
import hashlib
import json
import os
import re
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

# ---------------------------------------------------------------------------
# Hằng số và biểu thức chính quy
# ---------------------------------------------------------------------------

_USER_AGENT = "kafka-hyprland-dotfiles (https://github.com/TaZek244/kafka-hyprland-dotfiles)"
_API = "https://lrclib.net/api"
_TTL_EMPTY = 24 * 60 * 60  # Kết quả "không tìm thấy" được cache trong 1 ngày.

# Trạng thái giả để phân biệt lỗi mạng/JSON với mã HTTP 404 (404 là kết quả
# "không tìm thấy" hợp lệ, cần chuyển sang bước search).
_ERR = "loi-mang-hoac-json"

_RE_STAMP = re.compile(r"\[(\d{1,3}):(\d{1,2})(?:\.(\d{1,3}))?\]")
_RE_OFFSET = re.compile(r"\[offset:\s*([+-]?\d+)\s*\]", re.IGNORECASE)
_RE_META_TAG = re.compile(r"\[(?:ar|ti|al|length|by|offset|re|ve|lang|tool):[^\]]*\]", re.IGNORECASE)
_RE_FT = re.compile(r"\s*\b(?:ft|feat|featuring)\b\.?.*$", re.IGNORECASE)
_RE_DASH = re.compile(r"^\s*(.+?)\s+[-–—]\s+(.+?)\s*$")
_RE_BRACKET = re.compile(r"\s*[\[(]([^\])]*)[\])]\s*")
_RE_TOPIC = re.compile(r"\s*(?:[-–—]\s*)?topic\s*$", re.IGNORECASE)

_JUNK_WORDS = (
    "official",
    "video",
    "mv",
    "lyric",
    "audio",
    "karaoke",
    "teaser",
    "trailer",
    "visualizer",
    "hd",
    "hq",
    "4k",
    "vevo",
)


# ---------------------------------------------------------------------------
# Hàm thuần: phân tích LRC, tìm dòng, làm sạch tên
# ---------------------------------------------------------------------------


def parse_lrc(text):
    """Chuyển chuỗi LRC thành danh sách (giây: float, dòng: str) theo thời gian.

    Hỗ trợ [mm:ss.xx], [mm:ss.xxx], [mm:ss] và nhiều nhãn trên cùng một dòng.
    Các dòng metadata ([ar:], [ti:], [offset:]) bị bỏ qua, nhưng [offset:] được
    áp dụng: offset dương tính bằng ms làm lời hiện sớm hơn (trừ vào mốc thời gian).
    Dòng có nhãn thời gian nhưng không có chữ vẫn được giữ lại dưới dạng "".
    """
    if not text:
        return []
    raw = str(text)

    tim = _RE_OFFSET.search(raw)
    offset_ms = int(tim.group(1)) if tim else 0
    shift = offset_ms / 1000.0

    ketqua = []
    for dong in raw.splitlines():
        nhan = list(_RE_STAMP.finditer(dong))
        if not nhan:
            # Không có nhãn thời gian: đó là metadata hoặc dòng rỗng thường.
            continue

        noidung = dong[nhan[-1].end() :]
        noidung = _RE_META_TAG.sub("", noidung).strip()

        for st in nhan:
            phut = int(st.group(1))
            giay = int(st.group(2))
            le = st.group(3)
            if le:
                giay += int(le) / (10 ** len(le))
            ketqua.append((phut * 60 + giay - shift, noidung))

    ketqua.sort(key=lambda muc: muc[0])
    return ketqua


def line_index_at(lines, t):
    """Trả chỉ số dòng đang hát tại thời điểm t (giây).

    Là dòng cuối cùng có thời gian <= t; trả -1 nếu chưa tới dòng đầu.
    """
    if not lines:
        return -1
    thoi_gian = [muc[0] for muc in lines]
    chi_so = bisect.bisect_right(thoi_gian, t) - 1
    return chi_so if chi_so >= 0 else -1


def _is_junk(phan):
    """Nhận diện đoạn quảng cáo kiểu YouTube cần bỏ."""
    thap = phan.lower()
    return len(phan) <= 40 and any(tu in thap for tu in _JUNK_WORDS)


def _strip_bracket_junk(text):
    """Bỏ các cụm trong ngoặc như (Official Video), [MV], (Lyrics)..."""

    def _thay(m):
        return " " if _is_junk(m.group(1)) else m.group(0)

    return _RE_BRACKET.sub(_thay, text)


def _cut_ft(text):
    """Cắt bỏ 'ft.'/'feat.' và mọi thứ phía sau."""
    return _RE_FT.sub("", text).strip()


def _pick_segment(text):
    """Với chuỗi có dấu '|': giữ đoạn cuối còn lại sau khi bỏ đoạn rỗng/quảng cáo.

    Ví dụ 'Ca sĩ | Tên bài | Official MV' -> 'Tên bài'.
    """
    cac_phan = [phan.strip() for phan in text.split("|")]
    giu_lai = [phan for phan in cac_phan if phan and not _is_junk(phan)]
    if not giu_lai:
        return cac_phan[0].strip() if cac_phan else ""
    return giu_lai[-1].strip()


def _remove_topic(text):
    """Bỏ hậu tố ' - Topic' thường thấy ở tên kênh YouTube."""
    return _RE_TOPIC.sub("", text).strip()


def _looks_like_channel(name):
    """Đoán xem tên ca sĩ có phải chỉ là tên kênh hay không."""
    thap = (name or "").lower()
    if not thap:
        return True
    return any(tu in thap for tu in ("topic", "vevo", "official", "channel", "kênh"))


def clean_title(title):
    """Làm sạch tên bài hát, giữ nguyên dấu tiếng Việt."""
    if not title:
        return ""
    text = str(title).strip()
    text = _strip_bracket_junk(text)
    text = _cut_ft(text)
    if "|" in text:
        text = _pick_segment(text)
    text = _remove_topic(text)

    # Dạng 'Ca sĩ - Tên bài' thì trả về phần tên bài.
    hop = _RE_DASH.match(text)
    if hop:
        text = hop.group(2).strip()
    return text.strip()


def clean_artist(artist):
    """Làm sạch tên ca sĩ / tên kênh, giữ nguyên dấu tiếng Việt."""
    if not artist:
        return ""
    text = str(artist).strip()
    text = _strip_bracket_junk(text)
    text = _remove_topic(text)
    if "|" in text:
        text = text.split("|", 1)[0].strip()
    text = _cut_ft(text)
    return text.strip()


# ---------------------------------------------------------------------------
# Gọi mạng, lưu cache và chuẩn hoá kết quả
# ---------------------------------------------------------------------------


def _default_http_get(url, timeout):
    """Hàm gọi mạng mặc định dùng urllib, gắn User-Agent riêng."""
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.getcode(), resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        # 404 là kết quả hợp lệ để chuyển sang bước tìm kiếm.
        try:
            body = exc.read().decode("utf-8", "replace")
        except Exception:
            body = ""
        return exc.code, body


# Có thể thay bằng hàm giả lập trong test: hàm(url, timeout) -> (status, body).
_http_get = _default_http_get


def _request_json(url, timeout):
    """Trả về (status, dữ liệu JSON); status == _ERR khi lỗi mạng/JSON."""
    try:
        status, body = _http_get(url, timeout)
        status = int(status)
    except Exception:
        return _ERR, None

    if status == 404:
        return 404, None
    if status != 200:
        return _ERR, None

    try:
        return status, json.loads(body)
    except (ValueError, TypeError):
        return _ERR, None


def _choose(results, duration):
    """Chọn bài có duration gần nhất (lệch <= 5s), ưu tiên có syncedLyrics."""
    tot_nhat = None
    khoa_tot_nhat = None
    for muc in results or []:
        if not isinstance(muc, dict):
            continue
        try:
            do_dai = float(muc.get("duration"))
        except (TypeError, ValueError):
            do_dai = None

        if duration is not None:
            if do_dai is None or abs(do_dai - duration) > 5:
                continue
            chenh = abs(do_dai - duration)
        else:
            chenh = 0.0

        co_sync = bool(str(muc.get("syncedLyrics") or "").strip())
        khoa = (chenh, 0 if co_sync else 1)
        if khoa_tot_nhat is None or khoa < khoa_tot_nhat:
            khoa_tot_nhat, tot_nhat = khoa, muc
    return tot_nhat


def _search_request(params, duration, timeout):
    """Gọi /api/search rồi chọn kết quả tốt nhất."""
    url = _API + "/search?" + urllib.parse.urlencode(params)
    status, data = _request_json(url, timeout)
    if status == _ERR:
        return _ERR, None
    if status != 200 or not isinstance(data, list):
        return status, None
    return 200, _choose(data, duration)


def _cache_dir():
    """Thư mục cache, ưu tiên XDG_CACHE_HOME."""
    co_so = os.environ.get("XDG_CACHE_HOME") or os.path.join(os.path.expanduser("~"), ".cache")
    return os.path.join(co_so, "kafka", "lyrics")


def _cache_path(artist, title, duration):
    """Đường dẫn file cache theo sha1(artist|title|duration)."""
    khoa = "{}|{}|{}".format(
        artist or "",
        title or "",
        "" if duration is None else duration,
    )
    ten = hashlib.sha1(khoa.encode("utf-8")).hexdigest() + ".json"
    return os.path.join(_cache_dir(), ten)


def _read_cache(path):
    """Đọc cache; bỏ qua nếu đã hết hạn. Trả None khi không dùng được."""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            du_lieu = json.load(fh)
        het_han = du_lieu.get("expires_at")
        if het_han is not None and time.time() > float(het_han):
            return None
        ketqua = du_lieu.get("result")
        if not isinstance(ketqua, dict):
            return None
        ketqua = dict(ketqua)
        ketqua["source"] = "cache"
        # JSON biến cặp (giây, dòng) thành list → đổi lại tuple cho giống kết quả vừa tải
        if isinstance(ketqua.get("synced"), list):
            ketqua["synced"] = [(float(t), str(l)) for t, l in ketqua["synced"]]
        return ketqua
    except (OSError, ValueError, TypeError):
        return None


def _write_cache(path, result, empty=False):
    """Ghi kết quả đã chuẩn hoá kèm thời điểm lưu (bỏ qua lỗi ghi file)."""
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        bay_gio = time.time()
        du_lieu = {
            "saved_at": bay_gio,
            "expires_at": bay_gio + _TTL_EMPTY if empty else None,
            "result": result,
        }
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(du_lieu, fh, ensure_ascii=False)
    except OSError:
        pass


def _empty_result():
    """Kết quả khi không tìm thấy lời bài hát."""
    return {
        "synced": None,
        "plain": None,
        "source": "none",
        "instrumental": False,
    }


def _normalise(entry):
    """Chuẩn hoá một object trả về từ LRCLIB."""
    synced_raw = str(entry.get("syncedLyrics") or "")
    plain_raw = str(entry.get("plainLyrics") or "")
    synced = parse_lrc(synced_raw) if synced_raw.strip() else None
    if not synced:
        synced = None
    plain = plain_raw.strip() or None
    return {
        "synced": synced,
        "plain": plain,
        "source": "lrclib",
        "instrumental": bool(entry.get("instrumental")),
    }


def fetch_lyrics(title, artist, album="", duration=None, timeout=6):
    """Lấy lời bài hát từ LRCLIB.

    Trả về dict gồm:
      - synced: list[(giây, dòng)] hoặc None
      - plain: chuỗi lời thường hoặc None
      - source: 'lrclib' | 'cache' | 'none'
      - instrumental: bool

    Thứ tự: cache -> /api/get -> /api/search (theo tên) -> /api/search?q=...
    Mọi lỗi mạng/JSON đều trả source 'none' và không ghi cache để lần sau thử lại.
    """
    raw_title = str(title or "").strip()
    raw_artist = str(artist or "")
    ten_bai = clean_title(raw_title)
    ca_si = clean_artist(raw_artist)

    # Nếu tiêu đề dạng 'Ca sĩ - Tên bài' mà thiếu ca sĩ (hoặc chỉ có tên kênh)
    # thì tách luôn phần trước dấu gạch ngang làm ca sĩ.
    hop = _RE_DASH.match(raw_title)
    if hop and (not ca_si or _looks_like_channel(raw_artist)):
        ca_si = clean_artist(hop.group(1)) or ca_si

    if not ten_bai:
        return _empty_result()

    try:
        do_dai = None if duration is None else int(round(float(duration)))
    except (TypeError, ValueError):
        do_dai = None

    duong_dan_cache = _cache_path(ca_si, ten_bai, do_dai)
    cached = _read_cache(duong_dan_cache)
    if cached is not None:
        return cached

    # Bước 1: truy vấn chính xác /api/get.
    params = {"track_name": ten_bai}
    if ca_si:
        params["artist_name"] = ca_si
    if album and str(album).strip():
        params["album_name"] = str(album).strip()
    if do_dai is not None:
        params["duration"] = str(do_dai)
    url_get = _API + "/get?" + urllib.parse.urlencode(params)

    status, data = _request_json(url_get, timeout)
    if status == _ERR:
        return _empty_result()

    entry = None
    if status == 200:
        if isinstance(data, dict):
            entry = data
    elif status == 404:
        # Bước 2: tìm theo tên bài + ca sĩ.
        params_tim = {"track_name": ten_bai}
        if ca_si:
            params_tim["artist_name"] = ca_si
        status, entry = _search_request(params_tim, do_dai, timeout)
        if status == _ERR:
            return _empty_result()

        if entry is None:
            # Bước 3: tìm theo chuỗi truy vấn đơn giản.
            status, entry = _search_request({"q": ten_bai}, do_dai, timeout)
            if status == _ERR:
                return _empty_result()
    else:
        return _empty_result()

    if entry is None:
        # 404 + search rỗng: không tìm thấy thật, cache rỗng 1 ngày.
        ketqua = _empty_result()
        _write_cache(duong_dan_cache, ketqua, empty=True)
        return ketqua

    ketqua = _normalise(entry)
    # Có lời thì giữ mãi; không có lời thì chỉ giữ 1 ngày.
    _write_cache(
        duong_dan_cache,
        ketqua,
        empty=not (ketqua["synced"] or ketqua["plain"]),
    )
    return ketqua


# ---------------------------------------------------------------------------
# Tự kiểm tra và giao diện dòng lệnh
# ---------------------------------------------------------------------------


def _selftest():
    """Chạy các ca kiểm tra có sẵn, in PASS/FAIL và trả mã thoát."""
    global _http_get
    tat_dat = True

    def kiemtra(ten, dieu_kien):
        nonlocal tat_dat
        print(("PASS " if dieu_kien else "FAIL ") + ten)
        if not dieu_kien:
            tat_dat = False

    # --- parse_lrc ---
    lrc = (
        "[ar:Kafka]\n"
        "[ti:Web của Kafka]\n"
        "[offset:+500]\n"
        "[00:01.00][01:30.50]Hai nhãn cùng một dòng\n"
        "[00:02.123]Ba chữ số mili giây\n"
        "[00:03]\n"
        "[00:04.00]   \n"
        "Dòng không có nhãn thời gian\n"
    )
    da_doc = parse_lrc(lrc)
    kiemtra(
        "parse_lrc: nhiều nhãn trên một dòng",
        (0.5, "Hai nhãn cùng một dòng") in da_doc and (90.0, "Hai nhãn cùng một dòng") in da_doc,
    )
    kiemtra(
        "parse_lrc: offset dương làm lời hiện sớm hơn",
        any(abs(t - 1.623) < 1e-6 and s == "Ba chữ số mili giây" for t, s in da_doc),
    )
    kiemtra(
        "parse_lrc: dạng [mm:ss] và dòng trống nhạc dạo",
        (2.5, "") in da_doc and (3.5, "") in da_doc,
    )
    kiemtra(
        "parse_lrc: bỏ metadata và sắp theo thời gian",
        len(da_doc) == 5 and [t for t, _ in da_doc] == sorted(t for t, _ in da_doc),
    )

    # --- line_index_at ---
    dong = [(1.0, "a"), (2.5, "b"), (5.0, "c")]
    kiemtra("line_index_at: trước dòng đầu", line_index_at(dong, 0.5) == -1)
    kiemtra("line_index_at: giữa hai dòng", line_index_at(dong, 3.0) == 1)
    kiemtra("line_index_at: sau dòng cuối", line_index_at(dong, 9.0) == 2)
    kiemtra("line_index_at: đúng mốc thời gian", line_index_at(dong, 2.5) == 1)

    # --- clean_title / clean_artist ---
    cac_ten = (
        (
            "Sơn Tùng M-TP | Chúng Ta Của Tương Lai | Official MV",
            "Chúng Ta Của Tương Lai",
        ),
        (
            "Sài Gòn Hôm Nay Mưa (Official Music Video)",
            "Sài Gòn Hôm Nay Mưa",
        ),
        (
            "JSOL - Sài Gòn Hôm Nay Mưa ft. Hoàng Duyên",
            "Sài Gòn Hôm Nay Mưa",
        ),
    )
    for stt, (dau, mong_doi) in enumerate(cac_ten, 1):
        thuc_te = clean_title(dau)
        kiemtra(
            "clean_title ca {} ('{}' -> '{}')".format(stt, thuc_te, mong_doi),
            thuc_te == mong_doi,
        )
    kiemtra(
        "clean_artist: bỏ hậu tố ' - Topic'",
        clean_artist("Sơn Tùng M-TP - Topic") == "Sơn Tùng M-TP",
    )

    # --- fetch_lyrics với _http_get giả lập và cache tạm ---
    tmp = tempfile.mkdtemp(prefix="kafka-lyrics-selftest-")
    old_env = os.environ.get("XDG_CACHE_HOME")
    old_get = _http_get
    os.environ["XDG_CACHE_HOME"] = tmp
    try:
        # (a) /api/get trả 200.
        def fake_get_200(url, timeout):
            if "/api/get?" in url:
                return (
                    200,
                    json.dumps(
                        {
                            "trackName": "Chúng Ta Của Tương Lai",
                            "artistName": "Sơn Tùng M-TP",
                            "duration": 185,
                            "syncedLyrics": "[00:01.00]Lời đầu\n[00:02.00]Lời sau\n",
                            "plainLyrics": "Lời đầu\nLời sau",
                            "instrumental": 0,
                        }
                    ),
                )
            return (500, "")

        _http_get = fake_get_200
        ten_a, si_a = "Chúng Ta Của Tương Lai", "Sơn Tùng M-TP"
        ket_a = fetch_lyrics(ten_a, si_a, duration=185)
        kiemtra(
            "fetch_lyrics: API get 200",
            ket_a["source"] == "lrclib"
            and bool(ket_a["synced"])
            and ket_a["synced"][0][1] == "Lời đầu"
            and ket_a["plain"] == "Lời đầu\nLời sau",
        )

        # Đọc lại từ cache (mạng giả lỗi nhưng không được gọi).
        _http_get = lambda url, timeout: (500, "")
        ket_a2 = fetch_lyrics(ten_a, si_a, duration=185)
        kiemtra(
            "fetch_lyrics: đọc lại từ cache",
            ket_a2["source"] == "cache" and ket_a2["synced"] == ket_a["synced"],
        )

        # (b) 404 -> search chọn đúng duration và ưu tiên syncedLyrics.
        def fake_404_tim(url, timeout):
            if "/api/get?" in url:
                return (404, "không tìm thấy")
            if "/api/search?" in url and "track_name=" in url:
                return (
                    200,
                    json.dumps(
                        [
                            {
                                "trackName": "Bài hết mưa",
                                "artistName": "Kafka",
                                "duration": 100,
                                "plainLyrics": "bài khác",
                                "syncedLyrics": None,
                            },
                            {
                                "trackName": "Bài hết mưa",
                                "artistName": "Kafka",
                                "duration": 184,
                                "plainLyrics": "gần nhưng không sync",
                                "syncedLyrics": None,
                            },
                            {
                                "trackName": "Bài hết mưa",
                                "artistName": "Kafka",
                                "duration": 186,
                                "plainLyrics": "đúng bài",
                                "syncedLyrics": "[00:03.00]Lời đúng\n",
                            },
                        ]
                    ),
                )
            return (200, "[]")

        _http_get = fake_404_tim
        ket_b = fetch_lyrics("Bài hết mưa", "Kafka", duration=185)
        kiemtra(
            "fetch_lyrics: 404 -> search chọn đúng bài",
            ket_b["source"] == "lrclib" and bool(ket_b["synced"]) and ket_b["synced"][0][1] == "Lời đúng",
        )

        # (c) Lỗi mạng: trả 'none' và KHÔNG ghi cache.
        def fake_mang_loi(url, timeout):
            raise OSError("mạng lỗi")

        _http_get = fake_mang_loi
        ten_c, si_c = "Bài chưa có cache", "Kafka Test"
        ket_c = fetch_lyrics(ten_c, si_c, duration=200)
        duong_c = _cache_path(clean_artist(si_c), clean_title(ten_c), 200)
        kiemtra("fetch_lyrics: lỗi mạng -> source none", ket_c["source"] == "none")
        kiemtra(
            "fetch_lyrics: lỗi mạng không ghi cache",
            not os.path.exists(duong_c),
        )

        # (d) 404 + search rỗng: cache kết quả rỗng trong 1 ngày.
        def fake_rong(url, timeout):
            if "/api/get?" in url:
                return (404, "")
            return (200, "[]")

        _http_get = fake_rong
        ten_d, si_d = "Không tìm thấy lời", "Kafka Test"
        ket_d = fetch_lyrics(ten_d, si_d)
        duong_d = _cache_path(clean_artist(si_d), clean_title(ten_d), None)
        kiemtra(
            "fetch_lyrics: 404 + search rỗng -> cache kết quả rỗng",
            ket_d["source"] == "none" and os.path.exists(duong_d),
        )
        try:
            with open(duong_d, "r", encoding="utf-8") as fh:
                luu = json.load(fh)
            kiemtra(
                "fetch_lyrics: cache rỗng có hạn 1 ngày",
                luu.get("expires_at") is not None and 0 < luu["expires_at"] - luu["saved_at"] <= _TTL_EMPTY + 1,
            )
        except (OSError, ValueError, KeyError, TypeError):
            kiemtra("fetch_lyrics: cache rỗng có hạn 1 ngày", False)
    finally:
        _http_get = old_get
        if old_env is None:
            os.environ.pop("XDG_CACHE_HOME", None)
        else:
            os.environ["XDG_CACHE_HOME"] = old_env

    return 0 if tat_dat else 1


def _main(argv):
    """Điểm vào dòng lệnh."""
    if len(argv) >= 2 and argv[1] == "--selftest":
        return _selftest()

    if len(argv) < 3:
        print('Dùng: lyrics_lrclib.py --selftest | lyrics_lrclib.py "tên bài" "ca sĩ" [giây]')
        return 2

    tieu_de = argv[1]
    nghe_si = argv[2]
    do_dai = None
    if len(argv) >= 4:
        try:
            do_dai = float(argv[3])
        except ValueError:
            do_dai = None

    ketqua = fetch_lyrics(tieu_de, nghe_si, duration=do_dai)
    dong = []
    if ketqua["synced"]:
        dong = [noi_dung for _, noi_dung in ketqua["synced"][:5]]
    elif ketqua["plain"]:
        dong = ketqua["plain"].splitlines()[:5]

    for noi_dung in dong:
        print(noi_dung)
    if not dong:
        print("(không tìm thấy lời bài hát)")
    return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv))

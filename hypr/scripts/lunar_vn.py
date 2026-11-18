#!/usr/bin/env python3
"""Đổi lịch dương sang âm lịch Việt Nam (múi giờ UTC+7).

Chuyển ngữ sang Python từ thuật toán âm lịch của Hồ Ngọc Đức (https://www.informatik.uni-leipzig.de/~duc/amlich/).
Thông báo bản quyền gốc (giữ nguyên theo yêu cầu của tác giả; file này KHÔNG theo giấy phép MIT của repo):

    Copyright (c) 2006 Ho Ngoc Duc. All Rights Reserved.
    Astronomical algorithms from the book "Astronomical Algorithms" by Jean Meeus, 1998.
    Permission to use, copy, modify, and redistribute this software and its documentation
    for personal, non-commercial use is hereby granted provided that this copyright notice
    and appropriate documentation appears in all copies.
"""

import argparse
import datetime as _datetime
import math


_TZ = 7.0
_PI = math.pi
_CAN = ("Giáp", "Ất", "Bính", "Đinh", "Mậu", "Kỷ", "Canh", "Tân", "Nhâm", "Quý")
_CHI = ("Tý", "Sửu", "Dần", "Mão", "Thìn", "Tỵ", "Ngọ", "Mùi",
        "Thân", "Dậu", "Tuất", "Hợi")


def _int(x):
    return math.floor(x)


def _jd_from_date(day, month, year):
    a = _int((14 - month) / 12)
    y = year + 4800 - a
    m = month + 12 * a - 3
    jd = day + _int((153 * m + 2) / 5) + 365 * y + _int(y / 4)
    jd = jd - _int(y / 100) + _int(y / 400) - 32045
    return jd


def _new_moon_day(k, time_zone):
    """Ngày dương lịch bắt đầu sóc thứ k, quy về múi giờ địa phương."""
    t = k / 1236.85
    t2, t3, dr = t * t, t * t * t, _PI / 180
    jd1 = (2415020.75933 + 29.53058868 * k + 0.0001178 * t2
           - 0.000000155 * t3)
    jd1 += 0.00033 * math.sin((166.56 + 132.87 * t - 0.009173 * t2) * dr)
    m = 359.2242 + 29.10535608 * k - 0.0000333 * t2 - 0.00000347 * t3
    mpr = 306.0253 + 385.81691806 * k + 0.0107306 * t2 + 0.00001236 * t3
    f = 21.2964 + 390.67050646 * k - 0.0016528 * t2 - 0.00000239 * t3
    c1 = ((0.1734 - 0.000393 * t) * math.sin(m * dr)
          + 0.0021 * math.sin(2 * m * dr)
          - 0.4068 * math.sin(mpr * dr)
          + 0.0161 * math.sin(2 * mpr * dr)
          - 0.0004 * math.sin(3 * mpr * dr)
          + 0.0104 * math.sin(2 * f * dr)
          - 0.0051 * math.sin((m + mpr) * dr)
          - 0.0074 * math.sin((m - mpr) * dr)
          + 0.0004 * math.sin((2 * f + m) * dr)
          - 0.0004 * math.sin((2 * f - m) * dr)
          - 0.0006 * math.sin((2 * f + mpr) * dr)
          + 0.0010 * math.sin((2 * f - mpr) * dr)
          + 0.0005 * math.sin((2 * mpr + m) * dr))
    if t < -11:
        deltat = (0.001 + 0.000839 * t + 0.0002261 * t2
                  - 0.00000845 * t3 - 0.000000081 * t * t3)
    else:
        deltat = -0.000278 + 0.000265 * t + 0.000262 * t2
    return _int(jd1 + c1 - deltat + 0.5 + time_zone / 24)


def _sun_longitude(jdn, time_zone):
    """Kinh độ mặt trời tại thời điểm gần giữa ngày địa phương."""
    t = (jdn - 2451545.5 - time_zone / 24) / 36525
    t2, t3, dr = t * t, t * t * t, _PI / 180
    m = 357.52910 + 35999.05030 * t - 0.0001559 * t2 - 0.00000048 * t3
    l0 = 280.46645 + 36000.76983 * t + 0.0003032 * t2
    dl = ((1.914600 - 0.004817 * t - 0.000014 * t2) * math.sin(dr * m)
          + (0.019993 - 0.000101 * t) * math.sin(2 * dr * m)
          + 0.000290 * math.sin(3 * dr * m))
    lam = (l0 + dl - 0.00569 - 0.00478 * math.sin(dr * (125.04 - 1934.136 * t))) % 360
    return _int(lam / 30)


def _lunar_month_11(year, time_zone):
    off = _jd_from_date(31, 12, year) - 2415021
    k = _int(off / 29.530588853)
    nm = _new_moon_day(k, time_zone)
    if _sun_longitude(nm, time_zone) >= 9:
        nm = _new_moon_day(k - 1, time_zone)
    return nm


def _leap_month_offset(a11, time_zone):
    k = _int((a11 - 2415021.076998695) / 29.530588853 + 0.5)
    last = 0
    i = 1
    while i < 15:
        arc = _sun_longitude(_new_moon_day(k + i, time_zone), time_zone)
        if arc == last:
            return i - 1
        last = arc
        i += 1
    return 0


def _tet_jd(gregorian_year):
    """Tìm ngày sóc đầu tiên trong khoảng Tết (21/1 đến 20/2)."""
    start = _jd_from_date(21, 1, gregorian_year)
    k = _int((start - 2415021.076998695) / 29.530588853) - 1
    for i in range(4):
        nm = _new_moon_day(k + i, _TZ)
        if start <= nm <= _jd_from_date(20, 2, gregorian_year):
            return nm
    raise ValueError("Không tìm được ngày Tết")


def solar_to_lunar(day, month, year):
    """Trả về (ngày âm, tháng âm, năm âm, tháng nhuận)."""
    day_number = _jd_from_date(day, month, year)
    k = _int((day_number - 2415021.076998695) / 29.530588853)
    month_start = _new_moon_day(k + 1, _TZ)
    if month_start > day_number:
        month_start = _new_moon_day(k, _TZ)
    a11 = _lunar_month_11(year, _TZ)
    b11 = a11
    if month_start >= a11:
        lunar_year = year
        b11 = _lunar_month_11(year + 1, _TZ)
    else:
        lunar_year = year - 1
        a11 = _lunar_month_11(year - 1, _TZ)
    lunar_day = day_number - month_start + 1
    diff = _int((month_start - a11) / 29)
    lunar_leap = False
    lunar_month = diff + 11
    if b11 - a11 > 365:
        leap_month_diff = _leap_month_offset(a11, _TZ)
        if diff >= leap_month_diff:
            lunar_month = diff + 10
            if diff == leap_month_diff:
                lunar_leap = True
    if lunar_month > 12:
        lunar_month -= 12
    # Tên năm âm lịch là năm dương lịch chứa ngày Tết của năm đó.
    # Cách xác định này cũng xử lý đúng các ngày tháng 11, 12 trước Tết.
    lunar_year = year if day_number >= _tet_jd(year) else year - 1
    return lunar_day, lunar_month, lunar_year, lunar_leap


def can_chi_year(lunar_year):
    return f"{_CAN[(lunar_year + 6) % 10]} {_CHI[(lunar_year + 8) % 12]}"


def can_chi_day(day, month, year):
    jd = _jd_from_date(day, month, year)
    return f"{_CAN[(jd + 9) % 10]} {_CHI[(jd + 1) % 12]}"


def lunar_label(day, month, year):
    lunar_day, lunar_month, lunar_year, is_leap = solar_to_lunar(day, month, year)
    day_name = f"Mùng {lunar_day}" if lunar_day <= 10 else f"Ngày {lunar_day}"
    if lunar_month == 1:
        month_name = "tháng Giêng"
    elif lunar_month == 12:
        month_name = "tháng Chạp"
    else:
        month_name = f"tháng {lunar_month}"
    if is_leap:
        month_name += " nhuận"
    return f"{day_name} {month_name} năm {can_chi_year(lunar_year)}"


def _selftest():
    tests = [
        ((10, 2, 2024), (1, 1, 2024, False)),
        ((29, 1, 2025), (1, 1, 2025, False)),
        ((17, 2, 2026), (1, 1, 2026, False)),
        ((22, 1, 2023), (1, 1, 2023, False)),
        ((22, 3, 2023), (1, 2, 2023, True)),
        ((25, 7, 2025), (1, 6, 2025, True)),
    ]
    ok = True
    for solar, expected in tests:
        actual = solar_to_lunar(*solar)
        passed = actual == expected
        ok &= passed
        print(f"{'OK' if passed else 'FAIL'} {solar} -> {actual} (cần {expected})")
    for year, expected in ((2026, "Bính Ngọ"), (2025, "Ất Tỵ")):
        actual = can_chi_year(year)
        passed = actual == expected
        ok &= passed
        print(f"{'OK' if passed else 'FAIL'} can_chi_year({year}) -> {actual}")
    result = solar_to_lunar(17, 11, 2026)
    passed = result[1] in (9, 10) and result[2] == 2026
    ok &= passed
    print(f"{'OK' if passed else 'FAIL'} 17/11/2026 -> {result} (đối chiếu tháng 9 hoặc 10 năm 2026)")
    return 0 if ok else 1


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args()
    if args.selftest:
        raise SystemExit(_selftest())
    today = _datetime.date.today()
    print(lunar_label(today.day, today.month, today.year))


if __name__ == "__main__":
    main()

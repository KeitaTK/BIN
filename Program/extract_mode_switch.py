#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ArduPilot BINログからMODEメッセージのモード切替情報を抜き出して表示するスクリプト
"""
import sys
from pathlib import Path
import numpy as np
try:
    from pymavlink import mavutil
except ImportError:
    print("pymavlinkが必要です: pip install pymavlink")
    sys.exit(1)

# ログファイルパス（必要に応じて変更）
BIN_FILE = r"1\00000174.BIN"

mlog = mavutil.mavlink_connection(BIN_FILE)
mode_list = []
time_list = []
fields = set()

while True:
    msg = mlog.recv_match(type='MODE', blocking=False)
    if msg is None:
        break
    d = msg.to_dict()
    fields.update(d.keys())
    # 代表的なモード番号フィールドを探す
    for key in ['Mode', 'ModeNum', 'CNum']:
        if key in d:
            mode_list.append(d[key])
            time_list.append(d.get('TimeUS', None))
            break

print(f"MODEメッセージのフィールド一覧: {fields}")
print(f"MODE切替履歴（時刻[us], モード番号）:")
for t, m in zip(time_list, mode_list):
    print(f"{t}, {m}")

if len(mode_list) > 0:
    print(f"\nユニークなモード番号: {np.unique(mode_list)}")
else:
    print("MODEメッセージが見つかりませんでした")

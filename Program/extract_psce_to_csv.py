#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PSCEメッセージのデータをBINファイルから抽出し、CSVに出力するスクリプト
"""
import os
import sys
import csv
from pathlib import Path

try:
    from pymavlink import mavutil
except ImportError:
    print("[ERROR] pymavlinkが必要です: pip install pymavlink")
    sys.exit(1)

# ==================== 設定セクション ====================
INPUT_BIN_FILE = r"C:\Users\taki\Local\local\BIN\1\00000004.BIN"
OUTPUT_DIRECTORY = os.path.expanduser("~\\Downloads")
# =======================================================

PSCE_FIELDS = [
    "TimeUS", "DPE", "TPE", "PE", "DVE", "TVE", "VE", "DAE", "TAE", "AE"
]

def extract_psce_to_csv(bin_file_path, csv_output_path):
    if not os.path.exists(bin_file_path):
        print(f"[ERROR] ファイルが見つかりません: {bin_file_path}")
        return False
    print(f"[INFO] 読み込み: {bin_file_path}")
    try:
        mlog = mavutil.mavlink_connection(bin_file_path)
    except Exception as e:
        print(f"[ERROR] ファイルの読み込みに失敗: {e}")
        return False
    records = []
    msg_count = 0
    print("[INFO] PSCEメッセージを抽出中...")
    while True:
        msg = mlog.recv_match(blocking=False)
        if msg is None:
            break
        msg_type = msg.get_type()
        if msg_type == 'PSCE':
            try:
                record = {field: getattr(msg, field, 0) for field in PSCE_FIELDS}
                records.append(record)
                msg_count += 1
                if msg_count <= 3:
                    print(f"[DEBUG] レコード {msg_count}: " + ", ".join([f"{k}={record[k]}" for k in PSCE_FIELDS]))
                if msg_count % 50000 == 0:
                    print(f"[DEBUG] 処理中: {msg_count} レコード抽出")
            except Exception as e:
                print(f"[WARNING] メッセージ処理エラー: {e}")
                continue
    print(f"[INFO] 抽出レコード数: {len(records)}")
    try:
        os.makedirs(os.path.dirname(csv_output_path) or '.', exist_ok=True)
        with open(csv_output_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=PSCE_FIELDS)
            writer.writeheader()
            writer.writerows(records)
        print(f"[SUCCESS] CSV出力: {csv_output_path}")
        return True
    except Exception as e:
        print(f"[ERROR] CSV出力エラー: {e}")
        return False

def main():
    bin_file = INPUT_BIN_FILE
    if not os.path.exists(bin_file):
        print(f"[ERROR] ファイルが見つかりません: {bin_file}")
        sys.exit(1)
    bin_filename = os.path.basename(bin_file)
    if bin_filename.endswith('.BIN'):
        file_number = bin_filename.replace('.BIN', '')
    else:
        file_number = bin_filename
    csv_file = os.path.join(OUTPUT_DIRECTORY, f"PSCE_data_{file_number}.csv")
    print(f"[INFO] 処理開始:")
    print(f"  入力: {bin_file}")
    print(f"  出力: {csv_file}")
    extract_psce_to_csv(bin_file, csv_file)

if __name__ == "__main__":
    main()

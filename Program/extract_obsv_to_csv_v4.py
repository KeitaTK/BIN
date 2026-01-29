#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ArduPilot AP_ObserverのOBSVログフォーマット対応（v4）
TimeUS, PLX, PLY, PLZ, AX, AY, BX, BY, CX, CY, F, P, X, Y, SW を抽出してCSV化
pymavlinkを使用して正しい形式でメッセージ解析
SW: RC8スイッチ状態（0=オフ、1=オン）を追加
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

# ==================== 設定セクション（ここでファイル名を指定） ====================
# 読み込むBINファイル名（ここを変更してください）
# 例: "C:\\Users\\taki\\Local\\local\\BIN\\1\\00000426.BIN"
INPUT_BIN_FILE = "C:\\Users\\taki\\Local\\local\\BIN\\1\\00000444.BIN"

# 出力ディレクトリ（自動的にファイル名が生成されます）
OUTPUT_DIRECTORY = os.path.expanduser("~\\Downloads")
# =================================================================================

def extract_obsv_new_format(bin_file_path, csv_output_path):
    """
    pymavlinkを使用してOBSVメッセージを抽出してCSV化（SWフィールド追加）
    """
    fields = [
        "TimeUS", "PLX", "PLY", "PLZ", "AX", "AY", "BX", "BY", "CX", "CY", "F", "P", "X", "Y", "SW"
    ]
    
    # ファイルが存在するか確認
    if not os.path.exists(bin_file_path):
        print(f"[ERROR] ファイルが見つかりません: {bin_file_path}")
        return False
    
    print(f"[INFO] 読み込み: {bin_file_path}")
    
    # .binファイルを開く（pymavlink使用）
    try:
        mlog = mavutil.mavlink_connection(bin_file_path)
    except Exception as e:
        print(f"[ERROR] ファイルの読み込みに失敗: {e}")
        return False
    
    records = []
    msg_count = 0
    
    # すべてのメッセージを読み込み
    print("[INFO] OBSVメッセージを抽出中...")
    
    while True:
        msg = mlog.recv_match(blocking=False)
        if msg is None:
            break
        
        msg_type = msg.get_type()
        
        # OBSVメッセージのみを処理
        if msg_type == 'OBSV':
            try:
                record = {
                    "TimeUS": getattr(msg, 'TimeUS', 0),
                    "PLX": getattr(msg, 'PLX', 0.0),
                    "PLY": getattr(msg, 'PLY', 0.0),
                    "PLZ": getattr(msg, 'PLZ', 0.0),
                    "AX": getattr(msg, 'AX', 0.0),
                    "AY": getattr(msg, 'AY', 0.0),
                    "BX": getattr(msg, 'BX', 0.0),
                    "BY": getattr(msg, 'BY', 0.0),
                    "CX": getattr(msg, 'CX', 0.0),
                    "CY": getattr(msg, 'CY', 0.0),
                    "F": getattr(msg, 'F', 0.0),
                    "P": getattr(msg, 'P', 0.0),
                    "X": getattr(msg, 'X', 0.0),
                    "Y": getattr(msg, 'Y', 0.0),
                    "SW": getattr(msg, 'SW', 0),
                }
                records.append(record)
                msg_count += 1
                
                # デバッグ出力（最初の3件のみ）
                if msg_count <= 3:
                    print(f"[DEBUG] レコード {msg_count}: TimeUS={record['TimeUS']}, PLX={record['PLX']:.6f}, SW={record['SW']}")
                
                if msg_count % 50000 == 0:
                    print(f"[DEBUG] 処理中: {msg_count} レコード抽出")
            
            except Exception as e:
                print(f"[WARNING] メッセージ処理エラー: {e}")
                continue
    
    print(f"[INFO] 抽出レコード数: {len(records)}")
    
    # CSVに出力
    try:
        os.makedirs(os.path.dirname(csv_output_path) or '.', exist_ok=True)
        
        with open(csv_output_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            writer.writerows(records)
        
        print(f"[SUCCESS] CSV出力: {csv_output_path}")
        return True
    
    except Exception as e:
        print(f"[ERROR] CSV出力エラー: {e}")
        return False

def main():
    """
    メイン処理：設定セクションで指定されたBINファイルを処理します
    INPUT_BIN_FILE をプログラム冒頭で変更して使用してください
    """
    global INPUT_BIN_FILE, OUTPUT_DIRECTORY
    
    # 設定セクションから読み込むファイルを取得
    bin_file = INPUT_BIN_FILE
    
    # ファイルの存在確認
    if not os.path.exists(bin_file):
        print(f"[ERROR] ファイルが見つかりません: {bin_file}")
        print(f"[INFO] INPUT_BIN_FILE を確認してください: {bin_file}")
        sys.exit(1)
    
    # ファイル名から番号を抽出してCSV出力ファイル名を生成
    bin_filename = os.path.basename(bin_file)
    if bin_filename.endswith('.BIN'):
        file_number = bin_filename.replace('.BIN', '')
    else:
        file_number = bin_filename
    
    csv_file = os.path.join(OUTPUT_DIRECTORY, f"OBSV_data_{file_number}.csv")
    
    print(f"[INFO] 処理開始:")
    print(f"  入力: {bin_file}")
    print(f"  出力: {csv_file}")
    
    extract_obsv_new_format(bin_file, csv_file)


if __name__ == "__main__":
    main()

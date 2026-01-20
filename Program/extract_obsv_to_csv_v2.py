#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OBSVメッセージ抽出プログラム（改善版）
ARduPilot ログフォーマットに基づいて正確に解析
"""


import struct
import os
import sys
import csv
import math

class OBSVExtractorV2:
    def analyze_records(self, records):
        print("\n[ANALYZE] データ内容チェック")
        if not records:
            print("  レコードがありません")
            return

        timeus_list = [r['TimeUS'] for r in records]
        plx_list = [r['PLX'] for r in records]
        nan_count = 0
        inf_count = 0
        extreme_count = 0
        decreasing_count = 0
        duplicate_count = 0
        prev_timeus = None
        timeus_set = set()
        for t in timeus_list:
            if prev_timeus is not None:
                if t < prev_timeus:
                    decreasing_count += 1
                if t == prev_timeus:
                    duplicate_count += 1
            prev_timeus = t
            timeus_set.add(t)
        for r in records:
            for k, v in r.items():
                if isinstance(v, float):
                    if math.isnan(v):
                        nan_count += 1
                    if math.isinf(v):
                        inf_count += 1
                    if abs(v) > 1e10:
                        extreme_count += 1
        print(f"  総レコード数: {len(records)}")
        print(f"  TimeUS最小: {min(timeus_list)}")
        print(f"  TimeUS最大: {max(timeus_list)}")
        print(f"  TimeUS一意数: {len(timeus_set)}")
        print(f"  TimeUS減少回数: {decreasing_count}")
        print(f"  TimeUS重複回数: {duplicate_count}")
        print(f"  NaN値: {nan_count}")
        print(f"  Inf値: {inf_count}")
        print(f"  極端値(>|1e10|): {extreme_count}")
        print(f"  PLXサンプル: {plx_list[:5]}")
        if decreasing_count > 0:
            print("  [警告] TimeUSが減少する箇所があります")
        if nan_count > 0 or inf_count > 0:
            print("  [警告] NaN/Inf値を含むデータがあります")
        if extreme_count > 0:
            print("  [警告] 極端な値を含むデータがあります")
        print("[ANALYZE] チェック終了\n")
    def __init__(self, bin_file_path, csv_output_path):
        self.bin_file_path = bin_file_path
        self.csv_output_path = csv_output_path
        
        self.fields = [
            "TimeUS", "PLX", "PLY", "PLZ", 
            "AX", "AY", "BX", "BY", 
            "CX", "CY", "PRX", "PRY", 
            "PRZ", "ERR", "EST_FREQ", "CORR"
        ]
        
        self.messages = []
    
    def read_file_as_bytes(self):
        """ファイルを読み込む"""
        try:
            with open(self.bin_file_path, 'rb') as f:
                return f.read()
        except Exception as e:
            print(f"[ERROR] ファイル読み込みエラー: {e}")
            return None
    
    def find_obsv_with_headers(self, data):
        """OBSVメッセージとそのヘッダー情報を探す"""
        # "OBSV" の位置を探す
        obsv_positions = []
        start = 0
        
        while True:
            pos = data.find(b"OBSV", start)
            if pos == -1:
                break
            obsv_positions.append(pos)
            start = pos + 1
        
        print(f"[DEBUG] OBSV位置: {obsv_positions}")
        
        msg_info = []
        
        for obsv_pos in obsv_positions:
            # OBSVの直後の情報を解析
            offset = obsv_pos + 4
            
            # フォーマット文字列を読む（通常は Q (uint64) で始まる）
            try:
                fmt_char = chr(data[offset])
                print(f"[DEBUG] 位置 0x{obsv_pos:x}: フォーマット文字 = '{fmt_char}'")
                
                # 次の部分にCSVヘッダーがあると仮定
                header_marker = b"TimeUS,PLX"
                header_pos = data.find(header_marker, obsv_pos, obsv_pos + 300)
                
                if header_pos > 0:
                    # ヘッダーの終わり（改行）を探す
                    header_end = header_pos
                    while header_end < len(data) and data[header_end] not in [0x0a, 0x0d]:
                        header_end += 1
                    
                    header_line = data[header_pos:header_end].decode('utf-8', errors='ignore')
                    print(f"[DEBUG] ヘッダー: {header_line[:80]}")
                    
                    # ヘッダーの後、最初の ArduPilot メッセージヘッダー(0xA3 0x95)を探す
                    data_start = header_end
                    while data_start < len(data) and data[data_start] in [0x0a, 0x0d, 0x00]:
                        data_start += 1
                    
                    # 0xA3 0x95 を探す
                    search_limit = min(len(data), header_end + 100)
                    while data_start < search_limit:
                        if data_start + 2 < len(data) and data[data_start] == 0xA3 and data[data_start+1] == 0x95:
                            print(f"[DEBUG] 最初のメッセージヘッダー位置: 0x{data_start:x}")
                            break
                        data_start += 1
                    
                    msg_info.append({
                        'obsv_pos': obsv_pos,
                        'header_pos': header_pos,
                        'data_start': data_start,
                        'next_obsv': None,
                    })
            except Exception as e:
                print(f"[WARNING] 位置 0x{obsv_pos:x} での解析エラー: {e}")
        
        # 各メッセージの終了位置を設定
        for i in range(len(msg_info)):
            if i < len(msg_info) - 1:
                msg_info[i]['next_obsv'] = msg_info[i+1]['obsv_pos']
        
        return msg_info
    
    def extract_message_records(self, data, msg_info):
        """メッセージグループからデータレコードを抽出"""
        data_start = msg_info['data_start']
        end_pos = msg_info.get('next_obsv')
        if end_pos is None:
            end_pos = len(data)
        
        # ArduPilotメッセージヘッダー: 0xA3 0x95 + メッセージID (1バイト)
        # OBSVのメッセージIDを特定する必要がある
        # データレコードサイズ: ヘッダー(3) + TimeUS(8) + floats(15*4) = 71 bytes
        
        records = []
        current_pos = data_start
        msg_id = None
        
        # 最初のメッセージIDを特定
        if current_pos + 3 <= len(data):
            if data[current_pos] == 0xA3 and data[current_pos+1] == 0x95:
                msg_id = data[current_pos+2]
                print(f"[DEBUG] OBSVメッセージID: 0x{msg_id:02x}")
        
        if msg_id is None:
            print(f"[ERROR] メッセージIDを特定できません")
            return records
        
        # ファイル全体を走査してOBSVメッセージID (0xf9など) を持つメッセージを抽出
        print(f"[DEBUG] ファイル全体を走査してメッセージID 0x{msg_id:02x} を検索...")
        current_pos = 0
        scan_count = 0
        
        while current_pos + 71 <= len(data):
            try:
                # メッセージヘッダーをチェック
                if data[current_pos] == 0xA3 and data[current_pos+1] == 0x95:
                    current_msg_id = data[current_pos+2]
                    
                    # OBSVメッセージIDと一致する場合のみ処理
                    if current_msg_id == msg_id:
                        # データ部分を読み取り (ヘッダー3バイトをスキップ)
                        data_pos = current_pos + 3
                        
                        # TimeUS (8 bytes, uint64)
                        time_us = struct.unpack('<Q', data[data_pos:data_pos+8])[0]
                        
                        # floats (15 * 4 bytes)
                        floats_data = data[data_pos+8:data_pos+68]
                        floats = struct.unpack('<15f', floats_data)
                        
                        record = {
                            'TimeUS': time_us,
                            'PLX': floats[0],
                            'PLY': floats[1],
                            'PLZ': floats[2],
                            'AX': floats[3],
                            'AY': floats[4],
                            'BX': floats[5],
                            'BY': floats[6],
                            'CX': floats[7],
                            'CY': floats[8],
                            'PRX': floats[9],
                            'PRY': floats[10],
                            'PRZ': floats[11],
                            'ERR': floats[12],
                            'EST_FREQ': floats[13],
                            'CORR': floats[14],
                        }
                        
                        # デバッグ出力（最初の数レコードのみ）
                        if len(records) < 5:
                            print(f"[DEBUG] レコード {len(records)+1}: TimeUS={time_us}, PLX={floats[0]:.6f}, PLY={floats[1]:.6f}, PLZ={floats[2]:.6f}")
                        
                        records.append(record)
                        current_pos += 71  # ヘッダー(3) + データ(68)
                    else:
                        # 異なるメッセージIDなので3バイト進む
                        current_pos += 3
                    
                    scan_count += 1
                    if scan_count % 50000 == 0:
                        print(f"[DEBUG] 走査中... {len(records)} レコード抽出 (位置 0x{current_pos:x})")
                else:
                    current_pos += 1  # 1バイト進めて再検索

            except Exception as e:
                print(f"[DEBUG] レコード解析エラー (位置 0x{current_pos:x}): {e}")
                current_pos += 1

        # データ内容チェック
        print(f"[DEBUG] 抽出レコード数: {len(records)}")
        if len(records) > 0:
            self.analyze_records(records)
        
        return records
    
    def extract_all(self, data):
        """すべてのメッセージを抽出"""
        msg_infos = self.find_obsv_with_headers(data)
        print(f"\n[INFO] 検出されたOBSVメッセージグループ: {len(msg_infos)}\n")
        
        total_records = 0
        
        for idx, msg_info in enumerate(msg_infos):
            print(f"[INFO] メッセージグループ {idx + 1}:")
            print(f"  OBSV位置: 0x{msg_info['obsv_pos']:x}")
            print(f"  データ開始: 0x{msg_info['data_start']:x}")
            
            records = self.extract_message_records(data, msg_info)
            print(f"  ✓ 抽出: {len(records)} レコード")
            
            if len(records) > 0:
                print(f"    最初: TimeUS={records[0]['TimeUS']}, PLX={records[0]['PLX']:.6f}")
                if len(records) > 1:
                    print(f"    最後: TimeUS={records[-1]['TimeUS']}, PLX={records[-1]['PLX']:.6f}")
            
            self.messages.extend(records)
            total_records += len(records)
        
        print(f"\n[INFO] 合計 {total_records} レコード抽出")
        return total_records
    
    def write_csv(self):
        """CSVに出力"""
        try:
            with open(self.csv_output_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=self.fields)
                writer.writeheader()
                writer.writerows(self.messages)
            
            print(f"\n[SUCCESS] CSV出力: {self.csv_output_path}")
            return True
        except Exception as e:
            print(f"[ERROR] CSV出力エラー: {e}")
            return False
    
    def run(self):
        """実行"""
        print(f"[INFO] OBSV メッセージ抽出（改善版）")
        print(f"[INFO] 入力: {self.bin_file_path}")
        print(f"[INFO] 出力: {self.csv_output_path}")
        print(f"{'='*70}\n")
        
        data = self.read_file_as_bytes()
        if data is None:
            return False
        
        count = self.extract_all(data)
        if count == 0:
            print(f"[WARNING] レコードを抽出できませんでした")
            return False
        
        return self.write_csv()

def main():
    bin_file = "C:\\Users\\taki\\Local\\local\\BIN\\1\\00000404.BIN"
    csv_file = os.path.expanduser("~\\Downloads\\OBSV_data_00000404.csv")
    
    if not os.path.exists(bin_file):
        print(f"[ERROR] ファイルが見つかりません: {bin_file}")
        sys.exit(1)
    
    extractor = OBSVExtractorV2(bin_file, csv_file)
    success = extractor.run()
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()

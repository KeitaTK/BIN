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

class OBSVExtractorV2:
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
                    
                    # ヘッダーの直後からデータが始まる
                    data_start = header_end
                    while data_start < len(data) and data[data_start] in [0x0a, 0x0d, 0x00]:
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
        end_pos = msg_info.get('next_obsv', len(data))
        
        # データレコードサイズ: TimeUS (8) + floats (15*4) = 68 bytes
        record_size = 68
        
        records = []
        current_pos = data_start
        
        while current_pos + record_size <= end_pos:
            try:
                # TimeUS
                time_us = struct.unpack('<Q', data[current_pos:current_pos+8])[0]
                
                # floats
                floats_data = data[current_pos+8:current_pos+68]
                floats = struct.unpack('<15f', floats_data)
                
                # データの妥当性チェック
                # TimeUS は通常 1e12 ～ 1e15 程度（マイクロ秒）
                # floats は -1e5 ～ 1e5 程度
                
                valid = True
                
                # TimeUS の妥当性チェック
                if not (1e10 < time_us < 1e16):
                    print(f"[DEBUG] TimeUS が範囲外: {time_us}")
                    valid = False
                
                # float値の妥当性チェック
                if valid:
                    for i, f in enumerate(floats):
                        if f > 1e8 or f < -1e8:
                            if i not in [2, 9, 13, 14]:  # 一部フィールドは大きい値の可能性
                                print(f"[DEBUG] float[{i}] が範囲外: {f}")
                
                if valid:
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
                    records.append(record)
                    current_pos += record_size
                else:
                    break
                    
            except Exception as e:
                print(f"[DEBUG] レコード解析エラー (位置 0x{current_pos:x}): {e}")
                break
        
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
    bin_file = "C:\\Users\\taki\\Local\\local\\BIN\\1\\00000400.BIN"
    csv_file = "C:\\Users\\taki\\Local\\local\\BIN\\Program\\OBSV_data.csv"
    
    if not os.path.exists(bin_file):
        print(f"[ERROR] ファイルが見つかりません: {bin_file}")
        sys.exit(1)
    
    extractor = OBSVExtractorV2(bin_file, csv_file)
    success = extractor.run()
    
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()

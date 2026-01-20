#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OBSVメッセージ抽出プログラム（最終版）
ARduPilot ログフォーマットの正確な解析
"""

import struct
import os
import sys
import csv

class OBSVExtractorFinal:
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
    
    def parse_format_string(self, fmt_str):
        """フォーマット文字列をパース"""
        # フォーマット文字列の例: "sNNNNNNNNNNNNfff" or "Qffffffffffff"
        # s: signed, N: int32, f: float, Q: uint64
        
        struct_fmt = '<'  # little endian
        field_types = []
        
        for char in fmt_str:
            if char == 's':
                struct_fmt += 'b'
                field_types.append('int8')
            elif char == 'N':
                struct_fmt += 'I'
                field_types.append('int32')
            elif char == 'f':
                struct_fmt += 'f'
                field_types.append('float')
            elif char == 'Q':
                struct_fmt += 'Q'
                field_types.append('uint64')
            elif char == '-':
                # padding
                pass
        
        return struct_fmt, field_types
    
    def find_and_parse_obsv(self, data):
        """OBSVメッセージを検出して解析"""
        positions = []
        start = 0
        
        while True:
            pos = data.find(b"OBSV", start)
            if pos == -1:
                break
            positions.append(pos)
            start = pos + 1
        
        print(f"[INFO] 検出されたOBSVメッセージ位置: {len(positions)}")
        
        results = []
        
        for idx, obsv_pos in enumerate(positions):
            print(f"\n[INFO] メッセージ {idx + 1} の解析 (位置: 0x{obsv_pos:x}):")
            
            # ヘッダー行を探す
            header_marker = b"TimeUS,PLX"
            header_pos = data.find(header_marker, obsv_pos, obsv_pos + 300)
            
            if header_pos < 0:
                print(f"  [WARNING] ヘッダーが見つかりません")
                continue
            
            # ヘッダー行の終了位置
            header_end = header_pos
            while header_end < len(data) and data[header_end] not in [0x0a, 0x0d, 0x00]:
                header_end += 1
            
            header = data[header_pos:header_end].decode('utf-8', errors='ignore')
            print(f"  ヘッダー: {header[:80]}")
            
            # フォーマット行を探す (通常はフォーマット文字列 sNNNNNNNNNNNNfff など)
            fmt_pos = header_end + 1
            while fmt_pos < len(data) and data[fmt_pos] in [0x0a, 0x0d, 0x00]:
                fmt_pos += 1
            
            # フォーマット行の終了位置（改行またはnull）
            fmt_end = fmt_pos
            while fmt_end < len(data) and data[fmt_end] not in [0x0a, 0x0d, 0x00]:
                fmt_end += 1
            
            fmt_line = data[fmt_pos:fmt_end]
            
            # フォーマット行がフォーマット文字列のようかチェック
            is_format_line = any(c in fmt_line for c in [ord('s'), ord('N'), ord('f'), ord('Q'), ord('-')])
            
            if is_format_line:
                print(f"  フォーマット行: {fmt_line}")
                
                # 修飾子行を探す（Fで始まる）
                mod_pos = fmt_end + 1
                while mod_pos < len(data) and data[mod_pos] in [0x0a, 0x0d, 0x00]:
                    mod_pos += 1
                
                mod_end = mod_pos
                while mod_end < len(data) and data[mod_end] not in [0x0a, 0x0d, 0x00]:
                    mod_end += 1
                
                mod_line = data[mod_pos:mod_end]
                print(f"  修飾子行: {mod_line}")
                
                # データ開始位置
                data_pos = mod_end + 1
                while data_pos < len(data) and data[data_pos] in [0x0a, 0x0d, 0x00]:
                    data_pos += 1
            else:
                # フォーマット行が無い場合、ヘッダー直後がデータ
                data_pos = header_end + 1
                while data_pos < len(data) and data[data_pos] in [0x0a, 0x0d, 0x00]:
                    data_pos += 1
                print(f"  フォーマット行なし、データ直接開始")
            
            # 次のOBSVまたはファイル終了までのデータを抽出
            if idx < len(positions) - 1:
                end_pos = positions[idx + 1]
            else:
                end_pos = len(data)
            
            print(f"  データ範囲: 0x{data_pos:x} ～ 0x{end_pos:x}")
            
            # データレコードを抽出
            # TimeUS (8) + floats (15*4=60) = 68 bytes
            record_size = 68
            
            records = []
            current_pos = data_pos
            record_count = 0
            max_records = 10  # 最初の10レコードのみ抽出
            
            while current_pos + record_size <= end_pos and record_count < max_records:
                try:
                    time_us = struct.unpack('<Q', data[current_pos:current_pos+8])[0]
                    floats = struct.unpack('<15f', data[current_pos+8:current_pos+68])
                    
                    # 妥当性チェック
                    # TimeUS は通常 1e12 ～ 1e15 マイクロ秒（数日～数週間）
                    # floats は -1000 ～ 1000 程度の値
                    time_valid = (1e12 < time_us < 1e15)
                    
                    floats_valid = all(-1e5 < f < 1e5 for f in floats[:12])
                    
                    if time_valid and floats_valid:
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
                        record_count += 1
                    else:
                        if not time_valid:
                            print(f"    [DEBUG] TimeUS が範囲外: {time_us}")
                        break
                except Exception as e:
                    print(f"    [DEBUG] 解析エラー: {e}")
                    break
            
            print(f"  ✓ 抽出レコード数: {record_count}")
            
            if len(records) > 0:
                self.messages.extend(records)
                results.append({
                    'msg_num': idx + 1,
                    'obsv_pos': obsv_pos,
                    'record_count': record_count,
                })
        
        return results
    
    def write_csv(self):
        """CSVに出力"""
        try:
            with open(self.csv_output_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=self.fields)
                writer.writeheader()
                writer.writerows(self.messages)
            
            print(f"\n[SUCCESS] CSV出力完了: {self.csv_output_path}")
            print(f"[INFO] 合計 {len(self.messages)} レコード")
            
            return True
        except Exception as e:
            print(f"[ERROR] CSV出力エラー: {e}")
            return False
    
    def run(self):
        """実行"""
        print(f"[INFO] OBSV メッセージ抽出（最終版）")
        print(f"[INFO] 入力: {self.bin_file_path}")
        print(f"[INFO] 出力: {self.csv_output_path}")
        print(f"{'='*70}\n")
        
        data = self.read_file_as_bytes()
        if data is None:
            return False
        
        results = self.find_and_parse_obsv(data)
        
        if len(self.messages) == 0:
            print(f"\n[WARNING] レコードを抽出できませんでした")
            return False
        
        return self.write_csv()

def main():
    bin_file = "C:\\Users\\taki\\Local\\local\\BIN\\1\\00000400.BIN"
    csv_file = "C:\\Users\\taki\\Local\\local\\BIN\\Program\\OBSV_data.csv"
    
    if not os.path.exists(bin_file):
        print(f"[ERROR] ファイルが見つかりません: {bin_file}")
        sys.exit(1)
    
    extractor = OBSVExtractorFinal(bin_file, csv_file)
    success = extractor.run()
    
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()

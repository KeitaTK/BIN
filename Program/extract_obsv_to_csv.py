#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OBSVメッセージをCSVに抽出するプログラム
BINファイルから OBSV メッセージを解析し、CSVファイルに出力
"""

import struct
import os
import sys
import csv
from pathlib import Path

class OBSVtoCSVExtractor:
    def __init__(self, bin_file_path, csv_output_path):
        self.bin_file_path = bin_file_path
        self.csv_output_path = csv_output_path
        
        # OBSVメッセージのフィールド定義
        self.fields = [
            "TimeUS", "PLX", "PLY", "PLZ", 
            "AX", "AY", "BX", "BY", 
            "CX", "CY", "PRX", "PRY", 
            "PRZ", "ERR", "EST_FREQ", "CORR"
        ]
        
        self.messages = []
    
    def read_file_as_bytes(self):
        """バイナリファイルを読み込む"""
        try:
            with open(self.bin_file_path, 'rb') as f:
                return f.read()
        except Exception as e:
            print(f"[ERROR] ファイル読み込みエラー: {e}")
            return None
    
    def find_obsv_messages(self, data):
        """OBSVメッセージの位置を検索"""
        positions = []
        start = 0
        
        while True:
            pos = data.find(b"OBSV", start)
            if pos == -1:
                break
            positions.append(pos)
            start = pos + 1
        
        return positions
    
    def extract_message_data(self, data, obsv_pos):
        """OBSVメッセージからデータを抽出"""
        try:
            # OBSVの直後 + フォーマット情報（16バイト程度）を飛ばし
            # ヘッダー情報を探す
            
            # "TimeUS,PLX,..." という CSV ヘッダーを探す
            header_pattern = b"TimeUS,PLX"
            header_pos = data.find(header_pattern, obsv_pos, obsv_pos + 500)
            
            if header_pos == -1:
                return None
            
            # ヘッダー行の終端（改行まで）を探す
            header_end = header_pos
            while header_end < len(data) and data[header_end] not in [0x0a, 0x0d, 0x00]:
                header_end += 1
            
            # ヘッダー情報の直後からデータが始まると仮定
            # 次の改行を飛ばしてデータ開始
            data_start = header_end + 1
            while data_start < len(data) and data[data_start] in [0x0a, 0x0d]:
                data_start += 1
            
            # フォーマット情報行があるか確認
            # フォーマット行（例：sNNNNNNNNNNNNfff など）
            fmt_line_end = data_start
            while fmt_line_end < len(data) and data[fmt_line_end] not in [0x0a, 0x0d]:
                fmt_line_end += 1
            
            fmt_line = data[data_start:fmt_line_end]
            
            # フォーマット行の内容を確認
            # もしフォーマット文字列のようなら、その次がデータ
            if any(c in fmt_line for c in [b's', b'N', b'f', b'Q']):
                actual_data_start = fmt_line_end + 1
                while actual_data_start < len(data) and data[actual_data_start] in [0x0a, 0x0d, 0x00]:
                    actual_data_start += 1
            else:
                actual_data_start = data_start
            
            # TimeUS (8 bytes, uint64) + floats (15 * 4 = 60 bytes) = 68 bytes
            data_size = 8 + 15 * 4
            
            if actual_data_start + data_size <= len(data):
                # TimeUS
                time_us = struct.unpack('<Q', data[actual_data_start:actual_data_start+8])[0]
                
                # 15個のfloats
                floats_start = actual_data_start + 8
                floats = struct.unpack('<15f', data[floats_start:floats_start+60])
                
                message = {
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
                
                return message, actual_data_start + data_size
            
        except Exception as e:
            print(f"[WARNING] メッセージ解析エラー: {e}")
        
        return None
    
    def extract_all_messages(self, data):
        """すべてのOBSVメッセージを抽出"""
        obsv_positions = self.find_obsv_messages(data)
        print(f"[INFO] 検出されたOBSVメッセージ位置: {len(obsv_positions)} 個")
        
        extracted_count = 0
        
        for idx, obsv_pos in enumerate(obsv_positions):
            print(f"[INFO] メッセージ {idx + 1} を処理中... (位置: 0x{obsv_pos:x})")
            
            result = self.extract_message_data(data, obsv_pos)
            if result:
                message, next_pos = result
                self.messages.append(message)
                extracted_count += 1
                
                # デバッグ出力
                print(f"  ✓ 抽出成功: TimeUS={message['TimeUS']}, "
                      f"PLX={message['PLX']:.6f}, ERR={message['ERR']:.6f}")
                
                # 各メッセージから複数のログエントリを抽出しようとする
                # 次のメッセージまで探索
                if idx < len(obsv_positions) - 1:
                    next_obsv = obsv_positions[idx + 1]
                    current_pos = next_pos
                    
                    # 同じメッセージグループ内の追加データを探す
                    sub_count = 0
                    while current_pos < next_obsv - 100:
                        # 次のデータレコードを探す
                        # uint64 (TimeUS) として解析してみる
                        if current_pos + 8 + 60 <= next_obsv:
                            try:
                                time_us = struct.unpack('<Q', data[current_pos:current_pos+8])[0]
                                
                                # TimeUSが妥当な値か確認（マイクロ秒で通常は大きな値）
                                if 1e12 < time_us < 1e15:  # 妥当な範囲
                                    floats = struct.unpack('<15f', data[current_pos+8:current_pos+68])
                                    
                                    # floatsのすべてが妥当な範囲か確認
                                    valid = True
                                    for f in floats:
                                        if not (-1e6 < f < 1e6):  # 妥当な範囲
                                            valid = False
                                            break
                                    
                                    if valid:
                                        message = {
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
                                        self.messages.append(message)
                                        current_pos += 68
                                        sub_count += 1
                                        extracted_count += 1
                                    else:
                                        break
                                else:
                                    break
                            except:
                                break
                        else:
                            break
                    
                    if sub_count > 0:
                        print(f"  ✓ 追加: {sub_count} 個のデータレコードを抽出")
            else:
                print(f"  ✗ 抽出失敗")
        
        print(f"\n[INFO] 合計 {extracted_count} 個のメッセージを抽出")
        return extracted_count
    
    def write_to_csv(self):
        """CSVファイルに出力"""
        try:
            with open(self.csv_output_path, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=self.fields)
                
                # ヘッダー行を書き込み
                writer.writeheader()
                
                # データ行を書き込み
                for message in self.messages:
                    writer.writerow(message)
            
            print(f"\n[SUCCESS] CSVファイルを出力: {self.csv_output_path}")
            print(f"[INFO] 出力行数: {len(self.messages)} 行")
            
            return True
        except Exception as e:
            print(f"[ERROR] CSV出力エラー: {e}")
            return False
    
    def run(self):
        """実行"""
        print(f"[INFO] OBSVメッセージ抽出処理開始")
        print(f"[INFO] 入力ファイル: {self.bin_file_path}")
        print(f"[INFO] 出力ファイル: {self.csv_output_path}")
        print(f"{'='*70}\n")
        
        # ファイル読み込み
        data = self.read_file_as_bytes()
        if data is None:
            return False
        
        # メッセージ抽出
        self.extract_all_messages(data)
        
        if len(self.messages) == 0:
            print(f"\n[WARNING] メッセージを抽出できませんでした")
            return False
        
        # CSV出力
        return self.write_to_csv()

def main():
    bin_file = "C:\\Users\\taki\\Local\\local\\BIN\\1\\00000400.BIN"
    csv_file = "C:\\Users\\taki\\Local\\local\\BIN\\Program\\OBSV_data.csv"
    
    if not os.path.exists(bin_file):
        print(f"[ERROR] ファイルが見つかりません: {bin_file}")
        sys.exit(1)
    
    extractor = OBSVtoCSVExtractor(bin_file, csv_file)
    success = extractor.run()
    
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()

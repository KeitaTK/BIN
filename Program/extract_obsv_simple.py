#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OBSVメッセージをCSVに変換するプログラム
既知の有効なメッセージを抽出
"""

import struct
import os
import sys
import csv

class SimpleOBSVExtractor:
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
        try:
            with open(self.bin_file_path, 'rb') as f:
                return f.read()
        except Exception as e:
            print(f"[ERROR] ファイル読み込みエラー: {e}")
            return None
    
    def extract_messages(self, data):
        """データレコードを直接探索して抽出"""
        print("[INFO] バイナリデータをスキャン中...\n")
        
        record_size = 68  # TimeUS (8) + floats (15*4=60)
        found_count = 0
        
        # バイナリデータをスキャン
        for pos in range(0, len(data) - record_size, 4):
            try:
                # TimeUSを読む
                time_us = struct.unpack('<Q', data[pos:pos+8])[0]
                
                # 妥当性チェック（マイクロ秒）
                # 2020年1月1日～2030年12月31日：大体 1.58e15 ～ 1.89e15
                if not (1.5e15 < time_us < 2e15):
                    continue
                
                # floats を読む
                floats = struct.unpack('<15f', data[pos+8:pos+68])
                
                # floats の妥当性チェック
                valid = True
                for i, f in enumerate(floats[:12]):
                    # PLX, PLY, PLZ, AX, AY, BX, BY, CX, CY, PRX, PRY, PRZ は ±100以内が妥当
                    if abs(f) > 100:
                        valid = False
                        break
                
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
                    self.messages.append(record)
                    found_count += 1
                    
                    if found_count <= 3:
                        print(f"  [{found_count}] 位置: 0x{pos:08x}, TimeUS: {time_us}, PLX: {floats[0]:.4f}")
            except:
                pass
        
        print(f"\n[INFO] 合計 {found_count} レコード発見")
        return found_count
    
    def write_csv(self):
        """CSVに出力"""
        try:
            with open(self.csv_output_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=self.fields)
                writer.writeheader()
                writer.writerows(self.messages)
            
            print(f"[SUCCESS] CSV出力: {self.csv_output_path}")
            return True
        except Exception as e:
            print(f"[ERROR] CSV出力エラー: {e}")
            return False
    
    def run(self):
        print("[INFO] OBSV メッセージ抽出 - シンプル版")
        print(f"[INFO] 入力: {self.bin_file_path}")
        print(f"[INFO] 出力: {self.csv_output_path}")
        print(f"{'='*70}\n")
        
        data = self.read_file_as_bytes()
        if data is None:
            return False
        
        count = self.extract_messages(data)
        
        if count == 0:
            print("[WARNING] レコードを抽出できませんでした")
            return False
        
        return self.write_csv()

def main():
    bin_file = "C:\\Users\\taki\\Local\\local\\BIN\\1\\00000400.BIN"
    # ダウンロードフォルダに出力
    downloads_folder = os.path.expanduser("~\\Downloads")
    csv_file = os.path.join(downloads_folder, "OBSV_data.csv")
    
    if not os.path.exists(bin_file):
        print(f"[ERROR] ファイルが見つかりません: {bin_file}")
        sys.exit(1)
    
    extractor = SimpleOBSVExtractor(bin_file, csv_file)
    success = extractor.run()
    
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()

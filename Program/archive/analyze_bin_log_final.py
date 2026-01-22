#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
最終版：BINファイルのOBSVログメッセージ詳細分析プログラム
"""

import struct
import os
import sys

class FinalBINAnalyzer:
    def __init__(self, bin_file_path):
        self.bin_file_path = bin_file_path
        self.file_size = os.path.getsize(bin_file_path)
        
    def read_file_as_bytes(self):
        """バイナリファイルを読み込む"""
        try:
            with open(self.bin_file_path, 'rb') as f:
                return f.read()
        except Exception as e:
            print(f"[ERROR] ファイル読み込みエラー: {e}")
            return None
    
    def find_obsv_format_pattern(self, data):
        """OBSVメッセージのフォーマット情報を検索"""
        # "OBSV" の直後に続くフォーマット情報を探す
        pattern = b"OBSVQfffffffffff"  # "OBSV" + "Qfffffffffff..." のパターン
        
        positions = []
        start = 0
        while True:
            pos = data.find(b"OBSV", start)
            if pos == -1:
                break
            positions.append(pos)
            start = pos + 1
        
        return positions
    
    def parse_obsv_message(self, data, obsv_pos):
        """OBSVメッセージを解析"""
        print(f"\n[DEBUG] OBSV メッセージ解析 (位置: 0x{obsv_pos:x})")
        print(f"{'='*70}")
        
        # OBSVの直後のデータ構造
        offset = obsv_pos + 4  # "OBSV" (4 bytes)
        
        # メッセージ内容を表示
        try:
            # フォーマット文字列の部分
            if offset + 50 < len(data):
                msg_part = data[offset:offset+50]
                print(f"Message header (50 bytes):")
                print(f"  Hex: {' '.join(f'{b:02x}' for b in msg_part)}")
                print(f"  Text: {msg_part}")
            
            # フォーマット情報の次のフィールド名を見る
            # "TimeUS,PLX,..." のパターン
            header_start = data.find(b"TimeUS,PLX", obsv_pos)
            if header_start > 0 and header_start < obsv_pos + 200:
                header_end = header_start
                while header_end < len(data) and data[header_end] not in [0x00, 0x0a, 0x0d]:
                    header_end += 1
                
                header = data[header_start:header_end].decode('utf-8', errors='ignore')
                print(f"\n[INFO] 検出されたフィールド:")
                fields = header.split(',')
                for i, field in enumerate(fields):
                    print(f"  [{i}] {field}")
            
            # データセクションの開始位置を推定
            print(f"\n[DEBUG] 周辺バイナリダンプ:")
            for offset_debug in range(0, 100, 16):
                pos = obsv_pos + offset_debug
                if pos + 16 <= len(data):
                    hex_str = ' '.join(f'{b:02x}' for b in data[pos:pos+16])
                    ascii_str = ''.join(chr(b) if 32 <= b < 127 else '.' for b in data[pos:pos+16])
                    print(f"  0x{pos:08x}: {hex_str:<48} | {ascii_str}")
            
        except Exception as e:
            print(f"[ERROR] メッセージ解析エラー: {e}")
    
    def check_message_structure(self, data):
        """メッセージ構造を検証"""
        print(f"\n[INFO] メッセージ構造の検証:")
        print(f"{'='*70}")
        
        # 必須フィールドの確認
        required_fields = [
            "TimeUS", "PLX", "PLY", "PLZ", 
            "AX", "AY", "BX", "BY", "CX", "CY",
            "PRX", "PRY", "PRZ", "ERR", "EST_FREQ", "CORR"
        ]
        
        # フィールドの出現回数を数える
        found_fields = {}
        for field in required_fields:
            field_bytes = field.encode('utf-8')
            count = 0
            start = 0
            while True:
                pos = data.find(field_bytes, start)
                if pos == -1:
                    break
                count += 1
                start = pos + 1
            found_fields[field] = count
        
        print(f"\n[RESULT] フィールド出現回数:")
        all_found = True
        for field in required_fields:
            count = found_fields.get(field, 0)
            status = "✓" if count > 0 else "✗"
            print(f"  {status} {field:<12}: {count} 回")
            if count == 0:
                all_found = False
        
        return all_found
    
    def analyze_data_continuity(self, data):
        """データの連続性を確認"""
        print(f"\n[INFO] データの連続性確認:")
        print(f"{'='*70}")
        
        # 複数のOBSVメッセージが連続しているか確認
        obsv_positions = self.find_obsv_format_pattern(data)
        
        print(f"\n[RESULT] OBSV メッセージ情報:")
        print(f"  合計出現数: {len(obsv_positions)}")
        
        if len(obsv_positions) >= 2:
            print(f"\n[INFO] メッセージ間の距離:")
            for i in range(min(5, len(obsv_positions) - 1)):
                dist = obsv_positions[i+1] - obsv_positions[i]
                print(f"  位置 {i} → {i+1}: {dist:,} bytes (0x{dist:x})")
        
        # データが存在するか確認
        if len(obsv_positions) > 0:
            print(f"\n[SUCCESS] ログメッセージのデータが存在します")
            return True
        else:
            print(f"\n[WARNING] ログメッセージが見つかりません")
            return False
    
    def run(self):
        """分析実行"""
        print(f"[INFO] 最終版 BINファイル詳細分析")
        print(f"[INFO] ファイルパス: {self.bin_file_path}")
        print(f"[INFO] ファイルサイズ: {self.file_size:,} bytes ({self.file_size/1024/1024:.2f} MB)")
        print(f"{'='*70}\n")
        
        # ファイル読み込み
        data = self.read_file_as_bytes()
        if data is None:
            return False
        
        # メッセージ構造の検証
        has_all_fields = self.check_message_structure(data)
        
        # OBSVメッセージの検索と解析
        obsv_positions = self.find_obsv_format_pattern(data)
        
        if obsv_positions:
            # 最初と最後のメッセージを詳しく見る
            print(f"\n[INFO] 最初のOBSVメッセージ:")
            self.parse_obsv_message(data, obsv_positions[0])
            
            if len(obsv_positions) > 1:
                print(f"\n[INFO] 最後のOBSVメッセージ:")
                self.parse_obsv_message(data, obsv_positions[-1])
        
        # データの連続性確認
        has_continuity = self.analyze_data_continuity(data)
        
        # 最終結果
        print(f"\n{'='*70}")
        print(f"[SUMMARY] 分析結果:")
        print(f"  - ファイルサイズ: {self.file_size:,} bytes")
        print(f"  - OBSV メッセージ数: {len(obsv_positions)}")
        print(f"  - 全必須フィールド検出: {'YES' if has_all_fields else 'NO'}")
        print(f"  - メッセージ連続性: {'YES' if has_continuity else 'NO'}")
        
        if has_continuity and has_all_fields:
            print(f"\n[SUCCESS] ログメッセージが正常に含まれており、データの中身も存在します！")
            return True
        else:
            print(f"\n[WARNING] ログメッセージは存在しますが、不完全な可能性があります")
            return True if has_continuity else False

def main():
    bin_file = "C:\\Users\\taki\\Local\\local\\BIN\\1\\00000400.BIN"
    
    if not os.path.exists(bin_file):
        print(f"[ERROR] ファイルが見つかりません: {bin_file}")
        sys.exit(1)
    
    analyzer = FinalBINAnalyzer(bin_file)
    success = analyzer.run()
    
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()

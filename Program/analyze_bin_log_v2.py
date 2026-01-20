#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BINファイルのログメッセージ分析プログラム（改善版）
OBSVメッセージのフォーマットに基づいてデータを正しく解析
"""

import struct
import os
import sys
import re
from pathlib import Path

class BINLogAnalyzerV2:
    def __init__(self, bin_file_path):
        self.bin_file_path = bin_file_path
        self.file_size = os.path.getsize(bin_file_path)
        self.obsv_messages = []
        self.found_obsv = False
        
    def read_file_as_bytes(self):
        """バイナリファイルを読み込む"""
        try:
            with open(self.bin_file_path, 'rb') as f:
                data = f.read()
            return data
        except Exception as e:
            print(f"[ERROR] ファイル読み込みエラー: {e}")
            return None
    
    def search_log_structure(self, data):
        """ログの構造を分析"""
        # "TimeUS,PLX,PLY,PLZ" を検索してフォーマット情報の直後を見つける
        format_string = b"TimeUS,PLX,PLY,PLZ"
        
        positions = []
        start = 0
        while True:
            pos = data.find(format_string, start)
            if pos == -1:
                break
            positions.append(pos)
            start = pos + 1
        
        print(f"[INFO] ログフォーマット文字列の出現数: {len(positions)}")
        
        if len(positions) > 0:
            print(f"[INFO] 最初の出現位置: {positions[0]} (0x{positions[0]:x})")
            return positions
        
        return []
    
    def analyze_log_header(self, data, position, lookback=200):
        """ログヘッダーを分析"""
        print(f"\n[DEBUG] 位置 {position} (0x{position:x}) のヘッダー分析:")
        
        # フォーマット文字列の前をさかのぼってOBSVを探す
        start = max(0, position - lookback)
        context = data[start:position + 100]
        
        print(f"Hex dump from {start} to {position + 100}:")
        for i in range(0, len(context), 16):
            hex_part = ' '.join(f'{b:02x}' for b in context[i:i+16])
            ascii_part = ''.join(chr(b) if 32 <= b < 127 else '.' for b in context[i:i+16])
            print(f"  {start+i:08x}: {hex_part:<48} | {ascii_part}")
        
        # "OBSV" を前方検索
        obsv_search = data[start:position].rfind(b"OBSV")
        if obsv_search >= 0:
            actual_obsv_pos = start + obsv_search
            print(f"\n[DEBUG] OBSV位置: {actual_obsv_pos} (0x{actual_obsv_pos:x})")
            print(f"[DEBUG] 距離: {position - actual_obsv_pos} bytes")
    
    def extract_csv_header(self, data, position):
        """CSVヘッダーを抽出"""
        # position の位置からカンマで区切られたフィールド名を抽出
        start = position
        end = start
        
        # 改行またはNullまで探す
        while end < len(data) and data[end:end+1] not in [b'\n', b'\r', b'\x00']:
            end += 1
        
        try:
            header_line = data[start:end].decode('utf-8', errors='ignore')
            fields = [f.strip() for f in header_line.split(',')]
            return fields
        except:
            return []
    
    def analyze_data_section(self, data, format_pos):
        """フォーマット文字列の直後のデータセクションを分析"""
        print(f"\n[DEBUG] データセクション分析:")
        
        # "TimeUS,PLX,PLY,PLZ,..." を含む行の終端を探す
        line_end = format_pos
        while line_end < len(data) and data[line_end] != 0x0a:  # LF
            line_end += 1
        
        # CSV ヘッダー行
        header_line = data[format_pos:line_end]
        print(f"Header line (length={len(header_line)}): {header_line[:100]}")
        
        # フォーマット情報行の次を探す
        next_pos = line_end + 1
        
        # 次のいくつかの行の構造を確認
        print(f"\n[DEBUG] 次のデータ行:")
        
        line_count = 0
        current_pos = next_pos
        
        while line_count < 5 and current_pos < len(data):
            # 次の改行を探す
            line_end = current_pos
            while line_end < len(data) and data[line_end] != 0x0a:
                line_end += 1
            
            line = data[current_pos:line_end]
            
            if len(line) == 0:
                current_pos = line_end + 1
                continue
            
            # バイナリデータかテキストデータかを判断
            printable_chars = sum(1 for b in line if 32 <= b < 127)
            print(f"\n  Line {line_count}: pos={current_pos:08x}, len={len(line):3d}, printable={printable_chars:3d}")
            
            if printable_chars > len(line) * 0.7:
                # テキスト行
                try:
                    text = line.decode('utf-8', errors='ignore')
                    print(f"    Text: {text[:80]}")
                except:
                    pass
            else:
                # バイナリ行
                hex_str = ' '.join(f'{b:02x}' for b in line[:32])
                print(f"    Binary: {hex_str}...")
                
                # float データとして解析してみる
                if len(line) >= 8:
                    try:
                        # 最初の8バイトをuint64として
                        val = struct.unpack('<Q', line[:8])[0]
                        print(f"    [uint64] {val} (0x{val:016x})")
                        
                        # floatとして
                        if len(line) >= 4:
                            fval = struct.unpack('<f', line[:4])[0]
                            print(f"    [float] {fval}")
                    except:
                        pass
            
            line_count += 1
            current_pos = line_end + 1
    
    def run(self):
        """分析を実行"""
        print(f"[INFO] BINファイル分析開始（改善版）")
        print(f"[INFO] ファイルパス: {self.bin_file_path}")
        print(f"[INFO] ファイルサイズ: {self.file_size:,} bytes ({self.file_size/1024/1024:.2f} MB)")
        print(f"{'='*70}\n")
        
        # ファイルを読み込み
        data = self.read_file_as_bytes()
        if data is None:
            return False
        
        # ログフォーマット文字列を検索
        format_positions = self.search_log_structure(data)
        
        if not format_positions:
            print("[WARNING] ログフォーマット文字列が見つかりません")
            return False
        
        # 最初のいくつかのフォーマット位置を分析
        for idx, pos in enumerate(format_positions[:3]):
            print(f"\n{'='*70}")
            print(f"[INFO] フォーマット位置 {idx + 1}:")
            self.analyze_log_header(data, pos)
            self.analyze_data_section(data, pos)
        
        print(f"\n{'='*70}")
        print(f"[INFO] 分析完了")
        print(f"[SUCCESS] ログメッセージが含まれています")
        
        return True

def main():
    bin_file = "C:\\Users\\taki\\Local\\local\\BIN\\1\\00000400.BIN"
    
    if not os.path.exists(bin_file):
        print(f"[ERROR] ファイルが見つかりません: {bin_file}")
        sys.exit(1)
    
    analyzer = BINLogAnalyzerV2(bin_file)
    success = analyzer.run()
    
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()

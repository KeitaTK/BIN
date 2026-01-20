#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BINファイルのログメッセージ分析プログラム
OBSVメッセージの内容を検査し、データの中身を調査する
"""

import struct
import os
import sys
from pathlib import Path

# フォーマット文字列の定義
# フォーマット: OBSV, TimeUS, PLX, PLY, PLZ, AX, AY, BX, BY, CX, CY, PRX, PRY, PRZ, ERR, EST_FREQ, CORR
# sNNNNNNNNNNNNfff: s=signed, N=int32, f=float
# Expected data structure:
# - TimeUS: Q (uint64)
# - 13 floats (PLX, PLY, PLZ, AX, AY, BX, BY, CX, CY, PRX, PRY, PRZ, ERR)
# - 3 floats (EST_FREQ, CORR)

class BINLogAnalyzer:
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
            print(f"ファイル読み込みエラー: {e}")
            return None
    
    def search_obsv_message(self, data):
        """OBSVメッセージを検索"""
        # "OBSV" の文字列を検索
        search_string = b"OBSV"
        
        positions = []
        start = 0
        while True:
            pos = data.find(search_string, start)
            if pos == -1:
                break
            positions.append(pos)
            start = pos + 1
        
        print(f"[INFO] OBSVメッセージの出現数: {len(positions)}")
        
        if len(positions) > 0:
            self.found_obsv = True
            print(f"[INFO] 最初のOBSVメッセージ位置: {positions[0]} (0x{positions[0]:x})")
            if len(positions) > 1:
                print(f"[INFO] 最後のOBSVメッセージ位置: {positions[-1]} (0x{positions[-1]:x})")
            
            return positions
        else:
            print("[WARNING] OBSVメッセージが見つかりません")
            return []
    
    def analyze_nearby_data(self, data, position, context_bytes=100):
        """OBSVメッセージの周辺データを分析"""
        print(f"\n[DEBUG] 位置 {position} (0x{position:x}) のデータ分析:")
        print(f"=== 周辺データ（前後{context_bytes}バイト） ===")
        
        start = max(0, position - context_bytes)
        end = min(len(data), position + context_bytes + len(b"OBSV"))
        
        context = data[start:end]
        
        # 16進数表示
        print(f"Hex dump from {start} to {end}:")
        for i in range(0, len(context), 16):
            hex_part = ' '.join(f'{b:02x}' for b in context[i:i+16])
            ascii_part = ''.join(chr(b) if 32 <= b < 127 else '.' for b in context[i:i+16])
            print(f"  {start+i:08x}: {hex_part:<48} | {ascii_part}")
        
        # OBSVの直後のデータを解析
        if position + 4 < len(data):
            print(f"\n[DEBUG] OBSV直後のデータ:")
            offset = position + 4
            
            # フォーマット情報の後にデータが続くと仮定
            # TimeUS (Q: 8bytes)
            if offset + 8 <= len(data):
                try:
                    time_us = struct.unpack('<Q', data[offset:offset+8])[0]
                    print(f"  TimeUS (offset 0): {time_us} (0x{time_us:016x})")
                except:
                    print(f"  TimeUS: 読み込み失敗")
            
            # floats (4 bytes each)
            try:
                offset_floats = offset + 8
                if offset_floats + 52 <= len(data):  # 13 floats = 52 bytes
                    floats = struct.unpack('<13f', data[offset_floats:offset_floats+52])
                    print(f"  PLX, PLY, PLZ, AX, AY, BX, BY, CX, CY, PRX, PRY, PRZ, ERR:")
                    for i, val in enumerate(floats):
                        print(f"    [{i}]: {val:12.6f}")
                    
                    # EST_FREQ と CORR
                    offset_freq = offset_floats + 52
                    if offset_freq + 8 <= len(data):
                        freq_corr = struct.unpack('<2f', data[offset_freq:offset_freq+8])
                        print(f"  EST_FREQ: {freq_corr[0]:12.6f}")
                        print(f"  CORR: {freq_corr[1]:12.6f}")
            except Exception as e:
                print(f"  Float解析エラー: {e}")
    
    def check_data_validity(self, data, positions):
        """データの有効性をチェック"""
        print(f"\n[INFO] データの有効性チェック (最初の5個のメッセージを確認):")
        
        sample_count = min(5, len(positions))
        
        for idx in range(sample_count):
            pos = positions[idx]
            self.analyze_nearby_data(data, pos, context_bytes=50)
            print()
    
    def run(self):
        """分析を実行"""
        print(f"[INFO] BINファイル分析開始")
        print(f"[INFO] ファイルパス: {self.bin_file_path}")
        print(f"[INFO] ファイルサイズ: {self.file_size:,} bytes ({self.file_size/1024/1024:.2f} MB)")
        print(f"{'='*60}\n")
        
        # ファイルを読み込み
        data = self.read_file_as_bytes()
        if data is None:
            return False
        
        # OBSVメッセージを検索
        positions = self.search_obsv_message(data)
        
        # データの有効性をチェック
        if positions:
            self.check_data_validity(data, positions)
        
        print(f"\n{'='*60}")
        print(f"[INFO] 分析完了")
        
        if self.found_obsv:
            print(f"[SUCCESS] OBSVメッセージが含まれています")
        else:
            print(f"[WARNING] OBSVメッセージが見つかりません")
        
        return self.found_obsv

def main():
    bin_file = "C:\\Users\\taki\\Local\\local\\BIN\\1\\00000400.BIN"
    
    if not os.path.exists(bin_file):
        print(f"[ERROR] ファイルが見つかりません: {bin_file}")
        sys.exit(1)
    
    analyzer = BINLogAnalyzer(bin_file)
    success = analyzer.run()
    
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()

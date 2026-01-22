#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BINファイルのデータ構造を詳細に解析するプログラム
"""

import struct
import sys

def analyze_bin_structure(bin_file):
    """BINファイルの構造を詳細に解析"""
    
    print(f"[INFO] BINファイル構造解析: {bin_file}")
    print("="*70)
    
    with open(bin_file, 'rb') as f:
        data = f.read()
    
    print(f"\n[INFO] ファイルサイズ: {len(data)} bytes\n")
    
    # OBSVメッセージを探す
    obsv_pos = data.find(b"OBSV")
    if obsv_pos == -1:
        print("[ERROR] OBSVメッセージが見つかりません")
        return
    
    print(f"[INFO] OBSV位置: 0x{obsv_pos:x} ({obsv_pos})")
    print(f"\n[DEBUG] OBSV周辺のバイト列 (-32 ~ +128):")
    
    start = max(0, obsv_pos - 32)
    end = min(len(data), obsv_pos + 128)
    
    # バイト列を16進数とASCIIで表示
    for i in range(start, end, 16):
        hex_part = ' '.join(f'{b:02x}' for b in data[i:i+16])
        ascii_part = ''.join(chr(b) if 32 <= b < 127 else '.' for b in data[i:i+16])
        marker = " <-- OBSV" if i <= obsv_pos < i+16 else ""
        print(f"0x{i:08x}: {hex_part:<48} | {ascii_part}{marker}")
    
    # OBSVの後のフォーマット情報を解析
    print(f"\n[DEBUG] OBSVメッセージヘッダー解析:")
    offset = obsv_pos
    
    # ArduPilotのログフォーマット:
    # - メッセージヘッダー (通常2-3バイト): 0xA3, 0x95 + メッセージID
    # - その後に "OBSV" などのメッセージ名
    # - フォーマット記述子 (FMT)
    
    # OBSV前のヘッダーをチェック
    if obsv_pos >= 3:
        header_bytes = data[obsv_pos-3:obsv_pos]
        print(f"  OBSV直前3バイト: {' '.join(f'{b:02x}' for b in header_bytes)}")
        if header_bytes[0] == 0xA3 and header_bytes[1] == 0x95:
            msg_id = header_bytes[2]
            print(f"    → ArduPilotメッセージヘッダー検出 (ID={msg_id})")
    
    # OBSV直後を解析
    offset = obsv_pos + 4  # "OBSV"の後
    
    print(f"\n  OBSV+4以降のバイト:")
    for i in range(20):
        if offset + i < len(data):
            b = data[offset + i]
            print(f"    [{i}] 0x{b:02x} ({b:3d}) '{chr(b) if 32 <= b < 127 else '?'}'")
    
    # フォーマット記述子を探す
    print(f"\n[DEBUG] フォーマット記述子(FMT)を探索:")
    fmt_pos = data.find(b"FMT", 0, obsv_pos)
    if fmt_pos != -1:
        print(f"  FMT位置: 0x{fmt_pos:x}")
        # FMT周辺を表示
        start = max(0, fmt_pos - 16)
        end = min(len(data), fmt_pos + 200)
        for i in range(start, end, 16):
            hex_part = ' '.join(f'{b:02x}' for b in data[i:i+16])
            ascii_part = ''.join(chr(b) if 32 <= b < 127 else '.' for b in data[i:i+16])
            marker = " <-- FMT" if i <= fmt_pos < i+16 else ""
            print(f"  0x{i:08x}: {hex_part:<48} | {ascii_part}{marker}")
    
    # "TimeUS,PLX" などのヘッダーを探す
    print(f"\n[DEBUG] CSVヘッダーを探索:")
    header_marker = b"TimeUS,PLX"
    header_pos = data.find(header_marker, obsv_pos, obsv_pos + 300)
    
    if header_pos != -1:
        print(f"  ヘッダー位置: 0x{header_pos:x} ({header_pos})")
        print(f"  OBSVからのオフセット: +{header_pos - obsv_pos} bytes")
        
        # ヘッダー行を抽出
        header_end = header_pos
        while header_end < len(data) and data[header_end] not in [0x0a, 0x0d, 0x00]:
            header_end += 1
        
        header_line = data[header_pos:header_end].decode('utf-8', errors='ignore')
        print(f"  ヘッダー内容: {header_line}")
        
        # フォーマット文字列を探す (ヘッダーの前後)
        print(f"\n  ヘッダー周辺のバイト列:")
        start = max(0, header_pos - 64)
        end = min(len(data), header_pos + 16)
        for i in range(start, end, 16):
            hex_part = ' '.join(f'{b:02x}' for b in data[i:i+16])
            ascii_part = ''.join(chr(b) if 32 <= b < 127 else '.' for b in data[i:i+16])
            marker = " <-- Header" if i <= header_pos < i+16 else ""
            print(f"  0x{i:08x}: {hex_part:<48} | {ascii_part}{marker}")
        
        # データ開始位置を推定
        data_start = header_end
        while data_start < len(data) and data[data_start] in [0x0a, 0x0d, 0x00]:
            data_start += 1
        
        print(f"\n  推定データ開始: 0x{data_start:x} ({data_start})")
        print(f"  ヘッダー終了からのオフセット: +{data_start - header_end} bytes")
        
        # 最初のデータレコードを試し読み
        print(f"\n[DEBUG] 最初のデータレコード試し読み (Q + 15f = 68 bytes):")
        if data_start + 68 <= len(data):
            try:
                time_us = struct.unpack('<Q', data[data_start:data_start+8])[0]
                floats = struct.unpack('<15f', data[data_start+8:data_start+68])
                
                print(f"  TimeUS: {time_us}")
                print(f"  PLX: {floats[0]:.6f}")
                print(f"  PLY: {floats[1]:.6f}")
                print(f"  PLZ: {floats[2]:.6f}")
                print(f"  AX:  {floats[3]:.6f}")
                print(f"  AY:  {floats[4]:.6f}")
                print(f"  BX:  {floats[5]:.6f}")
                print(f"  BY:  {floats[6]:.6f}")
                print(f"  CX:  {floats[7]:.6f}")
                print(f"  CY:  {floats[8]:.6f}")
                print(f"  PRX: {floats[9]:.6f}")
                print(f"  PRY: {floats[10]:.6f}")
                print(f"  PRZ: {floats[11]:.6f}")
                print(f"  ERR: {floats[12]:.6f}")
                print(f"  EST_FREQ: {floats[13]:.6f}")
                print(f"  CORR: {floats[14]:.6f}")
                
                # TimeUSが妥当な範囲かチェック
                if time_us > 0 and time_us < 1e15:
                    print(f"  → TimeUSは妥当な範囲です")
                else:
                    print(f"  [警告] TimeUSが異常です")
                
                # 2番目のレコードも試し読み
                print(f"\n[DEBUG] 2番目のデータレコード:")
                data_pos2 = data_start + 68
                if data_pos2 + 68 <= len(data):
                    time_us2 = struct.unpack('<Q', data[data_pos2:data_pos2+8])[0]
                    floats2 = struct.unpack('<15f', data[data_pos2+8:data_pos2+68])
                    print(f"  TimeUS: {time_us2}")
                    print(f"  PLX: {floats2[0]:.6f}")
                    print(f"  PLY: {floats2[1]:.6f}")
                    print(f"  PLZ: {floats2[2]:.6f}")
                    
                    # TimeUSの差分チェック
                    if time_us2 > time_us:
                        delta = time_us2 - time_us
                        print(f"  TimeUS差分: {delta} μs ({delta/1000:.3f} ms)")
                    else:
                        print(f"  [警告] TimeUSが減少しています")
                
            except Exception as e:
                print(f"  [ERROR] 読み取りエラー: {e}")
        
        # データブロックの先頭数バイトを生表示
        print(f"\n  データブロック先頭80バイト(16進数):")
        for i in range(0, 80, 16):
            if data_start + i + 16 <= len(data):
                hex_part = ' '.join(f'{b:02x}' for b in data[data_start+i:data_start+i+16])
                print(f"  0x{data_start+i:08x}: {hex_part}")
    
    else:
        print(f"  ヘッダー 'TimeUS,PLX' が見つかりません")
    
    # ArduPilotログの一般的なメッセージヘッダーを探す
    print(f"\n[DEBUG] ArduPilotメッセージヘッダー(0xA3 0x95)の検索:")
    header_count = 0
    pos = 0
    while pos < min(len(data), 10000):  # 最初の10KB内を検索
        if data[pos] == 0xA3 and pos + 1 < len(data) and data[pos+1] == 0x95:
            msg_id = data[pos+2] if pos + 2 < len(data) else 0
            print(f"  位置 0x{pos:x}: メッセージID={msg_id}")
            header_count += 1
            if header_count >= 20:
                print(f"  ... (以下省略)")
                break
            pos += 3
        else:
            pos += 1
    
    print(f"\n[INFO] 解析完了")

if __name__ == "__main__":
    bin_file = "C:\\Users\\taki\\Local\\local\\BIN\\1\\00000404.BIN"
    analyze_bin_structure(bin_file)

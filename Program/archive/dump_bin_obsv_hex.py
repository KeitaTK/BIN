#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BINファイルのOBSVメッセージ周辺を16進ダンプ＋構造確認
"""
import sys

def dump_obsv_hex(bin_file_path, max_count=10):
    with open(bin_file_path, 'rb') as f:
        data = f.read()
    print(f"[INFO] ファイルサイズ: {len(data)} bytes")
    # OBSVメッセージID検出
    obsv_id = None
    pos = 0
    while pos < len(data):
        if data[pos:pos+4] == b"OBSV":
            for back in range(1, 10):
                if pos-back-2 >= 0 and data[pos-back-2] == 0xA3 and data[pos-back-1] == 0x95:
                    obsv_id = data[pos-back]
                    print(f"[INFO] OBSVメッセージID: 0x{obsv_id:02x} (位置0x{pos:x})")
                    break
            break
        pos += 1
    if obsv_id is None:
        print("[ERROR] OBSVメッセージIDが見つかりません")
        return
    # 全体を走査し、OBSVメッセージをダンプ
    count = 0
    pos = 0
    while pos + 3 + 8 + 12*4 + 16 <= len(data):
        if data[pos] == 0xA3 and data[pos+1] == 0x95 and data[pos+2] == obsv_id:
            print(f"\n[OBSV] 位置0x{pos:x}")
            hexline = ' '.join(f'{b:02x}' for b in data[pos:pos+3+8+12*4+16])
            print(f"  {hexline}")
            count += 1
            if count >= max_count:
                break
            pos += 3 + 8 + 12*4 + 16
        else:
            pos += 1
    print(f"[INFO] OBSVメッセージ {count}件ダンプ")

if __name__ == "__main__":
    bin_file = "C:\\Users\\taki\\Local\\local\\BIN\\1\\00000412.BIN"
    dump_obsv_hex(bin_file)

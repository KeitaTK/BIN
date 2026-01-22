# Program フォルダ機能一覧

このドキュメントは `Program` フォルダ内の各Pythonスクリプトの主な機能をまとめたものです。

## スクリプト一覧と機能

- **analyze_bin_log.py**
  - BINログファイルの基本的なバイナリ解析・データ抽出

- **analyze_bin_log_final.py**
  - BINログファイルの最終解析版。多機能・最終成果物向け

- **analyze_bin_log_v2.py**
  - BINログファイルの解析（v2：改良版・追加機能あり）

- **Convert_CSV.py**
  - ArduPilot .binログファイルからデータを抽出してCSVに変換（pymavlink使用）

- **extract_mode_switch.py**
  - モード切替イベントの抽出

- **extract_obsv_to_csv_new_format.py**
  - 新しいAP_Observerログフォーマット（TimeUS,PLX,PLY,PLZ,AX,AY,BX,BY,CX,CY,F,P,X,Y）対応の抽出・CSV化（現行推奨）
  - **pymavlinkライブラリを使用** して正しいメッセージ形式で解析

- **extract_sidd_sids_info.py**
  - SIDD/SIDS関連情報の抽出

- **FDM.py**
  - 飛行力学モデルやシミュレーション関連の処理

---

## OBSVデータ抽出方法（重要）

### 背景
ArduPilotログは**Binary MAVLink形式**で、各メッセージが個別のレコードとしてバラバラに格納されています。  
単純なバイナリダンプでは不正なデータ混合が発生します。

### 正しい抽出方法
**`pymavlink`ライブラリを使用して、メッセージIDとFMT定義に基づいて正しく解析する**

```python
from pymavlink import mavutil

mlog = mavutil.mavlink_connection(bin_file_path)

while True:
    msg = mlog.recv_match(blocking=False)
    if msg is None:
        break
    
    if msg.get_type() == 'OBSV':  # メッセージ型で選別
        # msg.TimeUS, msg.PLX, msg.PLY, ... でアクセス
        record = {
            "TimeUS": msg.TimeUS,
            "PLX": msg.PLX,
            "PLY": msg.PLY,
            ...
        }
```

### 実装例
[`extract_obsv_to_csv_new_format.py`](extract_obsv_to_csv_new_format.py) を参照

### ポイント
- ✅ `pymavlink.mavutil.mavlink_connection()` でBINファイルを開く
- ✅ `recv_match()` でメッセージを順次読み込み
- ✅ `msg.get_type()` でメッセージ型を判定
- ✅ 属性アクセス（`msg.TimeUS` など）でフィールド値を取得
- ✅ 各メッセージが正しい型・フォーマットで解析される

---

### archive フォルダ
- **extract_obsv_to_csv.py, extract_obsv_to_csv_v2.py, analyze_bin_structure.py, dump_bin_obsv_hex.py**
  - 古い形式や一時的な抽出・解析スクリプト（参考用・非推奨）

---

## 備考
- 詳細な引数や出力仕様は各スクリプトの先頭コメント・関数定義を参照
- 修正時は本READMEの抽出方法セクションを参考に実装してください

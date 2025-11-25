"""
Ardupilot .binログファイルからデータを抽出してCSVに変換するプログラム
"""
import os
from pathlib import Path
from pymavlink import mavutil
import csv


def extract_bin_to_csv(bin_file_path, message_fields):
    """
    .binファイルからデータを抽出してCSVに保存
    
    Parameters:
    -----------
    bin_file_path : str
        .binファイルのパス
    message_fields : list of tuple
        抽出するメッセージとフィールドのリスト
        例: [('SIDD', 'Gx'), ('SIDD', 'Gy'), ('IMU', 'AccX')]
    """
    
    # ファイルが存在するか確認
    if not os.path.exists(bin_file_path):
        print(f"エラー: ファイルが見つかりません: {bin_file_path}")
        return
    
    # 出力ファイル名を作成
    bin_filename = Path(bin_file_path).stem
    downloads_folder = Path.home() / "Downloads"
    csv_file_path = downloads_folder / f"{bin_filename}.csv"
    
    # ダウンロードフォルダが存在しない場合は作成
    downloads_folder.mkdir(parents=True, exist_ok=True)
    
    print(f"読み込み: {bin_file_path}")
    print(f"出力先: {csv_file_path}")
    
    # .binファイルを開く
    try:
        mlog = mavutil.mavlink_connection(bin_file_path)
    except Exception as e:
        print(f"エラー: .binファイルの読み込みに失敗しました: {e}")
        return
    
    # データを格納する辞書 {timestamp: {(msg_type, field): value}}
    data_dict = {}
    
    # すべてのメッセージを読み込み
    print("データを読み込んでいます...")
    message_count = 0
    
    while True:
        msg = mlog.recv_match()
        if msg is None:
            break
        
        msg_type = msg.get_type()
        
        # 指定されたメッセージタイプかチェック
        for msg_name, field_name in message_fields:
            if msg_type == msg_name:
                # タイムスタンプを取得
                timestamp = getattr(msg, 'TimeUS', None)
                if timestamp is None:
                    timestamp = getattr(msg, 'TimeMS', None)
                    if timestamp is not None:
                        timestamp = timestamp * 1000  # MSをUSに変換
                
                if timestamp is None:
                    continue
                
                # フィールド値を取得
                field_value = getattr(msg, field_name, None)
                
                if field_value is not None:
                    if timestamp not in data_dict:
                        data_dict[timestamp] = {}
                    data_dict[timestamp][(msg_name, field_name)] = field_value
                    message_count += 1
    
    print(f"読み込み完了: {message_count}個のデータポイント")
    
    # タイムスタンプでソート
    sorted_timestamps = sorted(data_dict.keys())
    
    # CSVに書き込み
    print("CSVファイルに書き込んでいます...")
    
    with open(csv_file_path, 'w', newline='', encoding='utf-8') as csvfile:
        # ヘッダー作成
        headers = ['時刻(us)']
        for msg_name, field_name in message_fields:
            headers.append(f"{msg_name}.{field_name}")
        
        writer = csv.writer(csvfile)
        writer.writerow(headers)
        
        # データ行を書き込み
        for timestamp in sorted_timestamps:
            row = [timestamp]
            for msg_name, field_name in message_fields:
                value = data_dict[timestamp].get((msg_name, field_name), '')
                row.append(value)
            writer.writerow(row)
    
    print(f"完了: {len(sorted_timestamps)}行のデータを書き込みました")
    print(f"保存先: {csv_file_path}")


if __name__ == "__main__":
    # ============================================================
    # ここで設定を変更してください
    # ============================================================
    
    # 読み込む.binファイルのパス
    BIN_FILE_PATH = r"c:\Users\taki\Local\local\BIN\1\00000174.BIN"
    
    # 抽出するデータ (メッセージ名, フィールド名) のリスト
    # 上から順番にCSVの列として記録されます
    MESSAGE_FIELDS = [
        # RATE: 制御器出力 u(t)
        ('RATE', 'ROut'),  # ロール軸のレート制御器出力 u_roll
        ('RATE', 'POut'),  # ピッチ軸のレート制御器出力 u_pitch
        
        # SIDD: 角速度センサ値 y(t)
        ('SIDD', 'Gx'),    # ロール軸角速度 y_roll (生ジャイロ値、X軸)
        ('SIDD', 'Gy'),    # ピッチ軸角速度 y_pitch (生ジャイロ値、Y軸)
    ]
    
    # ============================================================
    
    # データを抽出
    extract_bin_to_csv(BIN_FILE_PATH, MESSAGE_FIELDS)

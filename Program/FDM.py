#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ArduPilot System Identification 解析ツール
自動SYSID時間検出 + ボード線図 + コヒーレンス + ステップ応答推定

公式方法に準拠:
- pymavlink (ArduPilot BINファイル読み込み)
- scipy.signal.welch (パワースペクトル密度計算)
- control パッケージ (SISO/MIMO システム解析)
"""

import os
import sys
from pathlib import Path
from typing import Tuple, List, Optional, Dict
import warnings

import numpy as np
import matplotlib.pyplot as plt
from scipy import signal
from scipy.signal import welch, csd
from scipy.optimize import least_squares

# ArduPilot関連パッケージ
try:
    from pymavlink import mavutil
except ImportError:
    print("エラー: pymavlink がインストールされていません")
    print("インストール: pip install pymavlink")
    sys.exit(1)

# 制御工学パッケージ
try:
    import control as ctl
except ImportError:
    print("エラー: control がインストールされていません")
    print("インストール: pip install control")
    sys.exit(1)


# ============================================================
# 設定セクション（ここで変更してください）
# ============================================================

class Config:
    """解析設定"""
    
    # ====== ログファイル設定 ======
    # 読み込む .BIN ファイルのパス
    # BIN_FILE_PATH = r"1\00000174.BIN"
    BIN_FILE_PATH = r"1\00000315.BIN"
    
    # 解析するデータタイプを選択
    # - "roll": Roll Rate Loop (RATE.ROut -> SIDD.Gx)
    # - "pitch": Pitch Rate Loop (RATE.POut -> SIDD.Gy)
    # - "yaw": Yaw Rate Loop (RATE.YOut -> SIDD.Gz)
    ANALYSIS_TYPE = "roll"  # ← 変更してください
    
    # 時間範囲（秒）
    # None の場合は自動検出（推奨）
    TIME_START = None  # 自動検出
    TIME_END = None    # 自動検出
    
    # 周波数範囲（Hz、または rad/s）
    FREQ_START = 0.5   # [Hz]
    FREQ_END = 100     # [Hz]
    
    # ====== 出力設定 ======
    # 出力フォルダ（ここに結果が保存されます）
    # None の場合は "カレントディレクトリ/results/{ログ名}"
    OUTPUT_DIR = None
    
    # グラフ保存形式
    SAVE_FORMAT = 'png'  # 'png', 'pdf', 'jpg'
    DPI = 150  # 解像度
    
    # CSVファイルも出力するか
    EXPORT_CSV = True


# ============================================================
# ユーティリティ関数
# ============================================================

def read_mavlink_log(bin_path: str) -> Dict[str, Dict]:
    """
    ArduPilot BINファイルを読み込んでメッセージデータを辞書に格納
    
    Returns:
    --------
    messages : dict
        メッセージ名をキーとし、各メッセージのデータを含む辞書
    """
    print(f"[DEBUG] BINファイル読み込み開始: {bin_path}")
    
    messages = {}
    mlog = mavutil.mavlink_connection(bin_path)
    
    msg_count = 0
    while True:
        msg = mlog.recv_match(blocking=False)
        if msg is None:
            break
        
        msg_type = msg.get_type()
        if msg_type == 'BAD_DATA':
            continue
        
        # メッセージタイプごとに辞書を作成
        if msg_type not in messages:
            messages[msg_type] = {'timestamp': [], 'data': {}}
        
        # タイムスタンプを取得
        timestamp = getattr(msg, 'TimeUS', None)
        if timestamp is None:
            timestamp = getattr(msg, '_timestamp', msg_count * 1000)
        
        messages[msg_type]['timestamp'].append(timestamp)
        
        # 全フィールドを格納
        msg_dict = msg.to_dict()
        for key, value in msg_dict.items():
            if key not in messages[msg_type]['data']:
                messages[msg_type]['data'][key] = []
            messages[msg_type]['data'][key].append(value)
        
        msg_count += 1
        if msg_count % 10000 == 0:
            print(f"[DEBUG] 読み込み中: {msg_count} メッセージ")
    
    # リストをNumPy配列に変換
    for msg_type in messages:
        messages[msg_type]['timestamp'] = np.array(messages[msg_type]['timestamp'])
        for key in messages[msg_type]['data']:
            messages[msg_type]['data'][key] = np.array(messages[msg_type]['data'][key])
    
    print(f"[DEBUG] 読み込み完了: {len(messages)} 種類のメッセージ、合計 {msg_count} メッセージ")
    print(f"[DEBUG] 利用可能なメッセージタイプ: {list(messages.keys())}")
    
    return messages


def get_sysid_time_range(messages: Dict) -> Tuple[float, float]:
    """
    ログファイルからSYSID_MODEの時間範囲を自動検出
    
    Returns:
    --------
    (start_time_sec, end_time_sec) : tuple
        SYSID_MODEが有効だった時間範囲（秒）
    """
    print("[DEBUG] SYSID_MODE時間範囲の検出開始")
    

    try:
        # SIDD/SIDS優先
        if 'SIDD' in messages and len(messages['SIDD']['timestamp']) > 0:
            sidd_times = messages['SIDD']['timestamp'] / 1e6
            start_time_sec = sidd_times[0]
            end_time_sec = sidd_times[-1]
            print(f"✓ SIDDメッセージベースでSYSID期間を決定: {start_time_sec:.2f} - {end_time_sec:.2f} s (期間: {end_time_sec - start_time_sec:.2f} s)")
            return start_time_sec, end_time_sec
        if 'SIDS' in messages and len(messages['SIDS']['timestamp']) > 0:
            sids_times = messages['SIDS']['timestamp'] / 1e6
            start_time_sec = sids_times[0]
            end_time_sec = sids_times[-1]
            print(f"✓ SIDSメッセージベースでSYSID期間を決定: {start_time_sec:.2f} - {end_time_sec:.2f} s (期間: {end_time_sec - start_time_sec:.2f} s)")
            return start_time_sec, end_time_sec

        # SIDD/SIDSがなければ従来通りMODEで推定
        if 'MODE' not in messages:
            print("[DEBUG] MODEメッセージが見つかりません")
            return None, None

        mode_data = messages['MODE']
        times_us = mode_data['timestamp']
        print("[DEBUG] MODEメッセージの利用可能なフィールド:", list(mode_data['data'].keys()))
        modes = None
        mode_field_name = None
        for field_name in ['Mode', 'ModeNum', 'CNum']:
            if field_name in mode_data['data']:
                modes = mode_data['data'][field_name]
                mode_field_name = field_name
                print(f"[DEBUG] モードフィールド '{field_name}' を使用")
                break
        if modes is None:
            print("[DEBUG] Mode フィールドが見つかりません")
            return None, None
        unique_modes = np.unique(modes)
        print(f"[DEBUG] 利用可能なモード値: {unique_modes}")
        for mode_val in unique_modes:
            mode_indices = np.where(modes == mode_val)[0]
            if len(mode_indices) > 0:
                start_t = times_us[mode_indices[0]] / 1e6
                end_t = times_us[mode_indices[-1]] / 1e6
                duration = end_t - start_t
                print(f"[DEBUG] モード {mode_val}: {start_t:.2f}s - {end_t:.2f}s (期間: {duration:.2f}s, {len(mode_indices)} サンプル)")
        POSSIBLE_SYSID_MODES = [29, 26, 25]
        sysid_indices = None
        used_mode = None
        for sysid_mode in POSSIBLE_SYSID_MODES:
            sysid_indices = np.where(modes == sysid_mode)[0]
            if len(sysid_indices) > 0:
                used_mode = sysid_mode
                print(f"[DEBUG] SYSID_MODE {sysid_mode} を検出")
                start_idx = sysid_indices[0]
                end_idx = sysid_indices[-1]
                start_time_sec = times_us[start_idx] / 1e6
                end_time_sec = times_us[end_idx] / 1e6
                print(f"✓ SYSID_MODE (モード {used_mode}) 検出: {start_time_sec:.2f} - {end_time_sec:.2f} s (期間: {end_time_sec - start_time_sec:.2f} s)")
                return start_time_sec, end_time_sec
        print("[DEBUG] SYSID_MODE のデータが見つかりません")
        return None, None
    except Exception as e:
        print(f"[DEBUG] エラー: SYSID期間決定失敗: {e}")
        import traceback
        traceback.print_exc()
        return None, None


def extract_data(messages: Dict, 
                 start_time: float, 
                 end_time: float,
                 analysis_type: str) -> Tuple[np.ndarray, np.ndarray, np.ndarray, float]:
    """
    ログからデータを抽出
    
    Parameters:
    -----------
    messages : Dict
        読み込んだメッセージデータ
    start_time : float
        開始時刻（秒）
    end_time : float
        終了時刻（秒）
    analysis_type : str
        'roll', 'pitch', または 'yaw'
    
    Returns:
    --------
    (time, input_signal, output_signal, sample_rate) : tuple
    """
    print(f"[DEBUG] データ抽出開始: {analysis_type} 軸")
    
    # メッセージマッピング
    msg_map = {
        'roll': ('RATE', 'ROut', 'SIDD', 'Gx'),
        'pitch': ('RATE', 'POut', 'SIDD', 'Gy'),
        'yaw': ('RATE', 'YOut', 'SIDD', 'Gz'),
    }
    
    if analysis_type not in msg_map:
        raise ValueError(f"analysis_type は 'roll', 'pitch', 'yaw' のいずれかです")
    
    rate_msg, rate_field, sidd_msg, sidd_field = msg_map[analysis_type]
    
    try:
        # RATE メッセージを取得（入力信号 u(t)）
        if rate_msg not in messages:
            raise ValueError(f"{rate_msg} メッセージが見つかりません")
        
        rate_data = messages[rate_msg]
        rate_times_us = rate_data['timestamp']
        rate_values = rate_data['data'].get(rate_field, None)
        
        if rate_values is None:
            print(f"[DEBUG] {rate_msg} の利用可能なフィールド: {list(rate_data['data'].keys())}")
            raise ValueError(f"{rate_msg}.{rate_field} フィールドが見つかりません")
        
        print(f"[DEBUG] {rate_msg}.{rate_field} データポイント数: {len(rate_values)}")
        
        # SIDD メッセージを取得（出力信号 y(t)）
        if sidd_msg not in messages:
            raise ValueError(f"{sidd_msg} メッセージが見つかりません")
        
        sidd_data = messages[sidd_msg]
        sidd_times_us = sidd_data['timestamp']
        sidd_values = sidd_data['data'].get(sidd_field, None)
        
        if sidd_values is None:
            print(f"[DEBUG] {sidd_msg} の利用可能なフィールド: {list(sidd_data['data'].keys())}")
            raise ValueError(f"{sidd_msg}.{sidd_field} フィールドが見つかりません")
        
        print(f"[DEBUG] {sidd_msg}.{sidd_field} データポイント数: {len(sidd_values)}")
        
        # 時間範囲でフィルタ
        rate_mask = (rate_times_us >= start_time * 1e6) & (rate_times_us <= end_time * 1e6)
        sidd_mask = (sidd_times_us >= start_time * 1e6) & (sidd_times_us <= end_time * 1e6)
        
        rate_times = rate_times_us[rate_mask] / 1e6  # us -> sec
        rate_vals = rate_values[rate_mask]
        
        sidd_times = sidd_times_us[sidd_mask] / 1e6
        sidd_vals = sidd_values[sidd_mask]
        
        print(f"[DEBUG] フィルタ後の {rate_msg} データポイント数: {len(rate_vals)}")
        print(f"[DEBUG] フィルタ後の {sidd_msg} データポイント数: {len(sidd_vals)}")
        
        if len(rate_vals) == 0 or len(sidd_vals) == 0:
            raise ValueError(f"指定時間範囲にデータが見つかりません")
        
        # タイムスタンプを揃える（線形補間）
        # 共通の時間軸を作成
        t_min = max(rate_times[0], sidd_times[0])
        t_max = min(rate_times[-1], sidd_times[-1])
        
        # より細かい方のサンプリングレートを使用
        dt_rate = np.mean(np.diff(rate_times)) if len(rate_times) > 1 else 0.01
        dt_sidd = np.mean(np.diff(sidd_times)) if len(sidd_times) > 1 else 0.01
        dt = min(dt_rate, dt_sidd)
        
        common_times = np.arange(t_min, t_max, dt)
        
        print(f"[DEBUG] 共通時間軸: {len(common_times)} ポイント, dt={dt:.6f}s")
        
        # 補間
        rate_interp = np.interp(common_times, rate_times, rate_vals)
        sidd_interp = np.interp(common_times, sidd_times, sidd_vals)
        
        # サンプルレートを計算
        sample_rate = 1.0 / dt
        
        print(f"✓ データ抽出:")
        print(f"  メッセージ: {rate_msg}.{rate_field} (入力)")
        print(f"  メッセージ: {sidd_msg}.{sidd_field} (出力)")
        print(f"  データポイント数: {len(common_times)}")
        print(f"  サンプルレート: {sample_rate:.2f} Hz")
        print(f"  入力信号範囲: [{rate_interp.min():.3f}, {rate_interp.max():.3f}]")
        print(f"  出力信号範囲: [{sidd_interp.min():.3f}, {sidd_interp.max():.3f}]")
        
        return common_times, rate_interp, sidd_interp, sample_rate
        
    except Exception as e:
        print(f"[DEBUG] エラー: データ抽出失敗: {e}")
        import traceback
        traceback.print_exc()
        raise


# ============================================================
# ボード線図計算（標準方法）
# ============================================================

def compute_bode_plot(time: np.ndarray, 
                      input_signal: np.ndarray, 
                      output_signal: np.ndarray,
                      sample_rate: float,
                      freq_start: float = 0.5,
                      freq_end: float = 100.0) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """
    周波数応答（ボード線図）を計算
    
    標準方法: Welch 法でパワースペクトラム計算 -> 周波数応答算出
    
    Returns:
    --------
    (frequency_hz, magnitude_db, phase_deg, coherence) : tuple
    """
    print("[DEBUG] ボード線図計算開始")
    
    # Welch法でPSD計算
    nperseg = min(len(input_signal) // 8, 4096)
    print(f"[DEBUG] Welchパラメータ: nperseg={nperseg}, fs={sample_rate:.2f}")
    
    # 入力のパワースペクトル密度
    f_in, Pxx = welch(input_signal, fs=sample_rate, nperseg=nperseg)
    
    # 出力のパワースペクトル密度
    f_out, Pyy = welch(output_signal, fs=sample_rate, nperseg=nperseg)
    
    # クロススペクトル密度
    f_cross, Pxy = csd(input_signal, output_signal, fs=sample_rate, nperseg=nperseg)
    
    # 周波数軸を統一
    f_common = f_in
    
    print(f"[DEBUG] 周波数ポイント数: {len(f_common)}")
    print(f"[DEBUG] 周波数範囲: {f_common[0]:.2f} - {f_common[-1]:.2f} Hz")
    
    # コヒーレンス計算
    coherence = np.abs(Pxy) ** 2 / (Pxx * Pyy + 1e-10)
    
    # 転送関数（周波数応答）
    # G(jω) = Pxy(ω) / Pxx(ω)
    H_jw = Pxy / (Pxx + 1e-10)
    
    # ゲイン [dB] と位相 [deg]
    magnitude_db = 20 * np.log10(np.abs(H_jw) + 1e-10)
    phase_rad = np.angle(H_jw)
    phase_unwrapped = np.unwrap(phase_rad)
    phase_deg = np.degrees(phase_unwrapped)
    
    print(f"[DEBUG] ゲイン範囲: {magnitude_db.min():.2f} - {magnitude_db.max():.2f} dB")
    print(f"[DEBUG] 位相範囲: {phase_deg.min():.2f} - {phase_deg.max():.2f} deg")
    print(f"[DEBUG] コヒーレンス範囲: {coherence.min():.3f} - {coherence.max():.3f}")
    
    # 周波数範囲をフィルタ
    freq_mask = (f_common >= freq_start) & (f_common <= freq_end)
    
    print(f"[DEBUG] フィルタ後の周波数ポイント数: {np.sum(freq_mask)}")
    
    return f_common[freq_mask], magnitude_db[freq_mask], phase_deg[freq_mask], coherence[freq_mask]


# ============================================================
# ステップ応答推定
# ============================================================

def estimate_step_response(magnitude_db: np.ndarray,
                          phase_deg: np.ndarray,
                          frequency_hz: np.ndarray,
                          coherence: np.ndarray,
                          coherence_threshold: float = 0.7) -> Tuple[Optional[np.ndarray], Optional[np.ndarray], Optional[float], Optional[float]]:
    """
    測定した周波数応答から1次遅れモデル G(s) = K/(T*s+1) を最小二乗法でフィット
    
    方法:
    1. コヒーレンスが閾値（デフォルト0.7）以上のデータのみを使用
    2. 周波数応答を複素数形式に変換 H(jω_k)
    3. 1次遅れモデルの周波数応答 G(jω_k; K,T) = K/(1+jω_k*T) を定義
    4. 残差 e_k = H(jω_k) - G(jω_k; K,T) の実部・虚部について二乗和を最小化
    5. scipy.optimize.least_squares で非線形最小二乗問題を解く
    6. 得られたパラメータからステップ応答を計算
    
    コヒーレンスフィルタリングにより、ノイズや外乱の影響が大きい
    周波数帯域を除外し、フィッティング精度を向上させる。
    この手法は、ゲイン交差周波数の有無に関係なく、
    測定可能な周波数範囲内でモデルをフィットできる。
    
    Parameters:
    -----------
    magnitude_db : ゲイン [dB]
    phase_deg : 位相 [度]
    frequency_hz : 周波数 [Hz]
    coherence : コヒーレンス関数値
    coherence_threshold : コヒーレンス閾値（デフォルト0.7）
    
    Returns:
    --------
    (time_array, step_response_array, tau, settling_time) : tuple
    """
    print("[DEBUG] ステップ応答推定開始（最小二乗法フィッティング）")
    
    try:
        # コヒーレンスフィルタリング（0.7以上のデータのみ使用）
        valid_mask = coherence >= coherence_threshold
        n_valid = np.sum(valid_mask)
        
        if n_valid < 3:
            print(f"[WARNING] コヒーレンス >= {coherence_threshold} のデータが不足しています（{n_valid}点）")
            print("[WARNING] フィッティングをスキップします")
            return None, None, None, None
        
        magnitude_db_filtered = magnitude_db[valid_mask]
        phase_deg_filtered = phase_deg[valid_mask]
        frequency_hz_filtered = frequency_hz[valid_mask]
        
        print(f"[DEBUG] 全データポイント数: {len(magnitude_db)}")
        print(f"[DEBUG] コヒーレンス >= {coherence_threshold} のデータ: {n_valid}点 ({100*n_valid/len(magnitude_db):.1f}%)")
        
        # 【低周波フィッティング用フィルタ】5Hz以下のデータのみを使用
        low_freq_mask = frequency_hz_filtered <= 5.0
        n_low_freq_points = np.sum(low_freq_mask)
        
        if n_low_freq_points < 3:
            print(f"[WARNING] 周波数 <= 5Hz のデータが不足しています（{n_low_freq_points}点）")
            print("[WARNING] フィッティングをスキップします")
            return None, None, None, None
        
        magnitude_db_filtered = magnitude_db_filtered[low_freq_mask]
        phase_deg_filtered = phase_deg_filtered[low_freq_mask]
        frequency_hz_filtered = frequency_hz_filtered[low_freq_mask]
        
        print(f"[DEBUG] 周波数 <= 5Hz のデータ: {n_low_freq_points}点 ({100*n_low_freq_points/n_valid:.1f}%)")
        print(f"[DEBUG] 【低周波フィッティング】周波数範囲: {frequency_hz_filtered[0]:.2f} - {frequency_hz_filtered[-1]:.2f} Hz")
        
        # ボード線図を複素数に変換
        magnitude_linear = 10 ** (magnitude_db_filtered / 20)
        phase_rad = np.radians(phase_deg_filtered)
        H_jw = magnitude_linear * np.exp(1j * phase_rad)
        omega = 2 * np.pi * frequency_hz_filtered
        
        print(f"[DEBUG] ゲイン範囲（線形）: {magnitude_linear.min():.3f} - {magnitude_linear.max():.3f}")
        print(f"[DEBUG] ゲイン範囲（dB）: {magnitude_db_filtered.min():.2f} - {magnitude_db_filtered.max():.2f} dB")
        
        # 初期値推定（改良版・低周波フィッティング用）
        # 低周波（最初の5点または全体の20%）の平均をDCゲインとする
        n_low_freq_init = max(3, min(5, len(magnitude_linear) // 5))
        dc_gain_init = np.mean(magnitude_linear[:n_low_freq_init])
        
        # カットオフ周波数：ゲインが半減する点を探す
        target_mag = dc_gain_init / np.sqrt(2)
        idx_3db = np.argmin(np.abs(magnitude_linear - target_mag))
        
        # 低周波帯でゲインが減衰しているか確認
        if magnitude_linear[-1] > dc_gain_init * 0.7:
            # 低周波帯でも減衰しないパターン
            omega_c_init = 2 * np.pi * frequency_hz_filtered[len(frequency_hz_filtered)//3]
            print("[DEBUG] 【警告】低周波帯でもゲインが減衰していません（積分器的特性の可能性）")
        else:
            omega_c_init = 2 * np.pi * frequency_hz_filtered[idx_3db]
        
        tau_init = 1.0 / omega_c_init if omega_c_init > 0 else 0.1
        
        # 初期値を低周波フィッティング用の制約範囲内に収める
        # 低周波では時定数が大きくなる傾向があるため、上限を拡大
        tau_init = np.clip(tau_init, 0.001, 100.0)  # 低周波: 上限を拡大（元: 10秒）
        dc_gain_init = np.clip(dc_gain_init, 1.0, 10000.0)
        
        print(f"[DEBUG] 初期値: K={dc_gain_init:.3f}, τ={tau_init:.6f} s")
        print(f"[DEBUG] 初期カットオフ周波数: {1/(2*np.pi*tau_init):.2f} Hz")
        
        # 1次遅れモデルの周波数応答
        def first_order_model(omega_vals, K, T):
            """G(jω; K,T) = K / (1 + jωT)"""
            return K / (1 + 1j * omega_vals * T)
        
        # 重み付け：低周波を重視（高周波はノイズの影響を受けやすい）
        # 周波数に反比例する重み
        weights = 1.0 / (1.0 + frequency_hz_filtered / frequency_hz_filtered[0])
        weights = weights / np.max(weights)  # 正規化
        
        # 残差関数（実部と虚部を分離、重み付け、スケーリング）
        def residuals(params):
            K, T = params
            if K <= 0 or T <= 0:
                return np.ones(2 * len(omega)) * 1e10  # ペナルティ
            
            G_model = first_order_model(omega, K, T)
            error_complex = H_jw - G_model
            
            # スケーリング：測定値の大きさで正規化
            scale = np.abs(H_jw) + 1e-10
            error_normalized = error_complex / scale
            
            # 重み付けを適用
            error_weighted = error_normalized * np.sqrt(weights)
            
            # 実部と虚部を連結して返す
            return np.concatenate([error_weighted.real, error_weighted.imag])
        
        # 最小二乗法で最適化
        print("[DEBUG] 非線形最小二乗法でフィッティング中（低周波: ≤5Hz）...")
        # より現実的な制約：
        # K: 1～10,000（線形ゲイン）
        # τ: 0.001～100秒（低周波フィッティングでは時定数が大きくなる傾向）
        result = least_squares(
            residuals,
            x0=[dc_gain_init, tau_init],
            bounds=([1.0, 0.001], [10000.0, 100.0]),  # K, τ の範囲制約
            method='trf',
            verbose=0,
            ftol=1e-8,
            xtol=1e-8,
            max_nfev=1000
        )
        
        if not result.success:
            print(f"[WARNING] 最適化が収束しませんでした: {result.message}")
        
        K, tau = result.x
        print(f"[DEBUG] フィッティング結果: K={K:.3f}, τ={tau:.6f} s")
        print(f"[DEBUG] カットオフ周波数: {1/(2*np.pi*tau):.2f} Hz")
        print(f"[DEBUG] 残差ノルム: {np.linalg.norm(result.fun):.6f}")
        print(f"[DEBUG] 最適化ステータス: {result.message}")
        
        # フィッティング品質の確認
        G_fitted = first_order_model(omega, K, tau)
        mag_fitted = np.abs(G_fitted)
        relative_error = np.mean(np.abs(magnitude_linear - mag_fitted) / magnitude_linear)
        print(f"[DEBUG] 平均相対誤差: {relative_error*100:.1f}%")
        
        # 制約に張り付いていないか確認
        if K >= 9999.0:
            print("[WARNING] DCゲインが上限に達しています（モデルが適合していない可能性）")
        if tau >= 9.9:
            print("[WARNING] 時定数が上限に達しています（モデルが適合していない可能性）")
        
        # フィットした1次遅れモデルの転送関数を構築
        num = [K]
        den = [tau, 1]
        sys = ctl.TransferFunction(num, den)
        
        print(f"[DEBUG] フィット後システム: G(s) = {K:.3f} / ({tau:.6f}*s + 1)")
        
        # ステップ応答計算
        t = np.linspace(0, 5*tau, 1000)
        t_step, y_step = ctl.step_response(sys, T=t)
        
        # --- 正規化 ---
        y_step = y_step / K
        print(f"[DEBUG] ステップ応答をDCゲイン({K:.3f})で正規化")
        
        # --- 整定時間（±2%基準）計算 ---
        final_value = y_step[-1]
        threshold = 0.02 * abs(final_value)
        settling_time = None
        for i in range(len(y_step)-1, -1, -1):
            if abs(y_step[i] - final_value) > threshold:
                if i+1 < len(t_step):
                    settling_time = t_step[i+1]
                else:
                    settling_time = t_step[-1]
                break
        if settling_time is None:
            settling_time = t_step[-1]
        print(f"  整定時間 (±2%): {settling_time:.4f} s")
        
        print(f"✓ ステップ応答計算完了（最小二乗法フィッティング）")
        print(f"  DCゲイン K: {K:.3f}")
        print(f"  時定数 τ: {tau:.6f} s")
        print(f"  最終値: {y_step[-1]:.3f}")
        print(f"  整定時間 (±2%): {settling_time:.4f} s")
        
        return t_step, y_step, tau, settling_time
    except Exception as e:
        print(f"[DEBUG] 警告: ステップ応答推定失敗（最小二乗法フィッティング）: {e}")
        import traceback
        traceback.print_exc()
        return None, None, None, None


# ============================================================
# PM/GM 計算
# ============================================================

def compute_margins(magnitude_db: np.ndarray,
                   phase_deg: np.ndarray,
                   frequency_hz: np.ndarray) -> Tuple[float, float, float, float]:
    """
    位相余裕 (PM) とゲイン余裕 (GM) を計算
    
    Returns:
    --------
    (pm_deg, gm_db, omega_gc, omega_pc) : tuple
        PM: 位相余裕 [deg]
        GM: ゲイン余裕 [dB]
        omega_gc: ゲイン交差周波数 [Hz]
        omega_pc: 位相交差周波数 [Hz]
    """
    print("[DEBUG] PM/GM計算開始")
    
    # ゲイン交差周波数（0dB地点）
    omega_gc = None
    phase_at_gc = None
    pm = None
    # 0dBを通過しているか判定
    sign_change = np.any((magnitude_db[:-1] * magnitude_db[1:]) < 0)
    if sign_change:
        # 0dBを通過している場合、線形補間で交点を求める
        for i in range(len(magnitude_db)-1):
            if magnitude_db[i] * magnitude_db[i+1] < 0:
                # 線形補間
                frac = -magnitude_db[i] / (magnitude_db[i+1] - magnitude_db[i])
                omega_gc = frequency_hz[i] + frac * (frequency_hz[i+1] - frequency_hz[i])
                phase_at_gc = phase_deg[i] + frac * (phase_deg[i+1] - phase_deg[i])
                pm = phase_at_gc - (-180)
                break
    # 通過していなければNoneのまま
    
    # 位相交差周波数（-180°地点）
    idx_180 = np.argmin(np.abs(phase_deg - (-180)))
    omega_pc = frequency_hz[idx_180]
    mag_at_pc = magnitude_db[idx_180]
    gm = 0 - mag_at_pc

    if omega_gc is not None:
        print(f"[DEBUG] ゲイン交差周波数: {omega_gc:.2f} Hz, 位相: {phase_at_gc:.2f} deg")
    else:
        print(f"[DEBUG] ゲイン交差周波数: なし（0dB未到達）")
    print(f"[DEBUG] 位相交差周波数: {omega_pc:.2f} Hz, ゲイン: {mag_at_pc:.2f} dB")

    return pm, gm, omega_gc, omega_pc


# ============================================================
# グラフ出力
# ============================================================

def plot_bode_diagram(frequency: np.ndarray,
                     magnitude_db: np.ndarray,
                     phase_deg: np.ndarray,
                     coherence: np.ndarray,
                     output_file: Optional[Path] = None):
    """ボード線図を表示・保存"""
    print("[DEBUG] ボード線図プロット開始")
    
    fig, axes = plt.subplots(3, 1, figsize=(12, 10))
    fig.suptitle('Bode Diagram with Coherence', fontsize=14, fontweight='bold')
    
    # ゲイン線図
    axes[0].semilogx(frequency, magnitude_db, 'b-', linewidth=2)
    axes[0].axhline(y=0, color='r', linestyle='--', alpha=0.5, label='0 dB')
    axes[0].grid(True, which='both', alpha=0.3)
    axes[0].set_ylabel('Magnitude [dB]', fontsize=11)
    axes[0].set_title('Magnitude Response', fontsize=12)
    axes[0].legend()
    
    # 位相線図
    axes[1].semilogx(frequency, phase_deg, 'g-', linewidth=2)
    axes[1].axhline(y=-180, color='r', linestyle='--', alpha=0.5, label='-180°')
    axes[1].grid(True, which='both', alpha=0.3)
    axes[1].set_ylabel('Phase [deg]', fontsize=11)
    axes[1].set_title('Phase Response', fontsize=12)
    axes[1].legend()
    
    # コヒーレンス
    axes[2].semilogx(frequency, coherence, 'r-', linewidth=2)
    axes[2].axhline(y=0.9, color='g', linestyle='--', alpha=0.5, label='High coherence (>0.9)')
    axes[2].grid(True, which='both', alpha=0.3)
    axes[2].set_xlabel('Frequency [Hz]', fontsize=11)
    axes[2].set_ylabel('Coherence', fontsize=11)
    axes[2].set_ylim([0, 1.05])
    axes[2].set_title('Coherence', fontsize=12)
    axes[2].legend()
    
    plt.tight_layout()
    
    if output_file:
        plt.savefig(output_file, dpi=Config.DPI, bbox_inches='tight')
        print(f"✓ 保存: {output_file}")
    
    return fig, axes


def plot_step_response(time_array: np.ndarray,
                      step_array: np.ndarray,
                      output_file: Optional[Path] = None):
    """ステップ応答を表示・保存"""
    print("[DEBUG] ステップ応答プロット開始")
    
    fig, ax = plt.subplots(figsize=(12, 6))
    
    ax.plot(time_array, step_array, 'b-', linewidth=2, label='Step Response')
    ax.grid(True, alpha=0.3)
    ax.set_xlabel('Time [s]', fontsize=11)
    ax.set_ylabel('Output', fontsize=11)
    ax.set_title('Estimated Step Response (Unit Step Input)', fontsize=12, fontweight='bold')
    ax.legend()
    
    plt.tight_layout()
    
    if output_file:
        plt.savefig(output_file, dpi=Config.DPI, bbox_inches='tight')
        print(f"✓ 保存: {output_file}")
    
    return fig, ax


# ============================================================
# CSV エクスポート
# ============================================================

def export_to_csv(frequency: np.ndarray,
                 magnitude_db: np.ndarray,
                 phase_deg: np.ndarray,
                 coherence: np.ndarray,
                 output_file: Path):
    """ボード線図データを CSV に保存"""
    print("[DEBUG] CSV出力開始")
    
    import csv
    
    with open(output_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['Frequency_Hz', 'Magnitude_dB', 'Phase_deg', 'Coherence'])
        
        for freq, mag, phase, coh in zip(frequency, magnitude_db, phase_deg, coherence):
            writer.writerow([f'{freq:.4f}', f'{mag:.4f}', f'{phase:.2f}', f'{coh:.4f}'])
    
    print(f"✓ 保存: {output_file}")


# ============================================================
# メイン処理
# ============================================================

def main():
    """メイン処理"""
    
    print("=" * 70)
    print("ArduPilot System Identification 解析ツール")
    print("=" * 70)
    
    # ================================================
    # ステップ 1: ログファイルを開く
    # ================================================
    
    print(f"\n[ステップ 1] ログファイルを開く...")
    
    if not os.path.exists(Config.BIN_FILE_PATH):
        print(f"[DEBUG] エラー: ログファイルが見つかりません")
        print(f"[DEBUG] パス: {Config.BIN_FILE_PATH}")
        print(f"[DEBUG] カレントディレクトリ: {os.getcwd()}")
        sys.exit(1)
    
    print(f"読み込み中: {Config.BIN_FILE_PATH}")
    
    try:
        messages = read_mavlink_log(Config.BIN_FILE_PATH)
    except Exception as e:
        print(f"[DEBUG] エラー: ログファイルの読み込み失敗: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    
    # ================================================
    # ステップ 2: SYSID 時間範囲を自動検出
    # ================================================

    print(f"\n[ステップ 2] SYSID_MODE 時間範囲検出...")

    # --- 追加: PARM/PARAMから実験ゲインを抽出 ---
    gain_param_lines = []
    def collect_gain_params(messages):
        gain_keys = [
            'SYSID_GAIN', 'SYSID_RLL_GAIN', 'SYSID_PIT_GAIN', 'SYSID_YAW_GAIN',
            'ATC_RAT_RLL_P', 'ATC_RAT_PIT_P', 'ATC_RAT_YAW_P',
            'ATC_RAT_RLL_I', 'ATC_RAT_PIT_I', 'ATC_RAT_YAW_I',
            'ATC_RAT_RLL_D', 'ATC_RAT_PIT_D', 'ATC_RAT_YAW_D',
        ]
        found = False
        for parm_type in ['PARM', 'PARAM']:
            if parm_type in messages:
                parm_data = messages[parm_type]['data']
                name_arr = parm_data.get('Name', parm_data.get('name', None))
                value_arr = parm_data.get('Value', parm_data.get('value', None))
                if name_arr is not None and value_arr is not None:
                    for key in gain_keys:
                        idxs = np.where(name_arr == key)[0]
                        if len(idxs) > 0:
                            line = f"[設定パラメータ] {key}: {value_arr[idxs[-1]]}"
                            print(line)
                            gain_param_lines.append(line)
                            found = True
        if not found:
            msg = "[設定パラメータ] SYSID/制御ゲイン情報は見つかりませんでした"
            print(msg)
            gain_param_lines.append(msg)

    collect_gain_params(messages)

    if Config.TIME_START is None or Config.TIME_END is None:
        t_start, t_end = get_sysid_time_range(messages)
        if t_start is not None:
            Config.TIME_START = t_start
            Config.TIME_END = t_end
        else:
            print("[DEBUG] 警告: 時間範囲を自動検出できません")
            print("[DEBUG] デフォルト範囲を使用します")
            # デフォルトとして最初のデータから10秒間を使用
            if 'SIDD' in messages and len(messages['SIDD']['timestamp']) > 0:
                t_start = messages['SIDD']['timestamp'][0] / 1e6
                t_end = min(t_start + 10, messages['SIDD']['timestamp'][-1] / 1e6)
                Config.TIME_START = t_start
                Config.TIME_END = t_end
                print(f"[DEBUG] デフォルト範囲: {t_start:.2f} - {t_end:.2f} s")
            else:
                print("[DEBUG] エラー: データが見つかりません")
                sys.exit(1)
    
    # ================================================
    # ステップ 3: データを抽出
    # ================================================
    
    print(f"\n[ステップ 3] データ抽出 ({Config.ANALYSIS_TYPE} 軸)...")
    
    try:
        time, u_signal, y_signal, fs = extract_data(
            messages,
            Config.TIME_START,
            Config.TIME_END,
            Config.ANALYSIS_TYPE
        )
    except Exception as e:
        print(f"[DEBUG] エラー: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    
    # ================================================
    # ステップ 4: ボード線図を計算
    # ================================================
    
    print(f"\n[ステップ 4] ボード線図計算...")
    
    freq, mag_db, phase_deg, coherence = compute_bode_plot(
        time, u_signal, y_signal, fs,
        Config.FREQ_START, Config.FREQ_END
    )
    
    print(f"✓ 周波数範囲: {freq[0]:.2f} - {freq[-1]:.2f} Hz")
    print(f"✓ ゲイン範囲: {mag_db.min():.1f} - {mag_db.max():.1f} dB")
    
    # ================================================
    # ステップ 5: PM/GM 計算
    # ================================================
    
    print(f"\n[ステップ 5] PM/GM 計算...")
    
    pm, gm, omega_gc, omega_pc = compute_margins(mag_db, phase_deg, freq)
    
    if pm is not None:
        print(f"✓ 位相余裕 (PM): {pm:.1f}°")
    else:
        print(f"✓ 位相余裕 (PM): なし")
    print(f"✓ ゲイン余裕 (GM): {gm:.1f} dB")
    if omega_gc is not None:
        print(f"✓ ゲイン交差周波数: {omega_gc:.2f} Hz")
    else:
        print(f"✓ ゲイン交差周波数: なし（0dB未到達）")
    print(f"✓ 位相交差周波数: {omega_pc:.2f} Hz")
    
    # 安定性判定
    print(f"\n評価:")
    if pm is None:
        print("  判定不能（ゲイン交差周波数なし/PM未定義）")
    else:
        if pm > 45 and gm > 8:
            print(f"  ✓✓✓ 非常に良好（PM>45°, GM>8dB）")
        elif pm > 30 and gm > 6:
            print(f"  ✓ 良好（PM>30°, GM>6dB）")
        elif pm > 0 and gm > 0:
            print(f"  ⚠ 限界安定（PM>0°, GM>0dB）")
        else:
            print(f"  ✗ 危険（不安定）")
    
    # ================================================
    # ステップ 6: ステップ応答推定
    # ================================================
    
    print(f"\n[ステップ 6] ステップ応答推定...")
    
    t_step, y_step, tau, settling_time = estimate_step_response(mag_db, phase_deg, freq, coherence)

    if y_step is not None and tau is not None and settling_time is not None:
        print(f"✓ ステップ応答計算完了")
        print(f"  最終値: {y_step[-1]:.3f}")
        print(f"  時定数 τ: {tau:.6f} s")
        print(f"  整定時間 (±2%): {settling_time:.4f} s")
    
    # ================================================
    # ステップ 7: 出力ディレクトリ作成
    # ================================================
    
    print(f"\n[ステップ 7] 出力ディレクトリ作成...")
    
    if Config.OUTPUT_DIR is None:
        log_name = Path(Config.BIN_FILE_PATH).stem
        Config.OUTPUT_DIR = Path.cwd() / f"results_{log_name}_{Config.ANALYSIS_TYPE}"
    else:
        Config.OUTPUT_DIR = Path(Config.OUTPUT_DIR)
    
    Config.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    print(f"出力フォルダ: {Config.OUTPUT_DIR}")
    
    # ================================================
    # ステップ 8: グラフ出力
    # ================================================
    
    print(f"\n[ステップ 8] グラフ出力...")
    
    # ボード線図
    bode_file = Config.OUTPUT_DIR / f"01_bode_diagram.{Config.SAVE_FORMAT}"
    plot_bode_diagram(freq, mag_db, phase_deg, coherence, bode_file)
    
    # ステップ応答
    if y_step is not None:
        step_file = Config.OUTPUT_DIR / f"02_step_response.{Config.SAVE_FORMAT}"
        plot_step_response(t_step, y_step, step_file)
    
    # ================================================
    # ステップ 9: CSV エクスポート
    # ================================================
    
    if Config.EXPORT_CSV:
        print(f"\n[ステップ 9] CSV エクスポート...")
        csv_file = Config.OUTPUT_DIR / "bode_data.csv"
        export_to_csv(freq, mag_db, phase_deg, coherence, csv_file)
    
    # ================================================
    # ステップ 10: サマリーファイル出力
    # ================================================
    
    print(f"\n[ステップ 10] サマリーファイル出力...")
    
    summary_file = Config.OUTPUT_DIR / "SUMMARY.txt"
    with open(summary_file, 'w', encoding='utf-8') as f:
        f.write("=" * 70 + "\n")
        f.write("ArduPilot System Identification 解析結果\n")
        f.write("=" * 70 + "\n\n")

        f.write(f"ログファイル: {Config.BIN_FILE_PATH}\n")
        f.write(f"解析軸: {Config.ANALYSIS_TYPE.upper()}\n")
        f.write(f"解析時間: {Config.TIME_START:.2f} - {Config.TIME_END:.2f} s\n")
        f.write(f"サンプルレート: {fs:.2f} Hz\n")
        f.write(f"データポイント数: {len(time)}\n\n")

        # 追加: ゲインパラメータ情報
        f.write("【 設定パラメータ（ゲイン） 】\n")
        for line in gain_param_lines:
            f.write(line + "\n")
        f.write("\n")

        f.write("【 周波数応答特性 】\n")
        if omega_gc is not None:
            f.write(f"ゲイン交差周波数: {omega_gc:.2f} Hz\n")
        else:
            f.write(f"ゲイン交差周波数: なし（0dB未到達）\n")
        f.write(f"位相交差周波数: {omega_pc:.2f} Hz\n")
        if pm is not None:
            f.write(f"位相余裕 (PM): {pm:.1f}°\n")
        else:
            f.write(f"位相余裕 (PM): なし\n")
        f.write(f"ゲイン余裕 (GM): {gm:.1f} dB\n\n")

        f.write("【 安定性評価 】\n")
        if pm is None:
            f.write("判定不能（ゲイン交差周波数なし/PM未定義）\n")
        else:
            if pm > 45 and gm > 8:
                f.write("✓✓✓ 非常に良好（PM>45°, GM>8dB）\n")
            elif pm > 30 and gm > 6:
                f.write("✓ 良好（PM>30°, GM>6dB）\n")
            elif pm > 0 and gm > 0:
                f.write("⚠ 限界安定（PM>0°, GM>0dB）\n")
            else:
                f.write("✗ 危険（不安定）\n")

        f.write("\n【 出力ファイル 】\n")
        f.write(f"- 01_bode_diagram.{Config.SAVE_FORMAT}\n")
        if y_step is not None and tau is not None and settling_time is not None:
            f.write(f"- 02_step_response.{Config.SAVE_FORMAT}\n")
            # ステップ応答特性を出力
            f.write("\n【 ステップ応答特性 】\n")
            f.write(f"時定数 τ: {tau:.6f} s\n")
            f.write(f"整定時間 (±2%): {settling_time:.4f} s\n")
        if Config.EXPORT_CSV:
            f.write("- bode_data.csv\n")
        f.write(f"- SUMMARY.txt\n")
    
    print(f"✓ 保存: {summary_file}")
    
    # ================================================
    # 完了
    # ================================================
    
    print("\n" + "=" * 70)
    print("✓ 解析完了！")
    print("=" * 70)
    print(f"\n結果フォルダ: {Config.OUTPUT_DIR}")
    print("\nグラフを確認してください:")
    print(f"  - {Config.OUTPUT_DIR}/01_bode_diagram.{Config.SAVE_FORMAT}")
    if y_step is not None:
        print(f"  - {Config.OUTPUT_DIR}/02_step_response.{Config.SAVE_FORMAT}")
    print(f"  - {Config.OUTPUT_DIR}/SUMMARY.txt")


if __name__ == "__main__":
    main()

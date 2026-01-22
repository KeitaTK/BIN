import sys
from pymavlink import mavutil

if len(sys.argv) < 2:
    print("Usage: python extract_sidd_sids_info.py <BIN file>")
    sys.exit(1)

bin_path = sys.argv[1]
mlog = mavutil.mavlink_connection(bin_path)

sidd_count = 0
sids_count = 0
sidd_first = None
sidd_last = None
sids_first = None
sids_last = None

while True:
    msg = mlog.recv_match(blocking=False)
    if msg is None:
        break
    t = getattr(msg, 'TimeUS', None)
    if msg.get_type() == 'SIDD':
        sidd_count += 1
        if sidd_first is None:
            sidd_first = t
        sidd_last = t
    if msg.get_type() == 'SIDS':
        sids_count += 1
        if sids_first is None:
            sids_first = t
        sids_last = t

print(f"SIDD: {sidd_count}件")
if sidd_count > 0:
    print(f"  最初: {sidd_first} us, 最後: {sidd_last} us, 期間: {(sidd_last-sidd_first)/1e6:.2f} s")
else:
    print("  データなし")

print(f"SIDS: {sids_count}件")
if sids_count > 0:
    print(f"  最初: {sids_first} us, 最後: {sids_last} us, 期間: {(sids_last-sids_first)/1e6:.2f} s")
else:
    print("  データなし")

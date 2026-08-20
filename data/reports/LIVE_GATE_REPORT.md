# LIVE_GATE_REPORT

Generated: 2026-08-16 19:02 UTC
status: **LIVE_BLOCKED**
PAPER: `/workspace/configs/generated/PAPER_ONLY.yaml`
blocked file: `/workspace/configs/generated/LIVE_BLOCKED.yaml`
do not live without G5 G6

| gate | result | detail |
|---|---|---|
| G1 bosona cover ≥80% | **PASS** | {'cover': 0.8018867924528302, 'min': 0.8} |
| G2 mo cover ≥80% | **PASS** | {'cover': 0.8468468468468469, 'min': 0.8} |
| G3 pair_gt1_trade false | **PASS** | {'pair_gt_1_trade': False} |
| G4 shadow path | **PASS** | {'shadow_only': True} |
| G5 size_ok | **FAIL** | {'flag': '/workspace/data/ops/G5_size_ok.flag', 'note': 'FAIL until human size_ok flag'} |
| G6 fill calibration | **PASS** | {'flag': '/workspace/data/ops/G6_fill_calibrated.flag', 'note': 'FAIL until paper fill% logged vs sim + human flag'} |
| G7 --i-accept-risk | **FAIL** | {'note': 'FAIL until --i-accept-risk'} |

No hand-edited LIVE_READY. No clip 67 day-one. No pair>1.
MICRO_LIVE_TRIAL.yaml is not LIVE_READY. Full LIVE_READY stays BLOCKED without G5+G6+G7.

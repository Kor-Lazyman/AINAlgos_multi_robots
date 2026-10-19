# WAAM Validator Report

## Overall Result

**PASS**

- WAAM Validator version: 1.0.1

## Input Summary

- Directory: `C:\Users\lazzyman\Desktop\AINalgos2\version 1.1.1.e\output\train_e_40updates_20261019\final_stl\02\input`
- Trajectory rows: 14255
- Target watertight: True

## Schedule

- Makespan: 5992.68 s
- R1: completion 5992.68 s; Deposition 562.89 s; Travel 297.85 s; Wait 5131.94 s
- R2: completion 5992.68 s; Deposition 3436.36 s; Travel 1817.55 s; Wait 738.77 s
- R3: completion 5992.68 s; Deposition 0.03 s; Travel 17.45 s; Wait 5975.20 s

## Robot XY Reach

- Passed: True
- R1: max XY distance 1469.62 / 1500.00 mm; XY margin 30.38 mm; violating points 0
- R2: max XY distance 1500.00 / 1500.00 mm; XY margin 0.00 mm; violating points 0
- R3: max XY distance 1245.73 / 1500.00 mm; XY margin 254.27 mm; violating points 0

## Collision

- Arm Envelope events: 0
- Minimum Arm Envelope safety margin: 0.39 mm
- Arm centerline distance at worst case:
  250.39 mm
- Arm required centerline distance at worst case:
  250.00 mm
- TCP_RADIUS events: 0
- Minimum TCP distance: 250.39 mm

## Shape

- Target layer-integrated volume: 254007.579 mm³
- Deposited volume: 259104.458 mm³
- Intersection volume: 254007.579 mm³
- Underfill volume: 0.000 mm³
- Overfill volume: 5096.879 mm³
- Coverage: 100.00%
- Underfill: 0.00%
- Overfill: 2.01%
- IoU: 98.03%
- Failed layers: 0 / 8

## Failure Reasons

None

## Warnings

None

## Validation Violations

These findings contribute to a normal `FAIL`; they do not mean that the pipeline ended with
the fatal status `ERROR`.

None

## Output Files

- `summary.json`
- `validation_report.md`
- `robot_metrics.csv`
- `collision_events.csv`
- `layer_metrics.csv`
- `run.log`
- `validation_inputs.json`

## Interpretation Limitations

본 검증기는 각 로봇을 폭이 고정된 Base–TCP 2D Capsule로 단순화하고, XY 평면상 Capsule 안전 여유와 TCP 허용 원 침범만을 로봇 간 충돌로 판단한다. 검사는 adaptive sample 기반이며 연속시간 swept collision을 보증하지 않는다. 실제 로봇 링크, 관절 자세, Z 방향 분리, 지그 및 환경 충돌은 반영하지 않는다. 형상 검증은 일정한 비드 폭과 layer 높이를 가정한 명목 기하 모델이며 열변형, 비드 형상 변화, 용융풀 거동 및 공정 불안정성을 예측하지 않는다.

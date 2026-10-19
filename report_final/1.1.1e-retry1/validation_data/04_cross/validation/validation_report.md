# WAAM Validator Report

## Overall Result

**PASS**

- WAAM Validator version: 1.0.1

## Input Summary

- Directory: `C:\Users\lazzyman\Desktop\AINalgos2\version 1.1.1.e\output\train_e_retry1_40updates_20261019\validation_update_0040\04_cross\input`
- Trajectory rows: 219
- Target watertight: True

## Schedule

- Makespan: 269.29 s
- R1: completion 269.29 s; Deposition 0.00 s; Travel 0.00 s; Wait 269.29 s
- R2: completion 269.29 s; Deposition 219.47 s; Travel 49.83 s; Wait 0.00 s
- R3: completion 269.29 s; Deposition 0.00 s; Travel 0.00 s; Wait 269.29 s

## Robot XY Reach

- Passed: True
- R1: max XY distance 0.00 / 2500.00 mm; XY margin 2500.00 mm; violating points 0
- R2: max XY distance 1229.41 / 2500.00 mm; XY margin 1270.59 mm; violating points 0
- R3: max XY distance 0.00 / 2500.00 mm; XY margin 2500.00 mm; violating points 0

## Collision

- Arm Envelope events: 0
- Minimum Arm Envelope safety margin: 874.57 mm
- Arm centerline distance at worst case:
  1124.57 mm
- Arm required centerline distance at worst case:
  250.00 mm
- TCP_RADIUS events: 0
- Minimum TCP distance: 1124.57 mm

## Shape

- Target layer-integrated volume: 11264.000 mm³
- Deposited volume: 11283.261 mm³
- Intersection volume: 11252.218 mm³
- Underfill volume: 11.782 mm³
- Overfill volume: 31.043 mm³
- Coverage: 99.90%
- Underfill: 0.10%
- Overfill: 0.28%
- IoU: 99.62%
- Failed layers: 0 / 1

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

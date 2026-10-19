# WAAM 1.1.1.e retry1 — 자기 작업 재검토 후 인계

현재 코드는 `1.1.1.e-retry1`입니다. 40-update 학습을 끝낸 변경 전 e 모델과 코드, minor2 비교 결과는 **`report_final`**에 보존했습니다. 통합 Word 보고서는 `report_final/combined_report.docx`, 결과 브라우저는 `report_final/index.html`입니다. 보고서의 e 수치는 재검토 방식 적용 전 결과이며, retry1의 장시간 재학습은 아직 실행하지 않았습니다.

retry1은 액션, STL 배치, reward를 유지하고 스케줄러만 바꿉니다. 충돌 예상 작업은 원래 소유자의 보류 목록에 남긴 채 안전한 자기 작업을 먼저 수행합니다. 진행으로 시간·위치가 바뀌면 보류 작업을 다시 검사하며, 한 순회에서 더 이상 수행할 수 있는 작업이 없을 때만 남은 작업을 상위 로봇에 인계합니다. 진행할 때마다 미완료 작업 수가 줄어 무한 반복하지 않습니다.

기존 d 버전과 모델을 보존하고 별도로 만든 버전입니다. 기존 체크포인트를 불러오지 않고 새 PPO 정책으로 시작합니다. 기존 waam Python 환경과 이 폴더에 복사한 validator 소스를 사용합니다.

## 실행

PowerShell에서 이 폴더로 이동한 뒤 실행합니다.

```powershell
& 'C:\Users\lazzyman\anaconda3\envs\waam\python.exe' -u train.py --updates 40 --n-steps 64 --batch-size 32 --epochs 10 --eval-every 4 --save-every 4 --device cuda --train-dir train --validation-dir validation --official-validator --output output\train_e_retry1_40updates
```

현재 Windows에서는 PowerShell 스크립트 실행 정책 때문에 `run-training.ps1`이 차단되므로 위 Python 직접 실행 명령을 사용합니다. 실행 정책 변경은 필요 없습니다. 이전 e 학습은 완료되었으며 로그는 `output/logs/train_e_40updates_20261019.log`에 보존되어 있습니다.

기본 설정: **40 updates × 64 환경 step = 2,560 레이어**, batch 32, epoch 10, gamma 1, learning rate 0.0003, seed 42. 정책/가치 MLP는 각각 128–128이며 CUDA를 사용합니다. geometry와 충돌 검사는 CPU입니다. early stopping은 없습니다. 기존 학습 STL 6개와 validation 8개를 사용하며, validation은 초기 및 4 updates마다 평가합니다.

다시 실행할 때는 기존 결과를 덮어쓰지 않도록 출력 폴더를 바꿉니다.

```powershell
& 'C:\Users\lazzyman\anaconda3\envs\waam\python.exe' -u train.py --updates 40 --n-steps 64 --batch-size 32 --eval-every 4 --save-every 4 --device cuda --output output\another_run
```

하나의 입력을 평가하려면:

```powershell
& 'C:\Users\lazzyman\anaconda3\envs\waam\python.exe' test-version.py --input train\01 --checkpoint output\train_e_40updates_20261019\final_model.zip --official-validator --output output\test_01
```

## 알고리즘

1. 슬라이싱 전 STL 내부를 일정한 3D 격자로 표본화합니다. 점마다 가중치 1을 부여합니다. XY 사영 시 Z 방향으로 겹친 점의 개수를 그대로 보존합니다. 도달 판정이 XY 기준이므로 배치 목적함수는 이 사영을 사용합니다.
2. XY 평행 이동 후보마다 가장 가까운 도달 가능 로봇에 점을 배정하고, 로봇별 점 비율의 표준편차를 최소화합니다. 동률이면 이동 거리 등을 비교합니다. 작업 공간과 도달 영역을 벗어나는 후보는 제외합니다. 격자 탐색이므로 전역 최적을 보장하지는 않습니다. **STL 전체를 한 번 이동하여 모든 레이어의 이동량이 같습니다.**
3. 레이어 선분을 도달 원 및 로봇 간 등거리 경계에서 나눕니다. 최초 소유자는 가장 가까운 도달 가능 로봇입니다. 이 버전에서는 교집합을 처음부터 R1이 독점하지 않습니다.
4. PPO가 출발 XY 좌표, 진행 방향, hatch 각도 및 레이어 우선순위를 선택합니다. 출발 좌표는 자기 소유 적층 선분에 투영하여 공중에서 적층하지 않도록 합니다.
5. 우선순위 순으로 주 작업 경로를 예약합니다. 다음 작업의 접근·적층·안전한 홈 복귀 경로를 검사합니다. 안전하면 실행하고, 충돌 예상이면 해당 작업을 건너뛰어 다른 작업을 계속 검토합니다. **건너뛴 작업은 삭제하지 않습니다.**
6. 보류 작업을 원래 로봇의 현재 시간·위치에서 다시 검사합니다. 안전해진 작업은 원래 로봇이 수행하며 진행이 있는 동안 재검토합니다. 더 이상 진행할 수 없을 때 남은 작업만 도달 가능한 최상위 로봇으로 넘깁니다. 상위 로봇 모두 도달 불가능하면 원래 로봇의 보충 큐에 남깁니다. 작업 수와 적층 길이 보존을 검증합니다.
7. 각 로봇의 보충 큐는 자신의 주 작업 이후 가능한 가장 이른 안전 시각에 실행합니다. 다른 로봇의 예약된 작업은 계속됩니다. 보충 큐가 충돌하면 홈에서 시작을 늦춥니다. 필요한 경우 보충 작업의 일부 실행은 순차적일 수 있습니다. 이것을 주 작업 전체의 직렬화로 바꾸지는 않습니다.
8. 전체 궤적에 연속 TCP/arm XY 충돌 검사와 trajectory 제약 검사를 다시 수행합니다. 불가능한 경로는 성공으로 처리하지 않고 오류로 남깁니다.

사용자가 선택한 **실제 충돌 거리 + 작은 수치 여유**를 사용합니다. 여유는 `max(0.001 mm, 4 × geometry_epsilon_mm)`입니다. d의 2배 근접 기준은 e에 적용하지 않습니다. 작은 형상이나 큰 arm envelope에서는 동시에 적층할 수 있는 공간 자체가 제한될 수 있습니다.

## Action과 reward

`MultiDiscrete([8,33,33,2,33,33,2,33,33,2,6])`입니다.

| 인덱스 | 의미 |
|---|---|
| 0 | Hatch 각도: 22.5° 간격 8개 |
| 1, 2 | R1 출발 X, Y: 각각 0~32 |
| 3 | R1 CCW/CW |
| 4, 5 | R2 출발 X, Y |
| 6 | R2 CCW/CW |
| 7, 8 | R3 출발 X, Y |
| 9 | R3 CCW/CW |
| 10 | 로봇 우선순위 6가지 순열 |

출발 위치는 `layer_min_xy + action_xy / 32 × layer_span_xy`로 계산한 뒤 가장 가까운 자기 적층 선분 위 점으로 보정합니다. 선택한 선분을 그 점에서 나누어 전체 길이를 유지합니다. 해당 작업이 충돌 때문에 넘어가면 실제 첫 적층 위치는 달라질 수 있으며, 요청·보정 좌표와 실제 첫 적층 좌표를 모두 기록합니다.

보상은 **`r_layer = -layer_duration_seconds`**뿐입니다. gamma=1이므로 전체 STL의 episode return은 음의 makespan입니다. IoU, validator PASS, 활용률, handoff 횟수에는 별도 가중치나 보너스를 주지 않습니다. Validator는 평가 진단으로만 사용합니다.

## 결과 CSV와 재사용

학습 종료 후 최종 모델로 다음을 자동 저장합니다.

- `final_validation.csv`: validation 8개 결과.
- `final_stl.csv`: 학습 STL 6개 결과. 각 입력이 끝나는 대로 누적 저장.
- `final_results.csv`: 두 데이터셋 통합 결과.
- `final_model.zip`, `latest_model.zip`, `best_model.zip`: 최종·최근·검증 makespan 최적 모델. best가 최종 모델과 같다는 보장은 없습니다.

CSV에는 makespan, 계산 시간, validator 상태, IoU, 충돌 수, 로봇별 활용률, 정책/체크포인트·입력·코드 해시, 실제 산출물 위치와 cache hit 여부가 들어갑니다. 실패/미완료 makespan을 0으로 기록하지 않습니다. UTF-8 BOM 인코딩으로 Excel에서 열 수 있습니다.

동일 정책 가중치·STL·config·평가 코드·평가 옵션의 결과가 있고 기존 trajectory가 남아 있으면 `output/evaluation_cache`를 통해 재사용합니다. 특히 update 40 validation을 최종 validation으로 다시 계산하지 않습니다. **서로 다른 모델이나 입력 결과를 같은 것으로 재사용하지 않습니다.** 재사용 항목의 CSV `artifact_dir`는 실제 원본 산출물 폴더를 가리킵니다.

각 평가 폴더에는 `results.csv`, `summary.json`이 저장됩니다. 새로 계산한 입력에는 trajectory, 전체 간트 PNG, 공식 validator 출력, layer trace도 저장합니다. `training.json`은 update 단위, `live_progress.json`은 환경 step 단위 진행 상황입니다. 실행 로그는 `output/logs/`에 있습니다.

## TensorBoard

```powershell
& 'C:\Users\lazzyman\anaconda3\envs\waam\python.exe' -m tensorboard.main --logdir output\train_e_40updates_20261019\tensorboard --host 127.0.0.1 --port 6011 --reload_interval 2 --samples_per_plugin images=1
```

`http://127.0.0.1:6011/#images`에서 `latest_gantt` run/tag를 선택합니다. 가장 최근에 완료한 학습 레이어의 간트 한 장만 표시합니다. 이미지 제목의 step이 실제 학습 step이며, PPO scalar 이력은 유지합니다.

## 검증

`smoke_test.py`는 충돌 작업 넘기기 이후의 주 작업 지속, 3대 동시 적층이 가능한 합성 사례, 적층 길이 보존, 출발 좌표 action, 실제 PPO 가중치 갱신, sample validator, CSV 캐시 재사용을 확인합니다. `--all-training-first-layers`는 학습 STL 6개의 첫 레이어까지 검사합니다. 이는 6개 STL 전체 검증을 대체하지 않습니다.

확인 결과: [스모크 결과](output/smoke_e_20261019_run3/summary.json), [학습~최종 CSV 저장 통합 검사](output/pipeline_smoke_e_20261019/training.json). 합성 교차 사례에서 R2 작업 하나를 R1에게 넘긴 뒤 R2가 다른 작업을 계속했고 3대 동시 적층은 12.241초였습니다. 초기 정책의 실제 STL 첫 레이어 검사에서는 04의 3대 동시 적층이 27.996초, 05는 368.123초였습니다. 작은 01·03·06에서는 이 검사 action으로 3대 동시 적층이 발생하지 않았습니다. 이 결과들은 40-update 학습 성과를 뜻하지 않습니다.

활성 스케줄러는 `handoff_scheduler.py`입니다. `priority_scheduler.py`에서는 기존 연속 충돌 검사 및 시간 구간 보간 함수를 재사용하며, d의 정지·재개 `schedule()`은 호출하지 않습니다.

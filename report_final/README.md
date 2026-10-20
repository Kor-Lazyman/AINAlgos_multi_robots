# WAAM 실험 보고서와 결과

`combined_report.docx`는 사용자가 작성 중이던 Word 문서를 복구한 뒤, 원래 Main·minor1·minor2 본문과 이미지, 표를 그대로 둔 상태에서 **minor1 대 1.1.1.e retry1** 비교를 덧붙인 문서입니다. 비교는 동일한 원본 STL 6개 및 공통 validation 6개의 makespan, 계산시간, Validator 판정과 양쪽 WAAM Validator 간트를 포함합니다. 원래 작성본과 잘못 교체했던 문서는 `recovery/`에 각각 보관했습니다. 수치 원본은 `minor1_retry1_comparison.csv`입니다.

## 1.1.1.e retry1 40-update 최종 결과

`1.1.1e-retry1/`에 새로운 2,560-step 최종 체크포인트와 학습 STL 6개, validation 8개 평가를 추가했습니다. `combined_report_minor2_e_baseline.docx`는 자동 생성됐던 이전 비교 보고서로 별도 보존했습니다.

간트 PNG는 각 PASS 판정에 실제 사용된 trajectory를 WAAM Validator 대시보드의 `build_gantt_figure`로 그린 브라우저 캡처입니다. 각 사례의 `waam_validator_gantt.html`은 인터랙티브 원본입니다. 14개 입력 파일의 SHA256이 저장된 Validator 검증 입력 기록과 일치하는지 확인했습니다. `1.1.1e-retry1/results.csv`에 초 단위의 정확한 Makespan과 사례별 계산 시간이 있습니다. 전체 학습과 최종 평가의 합계 경과시간은 `model/training.json`에 별도로 기록됐습니다.

## Minor1 자료 이전

기존 `version 1.0.1/report final/minor1`의 전체 자료를 `minor1/`로 이전했습니다. Word 보고서, 모델과 placement 체크포인트, runtime, 학습 STL 및 validation 결과, trajectory, 간트차트, 수도코드, 기존 output까지 포함합니다. 이전한 276개 파일의 SHA256을 검증했으며 목록은 `minor1_transfer_manifest.json`에 있습니다. 공용 environment는 기존 것과 동일합니다. Minor1 개별 보고서는 `minor1/minor1_중간보고서.docx`에 있습니다.

두 실험의 2,560-step 모델과 저장된 평가 결과입니다. 1.1.1.e는 스케줄러 변경 전 40-update 최종 모델입니다. best_model.zip(32-update)은 별도 보관하며 보고서 수치에는 사용하지 않았습니다.

각 실험 폴더에는 model, runtime, stl_files, validation_data, pseudocode와 test-version.py가 있습니다. 각 입력 폴더의 input에는 Validator에 사용한 STL/config/trajectory, validation에는 공식 Validator JSON과 CSV, gantt.png에는 저장 trajectory로 그린 간트가 있습니다. e의 original_input은 위치 조정 전 입력이며, 재실행에는 이것을 사용합니다. input/target.stl은 이미 이동된 STL이므로 e 재실행에 사용하면 위치 조정이 중복될 수 있습니다.

## 실행

```powershell
& 'C:\Users\lazzyman\anaconda3\envs\waam\python.exe' .\minor2\test-version.py --stl .\minor2\stl_files\01\input\target.stl
& 'C:\Users\lazzyman\anaconda3\envs\waam\python.exe' .\1.1.1e\test-version.py --stl .\1.1.1e\stl_files\01\original_input\target.stl
```

생성물은 각 실험의 output에 저장합니다. --config, --device cpu, --output 옵션을 사용할 수 있습니다. 기존 모델을 불러오는 평가이며 재학습하지 않습니다.

all_results.csv에 정확한 초 단위 수치와 체크포인트 SHA256, 원본 출처가 있습니다. 활용률은 (이동+적층)/makespan이며 동시 적층률과 다릅니다. 계산시간은 각 실행에 저장된 측정값으로 하드웨어·캐시·측정 범위가 완전히 통제된 벤치마크는 아닙니다. minor2 validation은 기존 report final의 256-step 대신 같은 2,560-step 체크포인트 평가를 사용합니다. e의 추가 validation 2개는 minor2 비교 결과가 없습니다.

보고서의 설명 및 코멘트 칸은 작성자가 채울 수 있게 비워 두었습니다. TensorBoard 파일은 포함하지 않습니다.

## 1.1.1.e retry1 수도코드

실제 retry1 구현의 STL XY 배치 전처리, 레이어별 PPO action, 소유 작업 충돌 재검토와 handoff, makespan reward 및 학습 설정을 정리했습니다. 수도코드 원문과 논문 형식 이미지를 확인할 수 있습니다.

- [수도코드 설명 및 설정](1.1.1e-retry1/pseudocode/algorithm.md)
- [수도코드 이미지](1.1.1e-retry1/pseudocode/algorithm.png)
- [텍스트 수도코드](1.1.1e-retry1/pseudocode/algorithm.txt)

## ETC
코드 기준으로 정리하면 다음과 같습니다.

| 항목 | Minor1 | 1.1.1.e retry1 |
|---|---|---|
| 환경 버전 | `1.0.2-minor` | `1.1.1.e-retry1` |
| 레이어 1-step | 레이어 1개 경로 생성 | 레이어 1개 경로 생성 |
| Layer action space | `MultiDiscrete([8, 3, 4, 2, 2, 3, 6])` | `MultiDiscrete([8, 33, 33, 2, 33, 33, 2, 33, 33, 2, 6])` |
| Layer observation shape | `(309,)` | `(305,)` |
| 레이어 높이 | `2.0 mm` | `2.0 mm` |

### Minor1 action

Minor1은 레이어 경로 정책과 STL 위치 조정 정책이 분리되어 있습니다.

Layer policy:

```text
[ hatch_angle,
  hatch_spacing,
  start_corner,
  reverse,
  partition_axis,
  partition_quota,
  robot_order ]
```

각 값의 의미는 다음과 같습니다.

- `hatch_angle`: 8개 선택, 0°부터 157.5°까지 22.5° 간격
- `hatch_spacing`: 비드 폭의 0.8배, 0.9배, 1.0배
- `start_corner`: 네 모서리 중 시작 위치 선택
- `reverse`: 경로 진행 방향 반전
- `partition_axis`: X축 또는 Y축 기준 영역 분할
- `partition_quota`: 로봇별 작업 비율 선택
- `robot_order`: 3개 로봇의 작업 우선순위 6가지

별도의 placement policy도 있습니다.

```text
Box(2,)
```

즉, STL 전체에 적용할 전역 XY 이동량 `Δx, Δy`를 연속값으로 결정합니다. 이 이동은 슬라이싱 전에 STL 전체에 적용되며 모든 레이어에 동일하게 적용됩니다.

Minor1 placement observation은 다음과 같습니다.

```text
shape = (42,)
dtype = float32
```

여기에는 STL bounds·extent·중심·부피·표면적, 작업공간 정보, 3대 로봇의 base/home/reach 정보, bead width, layer height, 이동 속도와 적층 속도가 포함됩니다.

Minor1 Layer observation `(309,)`에는 다음 정보가 포함됩니다.

- 현재 레이어 인덱스와 전체 레이어 수
- 현재 IoU와 직전 레이어 IoU
- 현재 makespan과 직전 레이어 소요시간
- 로봇 3대의 이전 작업량
- 현재 레이어의 Z 위치, bounds, 면적, 둘레
- 16×16 레이어 raster, 총 256개 값
- 로봇별 base, home, reach radius, arm envelope, TCP radius
- bead width, layer height, travel/deposition speed
- collision clearance
- validator의 coverage, overfill, IoU 관련 기준값

### 1.1.1.e retry1 action

1.1.1.e에서는 action을 더 세밀하게 만들었습니다.

```text
[ hatch_angle,
  R1_start_x, R1_start_y, R1_direction,
  R2_start_x, R2_start_y, R2_direction,
  R3_start_x, R3_start_y, R3_direction,
  layer_priority ]
```

구체적으로는 다음과 같습니다.

- `hatch_angle`: 8개, 22.5° 간격
- 각 로봇 시작 X/Y: 각각 33단계 grid
- 각 로봇 방향: CW 또는 CCW
- `layer_priority`: 3개 로봇 우선순위 6가지

따라서 action 차원은 총 11개이고:

```text
MultiDiscrete([8, 33, 33, 2, 33, 33, 2, 33, 33, 2, 6])
```

입니다.

1.1.1.e에는 Minor1처럼 학습되는 별도 placement action이 없습니다. 대신 학습 전에 `positioning.py`가 STL 내부 샘플 점을 XY로 투영하고, 세 로봇의 점유 비율이 비슷해지도록 하나의 전역 XY 이동을 결정합니다. 그 이동을 STL 전체에 적용한 후 슬라이싱합니다.

1.1.1.e observation `(305,)`에는 다음이 포함됩니다.

- 현재 레이어 인덱스
- 현재 makespan
- 직전 레이어 소요시간
- 로봇 3대의 직전 작업량
- 현재 레이어의 Z, bounds, 면적, 둘레
- 로봇별 소유 영역 비율
- 세 로봇 공통 도달 영역 비율
- Robot 2·3 공통 도달 영역 비율
- 16×16 raster 256개
- 로봇별 base/home/reach/arm/TCP 정보
- bead width, layer height, deposition speed, travel speed

### 레이어 분할 간격

두 버전 모두 설정 파일에서:

```yaml
layer_height_mm: 2.0
```

으로 설정되어 있습니다.

따라서 STL은 **Z축 방향으로 2.0 mm 간격의 레이어**로 나뉩니다. 각 레이어의 경로 생성이 PPO 환경의 1 step이며, 한 레이어가 끝나면 모든 로봇이 barrier를 거쳐 다음 레이어로 넘어갑니다.

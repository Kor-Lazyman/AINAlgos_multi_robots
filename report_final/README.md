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

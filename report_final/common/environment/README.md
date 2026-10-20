# 3대 로봇 Gymnasium 환경

`gym_wrapper.py`의 `WaamGymEnv`를 SB3 PPO에서 사용할 수 있습니다.
기존 `env.py`의 검사 함수들을 호출하며 실행 중 CSV·JSON·보고서를 생성하지 않습니다.
`step()`의 `info`는 Gymnasium API가 요구하는 메모리상의 딕셔너리입니다.

## 관측과 행동

관측은 `float32`, 크기 `(3, 5)`입니다. 행 순서는 Robot 1, 2, 3입니다.

```text
[[현재 시간(s), x(mm), y(mm), z(mm), mode],
 [현재 시간(s), x(mm), y(mm), z(mm), mode],
 [현재 시간(s), x(mm), y(mm), z(mm), mode]]
```

모드 코드는 `T=0`, `D=1`, `W=2`, `F=3`입니다. 관측의 모드는 직전 행동에서 선택한
모드이며, `F`는 유지됩니다. 세 로봇의 시간은 동기화된 현재 시각입니다.

행동은 `(3, 4)` 크기의 `[-1, 1]` 연속값입니다. 첫 세 값은 **절대 목표 XYZ 좌표**로
변환하고, 네 번째 값은 다음 구간으로 모드를 선택합니다.

| 행동의 네 번째 값 | 모드 |
| --- | --- |
| `[-1, -0.5)` | T: 이동 |
| `[-0.5, 0)` | D: 적층 이동 |
| `[0, 0.5)` | W: 대기 |
| `[0.5, 1]` | F: 완료 |

XYZ의 기본 범위는 로봇 초기 위치, 작업 영역, STL 경계를 포함합니다.
`xyz_bounds=(최소_XYZ, 최대_XYZ)`로 직접 지정할 수 있습니다. 실제 좌표와 모드로
행동을 만들려면 `action_from_targets()`를 사용합니다. W/F는 XYZ를 무시하고 현재
위치를 유지합니다. F가 된 로봇에 이후 T/D 행동을 주어도 다시 움직이지 않습니다.

```python
from environment.gym_wrapper import WaamGymEnv

env = WaamGymEnv()
observation, info = env.reset(seed=42)
action = env.action_from_targets(observation[:, 1:4], ["W", "W", "F"])
observation, reward, terminated, truncated, info = env.step(action)
trajectory = env.get_trajectory()  # 열별 리스트 딕셔너리. F는 W로 변환됨.
env.close()
```

## 시간과 종료

세 로봇은 각 단계에서 동시에 행동을 시작합니다. T/D의 소요 시간은 이동 거리와
config.yaml의 해당 속도로 결정합니다. 먼저 도착한 로봇은 가장 늦은 로봇까지
기다립니다. W/F만 있는 단계도 `wait_time_s`(기본 0.1초)만큼 시간이 흐릅니다.
종료한 로봇도 그 위치에 계속 존재하므로 다른 로봇과의 충돌 검사에 포함됩니다.

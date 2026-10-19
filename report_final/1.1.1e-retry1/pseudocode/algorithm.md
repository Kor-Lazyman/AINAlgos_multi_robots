# Algorithm 1. 1.1.1.e retry1 layer PPO scheduling

**Input:** STL M, robot configuration C, training set D_tr, validation set D_val

**Output:** trained PPO policy and collision-checked robot trajectories

```text
01  Sample solid interior points from M; give every 3D sample weight 1
02  Project samples to XY and preserve multiplicity from different Z heights
03  Search rigid XY shifts that fit the workspace and all robot reach regions
04  Assign each projected point to its nearest reachable robot
05  Choose the shift minimizing the standard deviation of the three point shares;
    break ties by maximum share error, travel cost, then shift magnitude
06  Translate the entire STL by this one XY shift, then slice it into layers
07  For each layer, create fixed-spacing hatch segments at the selected angle
08  Split segments at reach-circle boundaries and nearest-base bisectors;
    assign each segment to its nearest reachable robot
09  Policy selects hatch angle (8), each robot start XY (33 x 33),
    each sweep direction (CW/CCW), and one of 6 priority orders
10  Project each requested start onto an owned segment, split it there, and order
    the robot segments by the selected angular sweep
11  for each robot r in the selected priority order do
12      for each deposition task q owned by r do
13          Test approach, deposition, and safe return against reserved trajectories
14          if safe then reserve q for r
15          else keep q pending and continue with the remaining owned tasks
16      Retry pending tasks after any task is accepted; stop if none remain or
        a full sweep accepts no task
17  Transfer only unresolved tasks to the highest-priority robot that can reach them;
    if none qualifies, retain the tasks in the original robot deferred queue
18  Append deferred work after primary routes; delay its home release only if needed
19  Verify every task occurs once, deposition length is preserved, and trajectories
    pass physical collision and trajectory-semantics checks
20  Set layer reward r_l = -T_l; episode return = -sum_l T_l = -makespan
21  Train PPO for 40 updates x 64 steps; keep the lowest validation-mean-makespan
    checkpoint; do not early-stop. Run WAAM Validator for evaluation only
```

**Training:** PPO MlpPolicy; policy/value MLP layers [128, 128]; learning rate 0.0003; gamma 1.0; GAE lambda 0.95; batch size 32; 10 epochs; 2,560 steps. Policy runs on CUDA and geometry on CPU. Training starts from fresh random weights.

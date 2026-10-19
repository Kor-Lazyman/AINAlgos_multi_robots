"""Present existing final CSVs without evaluating the models again."""
import csv
import html
import json
import os
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
RUN=ROOT/'output/train_e_40updates_20261019'


def main():
    with (RUN/'final_comparison.csv').open(encoding='utf-8-sig',newline='') as f:
        records=list(csv.DictReader(f))
    lines=['# 1.1.1.e 최종 결과','',
           '40 updates / 2,560 환경 step 완료. 아래 결과는 마지막 final_model.zip 기준입니다.',
           '학습 및 최종 평가 총 소요: 3,828.419초 (1시간 3분 48초). 학습 STL 6개 + validation 8개 모두 공식 validator PASS, 충돌 0건.',
           '저장된 CSV/trajectory를 읽었으며 모델 평가를 재실행하지 않았습니다. 원본 STL/config 해시가 비교 대상과 일치합니다.',
           'minor1은 1,024-step 체크포인트, minor2는 2,560-step 최종 모델입니다. 버전별 배치·경로·스케줄러 및 학습량 차이가 있으므로 학습만의 효과로 해석할 수 없습니다.','']
    web=['<!doctype html><html lang="ko"><meta charset="utf-8"><title>1.1.1.e 최종 결과</title>',
         '<style>body{font:16px system-ui,sans-serif;max-width:1250px;margin:35px auto;padding:0 20px;color:#1a2635}table{border-collapse:collapse;width:100%;margin:20px 0}td,th{padding:9px;border-bottom:1px solid #ddd;text-align:right}td:first-child,th:first-child{text-align:left}th{background:#edf2f7}img{max-width:100%}a{color:#165ac4}</style>',
         '<h1>1.1.1.e 최종 결과</h1><p>40 updates / 2,560 step 완료 · 전체 14개 PASS · 충돌 0건</p>',
         '<p>학습·평가 총 1시간 3분 48초. 마지막 final_model 기준이며 best_model과 다릅니다. 저장된 결과를 사용했습니다.</p>']
    names={'01':'Honeycomb','02':'Spiral','03':'Triangular truss','04':'Motor inner','05':'Twisted shell','06':'Angle frame'}
    for split,title in [('train','학습 STL 6개'),('validation','Validation 8개')]:
        lines += ['## '+title,'','단위: 초. 변화율은 (e / minor − 1) × 100%이며 음수는 단축입니다.','',
                  '| 입력 | minor1 | minor2 | 최종 e | e vs minor1 | e vs minor2 |','|---|---:|---:|---:|---:|---:|']
        web += [f'<h2>{title}</h2><p>단위: 초 · 음수 변화율은 단축</p><table><tr><th>입력</th><th>minor1</th><th>minor2</th><th>최종 e</th><th>vs minor1</th><th>vs minor2</th></tr>']
        selected=[r for r in records if r['split']==split]
        for r in selected:
            label=r['job']+(' '+names[r['job']] if split=='train' else '')
            vals=[label]+[f'{float(r[k]):,.3f}' if r[k] else '—' for k in ('minor1_makespan_s','minor2_makespan_s','e_makespan_s')]
            vals += [f'{float(r[k]):+.2f}%' if r[k] else '—' for k in ('e_vs_minor1_pct','e_vs_minor2_pct')]
            lines += ['| '+' | '.join(vals)+' |']
            web += ['<tr>'+''.join('<td>'+html.escape(v)+'</td>' for v in vals)+'</tr>']
        common=[r for r in selected if r['minor1_makespan_s']]
        sums={m:sum(float(r[m+'_makespan_s']) for r in common) for m in ('minor1','minor2','e')}
        summary=f'공통 {len(common)}개 합계: minor1 {sums["minor1"]:,.3f}s / minor2 {sums["minor2"]:,.3f}s / e {sums["e"]:,.3f}s. e 변화율: minor1 대비 {100*(sums["e"]/sums["minor1"]-1):+.2f}%, minor2 대비 {100*(sums["e"]/sums["minor2"]-1):+.2f}%.'
        lines+=['',summary,''];web+=['</table><p>'+summary+'</p>']
    learning='Validation 8개 평균 makespan: 학습 전 2,407.197초 → 최종 2,365.761초 (1.72% 단축).'
    best='최저 검증 평균은 update 32 / step 2,048의 2,019.196초였습니다. 최종 update 40은 이보다 17.16% 길어 마지막 모델이 최선은 아닙니다. best_model.zip의 학습 STL 전체 평가는 아직 별도로 수행하지 않았습니다.'
    lines += ['## 학습 전후와 best checkpoint','',learning,best,'','## 로봇 활용률과 간트','',
              '활용률 = (적층 시간 + 이동 시간) / makespan. 동시 적층 시간과는 다른 지표입니다.','',
              '| 입력 | R1 | R2 | R3 | 전체 간트 |','|---|---:|---:|---:|---|']
    web += ['<h2>학습 전후</h2><p>'+learning+'</p><p>'+best+'</p><h2>전체 간트</h2>']
    for r in records:
        relative=Path(os.path.relpath(Path(r['artifact_dir'])/'gantt.png',RUN)).as_posix()
        assert (RUN/relative).is_file()
        util=[f'{100*float(r[f"robot{i}_utilization"]):.2f}%' for i in (1,2,3)]
        lines+=['| '+r['split']+'/'+r['job']+' | '+' | '.join(util)+f' | [보기](<{relative}>) |']
        web += [f'<details><summary>{r["split"]}/{r["job"]} — R1 {util[0]} · R2 {util[1]} · R3 {util[2]}</summary><img src="{html.escape(relative)}" loading="lazy"></details>']
    concurrency='05 Twisted shell은 전체 182,814.394초 중 61,830.325초(33.82%) 동안 3대가 동시에 적층했습니다. 04 Motor inner는 292.866초(0.42%)입니다. 공통 validation 00~05와 학습 STL 06에서는 최종 모델이 R2 한 대만 사용했습니다. 따라서 3대 활용이 모든 입력에서 달성된 것은 아닙니다.'
    lines+=['',concurrency,'','## 저장 자료','','- [최종 학습 STL CSV](final_stl.csv)',
            '- [최종 validation CSV](final_validation.csv)','- [최종 통합 CSV](final_results.csv)',
            '- [minor1·minor2 비교 CSV](final_comparison.csv)','- [최종 모델](final_model.zip)',
            '- [검증 최적 모델](best_model.zip)','']
    web += ['<p>'+concurrency+'</p><p><a href="final_stl.csv">학습 STL CSV</a> · <a href="final_validation.csv">Validation CSV</a> · <a href="final_comparison.csv">비교 CSV</a> · <a href="FINAL_REPORT.md">상세 보고서</a></p></html>']
    (RUN/'FINAL_REPORT.md').write_text('\n'.join(lines),encoding='utf-8')
    (RUN/'final_report.html').write_text('\n'.join(web),encoding='utf-8')
    assert '최종 결과' in (RUN/'FINAL_REPORT.md').read_text(encoding='utf-8')
    print('UTF-8 reports saved; all 14 Gantt links verified.')


if __name__=='__main__':main()

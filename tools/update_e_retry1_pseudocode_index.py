from pathlib import Path
import hashlib
import json

report = Path(r'C:\Users\lazzyman\Desktop\AINalgos2\version 1.1.1.e\report_final')
readme = report / 'README.md'
index = report / 'index.html'
section = '''\n## 1.1.1.e retry1 수도코드\n\n실제 retry1 구현의 STL XY 배치 전처리, 레이어별 PPO action, 소유 작업 충돌 재검토와 handoff, makespan reward 및 학습 설정을 정리했습니다. 수도코드 원문과 논문 형식 이미지를 확인할 수 있습니다.\n\n- [수도코드 설명 및 설정](1.1.1e-retry1/pseudocode/algorithm.md)\n- [수도코드 이미지](1.1.1e-retry1/pseudocode/algorithm.png)\n- [텍스트 수도코드](1.1.1e-retry1/pseudocode/algorithm.txt)\n'''
old = readme.read_text(encoding='utf-8')
if '## 1.1.1.e retry1 수도코드' not in old:
    readme.write_text(old.rstrip() + '\n' + section, encoding='utf-8')
old_html = index.read_text(encoding='utf-8')
if '1.1.1e-retry1/pseudocode/algorithm.md' not in old_html:
    addition = '<p><a href="1.1.1e-retry1/pseudocode/algorithm.md">1.1.1.e retry1 pseudocode</a> · <a href="1.1.1e-retry1/pseudocode/algorithm.png">paper-style algorithm image</a></p>\n'
    index.write_text(old_html.rstrip() + '\n' + addition, encoding='utf-8')

manifest_path = report / 'manifest.json'
entries = json.loads(manifest_path.read_text(encoding='utf-8'))
by_path = {entry['path']: entry for entry in entries}
paths = [
    report / 'combined_report.docx', report / 'README.md', report / 'index.html',
    report / '1.1.1e-retry1' / 'pseudocode' / 'algorithm.md',
    report / '1.1.1e-retry1' / 'pseudocode' / 'algorithm.txt',
    report / '1.1.1e-retry1' / 'pseudocode' / 'algorithm.png',
    report / '1.1.1e-retry1' / 'pseudocode' / 'algorithm_paper_style.png',
    report / 'recovery' / 'combined_report_before_pseudocode_20261019.docx',
    report / 'recovery' / 'combined_report_before_pseudocode_restyle_20261019.docx',
    report / '1.1.1e-retry1' / 'pseudocode' / 'algorithm_original_serif.png',
]
for path in paths:
    if path.is_file():
        rel = path.relative_to(report).as_posix()
        by_path[rel] = {'path': rel, 'size': path.stat().st_size,
                        'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
manifest_path.write_text(json.dumps(sorted(by_path.values(), key=lambda e: e['path']),
                                    ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print('Updated README, index, and manifest')

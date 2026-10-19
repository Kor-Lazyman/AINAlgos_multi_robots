from pathlib import Path
from docx import Document

path=Path(__file__).resolve().parents[1]/'report_final/combined_report.docx'
doc=Document(path)
old='계산 시간은 최종 모델로 해당 STL의 trajectory를 생성하고 평가한 실행의 경과시간이다.'
new='계산 시간은 최종 모델로 해당 STL의 trajectory를 생성한 경과시간이며, 별도 WAAM Validator 실행 시간은 포함하지 않는다.'
found=0
for para in doc.paragraphs:
    if old in para.text:
        para.text=para.text.replace(old,new)
        found+=1
assert found==1,found
doc.save(path)
print('Corrected computation-time definition')

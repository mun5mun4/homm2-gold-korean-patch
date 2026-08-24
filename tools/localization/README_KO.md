# 현지화 도구

- `h2c_rebuilder.py`: H2C/MP2 컨테이너의 확인된 텍스트 필드를 바이트 보존 방식으로 재구성
- `h2k3_bank.py`: `KOREAN.BIN` H2K3 v3 직렬화·파싱·원자적 로드 모델
- `final_text_hotfix.py`: 고정된 pre-beta.2 누적 EXE에 beta.2 문구 교정과 주문 재배치·H2K3 본체 진입 전 호출·실주소 허용 범위·합류 예비 문구를 함께 적용하거나 결과 해시를 검증
- `final_bank_hotfix.py`: 고정된 beta.2 `KOREAN.BIN`에서 합류 문장을 바꾸고 Object2 기반 일반 descriptor 155개를 실기 재배치 주소로 교정한 뒤 구조·체크섬·결과 해시를 검증

이 디렉터리의 도구는 게임을 자동 실행하거나 DOSBox를 제어하지 않습니다. 입력·출력 해시가 고정된 오프라인 변환만 제공합니다.

# Heroes of Might and Magic II Gold 한국어 패치

`v0.9.0-beta.6`는 GOG 영문 DOS판용 한국어 패치입니다. 게임 실행 파일 전체나 원작 리소스를 포함하지 않으며, 설치기가 사용자의 적법한 원본 또는 검증된 공개 beta.4·beta.5 설치본을 확인한 뒤 바이너리 델타와 설치 시 생성한 한글 글리프를 적용합니다.

## 포함 범위

- 오리지널 및 확장 캠페인 맵 47개 문장 번역
- 영웅·성·전투·주문·아티팩트·모험 지도의 주요 비이미지 UI
- 설치할 때 생성하는 874자 한글 글리프와 외부 문자열 은행 `KOREAN.BIN`
- 배포에서 유일하게 사용하는 글꼴 `fonts/NanumGothicCoding-Regular.ttf`
- 렌더러 v2의 고정 기준선으로 beta.4에서 한글 높이가 들쭉날쭉하던 문제 수정
- 영웅 능력치의 `Knowledge` 표시를 `지력`으로 교정
- 외부 문자열 은행을 게임 본체 진입 전에 불러오고 실기 재배치 주소를 사용하도록 교정
- 중립 부대 합류 제목과 동적 문장을 한국어로 표시
- 대상 주문 로그의 조사 오류 수정
  - 예: `Bikko: 외눈들에게 저주 시전.`
- 도주 안내의 `air elementals` 직접 폴백을 `공기정령`으로 수정

## 이번 베타에서 제외한 범위

- 버튼·제목·퍼즐 화면처럼 그림에 박힌 영문
- 일반 MP2/MX2 사용자 지도 문장
- 세이브 파일, 음악, 영상, DOSBox 및 GOG 구성요소

beta.3까지 시험적으로 수정했던 이미지 UI 4개는 배포물에서 제거하고 원본 영어 이미지로 되돌립니다. 따라서 일부 이미지 UI는 영어로 표시됩니다. 이는 알려진 제한이며 게임 문자열 번역 누락과는 별도입니다. 모집 창의 `Cost per troop:` 한 곳은 설치 시 나눔고딕코딩 작은 글리프로 `병력당 비용:`을 생성해 표시합니다.

## 글꼴

`INSTALL.cmd`는 SIL Open Font License 1.1의 NanumGothicCoding Regular만 사용합니다. 일반 글꼴은 13x14 셀·advance 13·공통 기준선 14, 작은 글꼴은 11x12 셀·advance 11·공통 기준선 12로 생성합니다. 글자별 확대·축소 없이 face 전체의 공통 정수 크기와 tight crop 위치를 보존하므로 beta.4 렌더러 v1의 높이 회귀를 수정합니다.

설치기가 원본 AGG의 영문 글리프를 보존한 채 필요한 한글 글리프를 그 자리에서 생성하므로, 바탕체로 미리 만든 고정 래스터나 바탕체 파일은 배포 ZIP에 포함하지 않습니다.

beta.6 배포판은 사용자 글꼴 선택 스크립트와 관련 명령줄 옵션을 포함하지 않습니다. ZIP 안의 글꼴 파일도 나눔고딕코딩 하나뿐입니다.

## 빠른 설치

공개 beta.4·beta.5 설치자는 제거하지 않고 beta.6의 `INSTALL.cmd`를 실행해 직접 업그레이드합니다. 이전 버전에서 기본 글꼴이나 사용자 글꼴 중 무엇을 사용했든 나눔고딕코딩으로 자동 전환됩니다.

설치기는 동봉한 고정 beta.4·beta.5 manifest, 기존 receipt와 현재 설치 파일을 검증합니다. 업그레이드가 실패하면 업그레이드 직전 버전으로 롤백하고, 업그레이드된 beta.6를 제거하면 최초 GOG 원본을 복원합니다.

beta.1~beta.3 설치자는 설치에 사용한 이전 배포 폴더의 `UNINSTALL.cmd`로 원본을 복구한 뒤 beta.6를 설치해야 합니다. 이전 배포 폴더가 없다면 해당 버전 ZIP을 다시 받아 제거할 수 있습니다.

1. GOG Galaxy, Heroes II, DOSBox를 모두 종료합니다.
2. ZIP을 원하는 폴더에 모두 풉니다.
3. `INSTALL.cmd`를 실행합니다.
4. 설치기는 GOG Galaxy 기본 경로를 자동으로 확인합니다.

```text
C:\Program Files (x86)\GOG Galaxy\Games\HoMM 2 Gold
```

5. 자동 탐지가 실패하면 명령 프롬프트에서 다음처럼 게임 폴더를 지정합니다.

```text
homm2-ko-patcher.exe install --game-dir "C:\Program Files (x86)\GOG Galaxy\Games\HoMM 2 Gold"
```

소스 형태의 `homm2_ko_patcher.py`를 직접 실행하려면 Python 3과 Pillow 12.0.0이 필요합니다. 일반 사용자는 필요한 런타임이 모두 포함된 `homm2-ko-patcher.exe`를 사용하면 됩니다.

상세 절차와 제거 방법은 `INSTALL_KO.md`를 참고하세요.

## 지원 원본

- GOG gameId: `1207658785`
- GOG buildId: `52745329670822422`
- 언어: English

다른 언어판, CD판, 지원하지 않는 수정 설치본에는 설치하지 않습니다. 설치기는 50개 원본 파일의 SHA-256을 전부 확인하며 하나라도 다르면 변경 전에 중단합니다. 설치 시 생성되는 AGG의 실제 해시는 로컬 receipt에 기록해 검증과 제거에 사용합니다.

## 라이선스와 권리

프로젝트 소스와 번역은 `GPL-2.0-only` 조건으로 배포됩니다. 기본 NanumGothicCoding Regular는 SIL Open Font License 1.1을 따릅니다. 원작 게임·그래픽·지도·캠페인·상표의 권리는 각 권리자에게 있습니다. 자세한 내용은 `NOTICE.md`, `THIRD_PARTY_NOTICES.md`, `COPYING.GPL-2.0`을 확인하세요.

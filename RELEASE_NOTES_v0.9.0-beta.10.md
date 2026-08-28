# Heroes II Gold 한국어 패치 v0.9.0-beta.10

릴리스 날짜: 2026-08-28

이번 버전은 다른 PC의 기본 GOG 바로가기에서 영상 재생 중 종료되거나 캠페인 자막이 나오지 않던 호환성 문제를 고쳤습니다. 수정본은 기본 GOG 실행 환경에서 게임 실행과 오리지널 캠페인 자막 표시를 사용자 실기로 확인했습니다.

## 주요 변경

- DOSBox 실행 환경마다 달라질 수 있는 DOS/4GW LE Object 로드 주소에 독립적인 자막 로더 적용
- 오프닝·캠페인 영상 51편, 57개 장면, 한국어 자막 388개 유지
- 자막의 아라비아 숫자를 한글 수사로 바꿔 숫자와 한글의 높이 차이를 완화
- 흰색 글자·검은 외곽선, 음성 기준 동기화와 반복 깜빡임 억제 유지
- beta.9의 렌더러 v3와 기본 `Iropke Batang Medium`, 보완 `NanumGothicCoding Regular` 방식 유지
- 공개 beta.4·beta.5·beta.6·beta.7·beta.8·beta.9 설치본에서 직접 업그레이드 지원

## 설치

1. Heroes II, DOSBox, GOG Galaxy를 모두 종료합니다.
2. `homm2-ko-v0.9.0-beta.10-win-gog.zip`을 내려받아 모두 풉니다.
3. 기본 이롭게 바탕체는 `INSTALL.cmd`, 사용자가 보유한 글꼴은 `INSTALL_CUSTOM_FONT.cmd`를 실행합니다.

beta.1~beta.3 사용자는 먼저 해당 버전의 `UNINSTALL.cmd`로 GOG 원본을 복구해야 합니다. beta.4~beta.9 사용자는 기존 버전을 제거하지 않고 바로 설치할 수 있습니다.

지원 대상은 GOG gameId `1207658785`, buildId `52745329670822422`, English DOS판입니다. 자세한 설치·복구·제거 방법은 ZIP 안의 `INSTALL_KO.md`를 확인하세요.

## 배포 형식

배포 ZIP에는 완성된 게임 실행 파일, AGG, 캠페인 맵이나 원본 SMK 영상이 들어 있지 않습니다. 정확한 지원 원본에서만 사용할 수 있는 바이너리 델타, 프로젝트 문자열 은행, 번역 데이터, 설치기 소스와 OFL 1.1 글꼴을 포함하며 글리프·버튼·AGG는 설치 시 생성합니다.

beta.10 배포 입력은 다음 identity로 고정됩니다.

- `HEROES2.EXE`: 1,523,420바이트, SHA-256 `87B175EF0698C65893BAF6A0581E74BEA60CCECA0D8DF57E9DF7614B27DB2365`
- `KOREAN.BIN`: 36,159바이트, SHA-256 `37FDC1F372627E7B637EEEBFC15610E26B427E66947D7AA699B46B807F7338DA`
- beta.9 upgrade manifest: 34,263바이트, SHA-256 `CEB8E7D765DBFA2FBB6D955364E68A0D2A158B31BDA7DA70C1F04A85C37AEBDD`

각 다운로드의 해시는 함께 제공하는 `SHA256SUMS.txt`에서 확인할 수 있습니다.

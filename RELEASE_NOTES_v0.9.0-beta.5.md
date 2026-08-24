# v0.9.0-beta.5 릴리스 노트

날짜: 2026-08-24

beta.5는 2026-08-24 공개된 beta.4 prerelease의 동적 폰트 높이 회귀와 영웅 능력치 `Knowledge` 표시를 수정하고, beta.4에서 직접 업그레이드하는 경로를 추가한 배포판입니다.

## 주요 수정

- 기본 글꼴을 저해상도 DOS 화면에 맞는 `NanumGothicCoding Regular`로 변경했습니다.
- 렌더러 v2가 모든 한글을 face 공통 기준선에 맞춰 beta.4에서 글자 높이가 들쭉날쭉하던 문제를 수정합니다.
- 영웅 화면의 영문 `Knowledge`를 `지력`으로 표시합니다.
- beta.4 기본·사용자 글꼴 설치본에서 beta.5로 직접 업그레이드할 수 있습니다.

## 설치와 업그레이드

- 깨끗한 GOG 원본 또는 beta.4 기본 글꼴 설치본: `INSTALL.cmd`
- beta.4 사용자 글꼴 설치본: `INSTALL_CUSTOM_FONT.cmd`를 실행하고 글꼴을 다시 선택
- beta.1~beta.3 설치본: 해당 버전의 `UNINSTALL.cmd`로 GOG 원본을 복구한 뒤 beta.5 설치

beta.4 receipt에는 사용자가 고른 원본 글꼴의 경로를 저장하지 않습니다. 따라서 beta.4 사용자 글꼴 설치본은 직접 업그레이드할 수 있지만 글꼴 재선택이 필수입니다.

설치기는 ZIP에 동봉한 고정 beta.4 manifest, 기존 receipt와 현재 설치 파일을 모두 확인합니다. 업그레이드 도중 실패하면 beta.4 상태로 롤백합니다. 업그레이드된 beta.5를 제거하면 beta.4가 아니라 최초 GOG 원본을 복원합니다.

## 렌더러 v2

| 용도 | 논리 셀 | advance | 공통 ink-bottom 기준선 |
|---|---:|---:|---:|
| 일반 | 13x14 | 13 | 14 |
| 작은 글꼴 | 11x12 | 11 | 12 |

렌더러는 각 face의 모든 한글 전경이 셀에 들어가는 가장 큰 정수 픽셀 크기를 한 번만 선택합니다. 글자별 확대·축소는 하지 않습니다. 실제 mask는 tight crop하되 논리 셀의 `offset_y`를 보존하며 전경 잘림은 0으로 검증합니다. `(1, 1)` 그림자는 셀 오른쪽·아래 경계에서만 제한적으로 잘릴 수 있습니다.

beta.4 렌더러 v1은 글자마다 tight crop한 뒤 `offset_y=0`으로 저장해 서로 다른 ink 높이가 같은 행의 위쪽부터 시작했습니다. 렌더러 v2는 모든 한글의 ink bottom을 같은 기준선에 배치해 이 회귀를 제거합니다.

## `지력` 교정

폰트 없는 `HEROES2.AGG` 기반이 유지하는 번역 BIN은 7개에서 8개로 늘었고 `HEROWIND.BIN`이 추가됐습니다. 빌더는 payload offset 303의 `0A 00` 길이 word를 유지하면서 offset 305의 10바이트가 정확히 `Knowledge\0`일 때만 `82 D8 82 95 00 00 00 00 00 00`(`지력`)으로 교체합니다. 이미 교정된 값은 허용하고 예상 밖의 값은 배포 생성 전에 거부합니다.

## 기본 글꼴과 라이선스

- 파일: `fonts/NanumGothicCoding-Regular.ttf`
- 원본: Google Fonts `google/fonts` commit `90abd17b4f97671435798b6147b698aa9087612f`
- SHA-256: `787EFFD7EFED2ABCA88ADE231FAA8191F4E9FCF85B1805A13EE1DC3724B72089`
- 라이선스: SIL Open Font License 1.1
- 라이선스 파일: `THIRD_PARTY_LICENSES/NANUM_GOTHIC_CODING_OFL.txt`

사용자가 선택한 로컬 `TTF`, `OTF`, `TTC`, `OTC`는 복사·수집·업로드·배포하지 않습니다. 선택한 글꼴에 없는 매핑 문자는 동봉한 나눔고딕코딩으로 보완합니다.

## 범위와 알려진 제한

- 오리지널·확장 캠페인 맵 47개와 주요 비이미지 UI 번역을 포함합니다.
- 일반 MP2/MX2 사용자 지도는 번역 범위에서 제외합니다.
- 그림에 박힌 버튼·제목과 시험 이미지 UI ICN 4개는 원본 영어로 표시됩니다.
- 설치 뒤 `VERIFY.cmd`로 51개 설치 파일과 receipt를 확인할 수 있습니다.

`docs/ACTIVE_FILE_HASHES.json`은 beta.3 활성 번역 트리의 source pin입니다. beta.5 출력 해시 목록이 아니므로 이번 배포에서도 파일 자체를 바꾸지 않습니다.

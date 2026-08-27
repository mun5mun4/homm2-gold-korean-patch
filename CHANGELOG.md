# 변경 기록

## v0.9.0-beta.9 — 2026-08-27

- SIL Open Font License 1.1의 `Iropke Batang Medium` 원본 TTF를 배포 ZIP에 동봉하고 기본 설치 글꼴로 변경
- `INSTALL.cmd` 실행 시 이롭게 바탕체로 874자 게임 글리프, 한글 버튼과 모집 창의 `병력당 비용:`을 동적으로 생성
- 기본 이롭게 바탕체에 없는 매핑 문자는 동봉한 `NanumGothicCoding Regular`로 보완
- `INSTALL_CUSTOM_FONT.cmd`, `--choose-font`, `--font-file`, `--font-index` 사용자 글꼴 선택 기능 유지
- 이롭게 바탕체 및 나눔고딕코딩 원본 파일의 SHA-256과 각각의 OFL 1.1·Reserved Font Name 고지를 패키지에서 고정 검증
- 공개 beta.4·beta.5·beta.6·beta.7·beta.8 설치본에서 beta.9 직접 업그레이드 지원

## v0.9.0-beta.8 — 2026-08-27

- 글리프를 셀 바닥에 맞추던 렌더러 v2를 FreeType `glyph.top`을 보존하는 typographic 기준선 렌더러 v3로 교체
- 선택·보완 face의 공통 ink union으로 픽셀 크기와 기준선을 결정해 혼합 글꼴도 한 줄에서 같은 기준선을 사용하고, 이롭게 바탕체의 `주/조/소` 수직 위치 어긋남 수정
- `INSTALL_CUSTOM_FONT.cmd`, `--choose-font`, `--font-file`, `--font-index` 사용자 글꼴 선택 경로 복구
- 사용자 소유 TTF·OTF·TTC·OTC는 설치 시 로컬에서만 읽고 저장소·게임 폴더·배포 ZIP에 복사하지 않으며, 누락 문자는 동봉한 나눔고딕코딩으로 보완
- 게임 글리프와 한글 버튼·`병력당 비용:` 문구를 같은 선택 글꼴에서 생성하도록 동적 이미지 렌더링 계약 확장
- 메인 메뉴 배경·장식은 원본을 보존하고 선언된 버튼 글씨 영역만 선택 글꼴로 동적 생성
- 배포 ZIP의 글꼴 allowlist는 `NanumGothicCoding-Regular.ttf` 하나로 유지하고 임의의 추가 TTF·OTF를 fail-closed로 거부
- 공개 beta.4·beta.5·beta.6·beta.7 설치본에서 beta.8 직접 업그레이드 지원
- 로컬 `Iropke Batang Medium` 선택 예시로 874자·기준선·전경 잘림 0을 별도 검증하되 해당 글꼴 파일과 생성 래스터·AGG는 배포하지 않음

## v0.9.0-beta.7 — 2026-08-26

- 오프닝·캠페인 영상 51편, 57개 장면에 한국어 자막 388개 추가
- Whisper 전사와 단어 단위 DTW 정렬을 사용해 실제 영어 내레이션에 자막 경계 동기화
- 음성이 주 영상에 든 장면은 primary 시계, 별도 음성 영상에 든 장면은 secondary 시계를 사용해 장면 로딩 시간에 따른 약 0.5초 선행 수정
- 흰색 글자와 검은 테두리의 2배 자막을 사용하고, 자막 활성 중 영상 하단의 선행 갱신만 억제해 반복 깜빡임 제거
- 자막 종료·영상 건너뛰기·장면 재진입에서 원본 화면 갱신으로 안전하게 복귀하도록 generation gate 추가
- 공개 beta.4·beta.5·beta.6 설치본에서 beta.7 `INSTALL.cmd` 직접 업그레이드 지원
- beta.6 공개 manifest(33,107바이트, `32E731...`)를 배포 ZIP에 바이트 고정하고 기존 beta.4·beta.5 manifest와 함께 검증

beta.1~beta.3 사용자는 해당 버전을 제거해 GOG 원본을 복구한 뒤 beta.7를 설치해야 합니다.

## v0.9.0-beta.6 — 2026-08-24

- 배포 글꼴을 OFL 1.1의 `NanumGothicCoding Regular` 하나로 고정
- `INSTALL_CUSTOM_FONT.cmd`와 `--choose-font`, `--font-file`, `--font-index` 사용자 글꼴 선택 경로 제거
- 공개 beta.4·beta.5 설치본에서 beta.6 `INSTALL.cmd`로 직접 업그레이드 지원
- 이전 beta.4·beta.5에서 사용자 글꼴을 사용했더라도 별도 재선택 없이 나눔고딕코딩으로 자동 전환
- 공개 beta.4 manifest(31,988바이트, `D623C6...`)와 beta.5 manifest(32,845바이트, `A9A402...`)를 배포 ZIP에 바이트 고정하고 descriptor 순서·경로·identity를 fail-closed로 검증
- 모집 창 배경에 남아 있던 `Cost per troop:`을 설치 시 나눔고딕코딩 작은 글리프로 생성하는 `병력당 비용:`으로 복구하고, 지정 ROI 밖의 그림 데이터가 보존되도록 고정 검증
- 업그레이드 실패 시 직전 베타 상태로 롤백하고, beta.6 제거 시 최초 GOG 원본을 복원하는 계약 유지

beta.1~beta.3 사용자는 해당 버전을 제거해 GOG 원본을 복구한 뒤 beta.6를 설치해야 합니다.

## v0.9.0-beta.5 — 2026-08-24

- 저해상도 DOS 화면에 맞는 `NanumGothicCoding Regular`(OFL 1.1)를 새 기본 글꼴로 채택
- 렌더러를 `pillow-freetype-monochrome-v2-fixed-baseline`으로 교체해 beta.4에서 한글 높이가 들쭉날쭉하던 회귀 수정
- 일반 글꼴은 13x14 셀·advance 13, 작은 글꼴은 11x12 셀·advance 11로 고정하고 각 face의 모든 한글을 공통 ink-bottom 기준선 14/12에 정렬
- face 전체에 적용되는 가장 큰 정수 픽셀 크기를 한 번만 선택해 전경을 셀 안에 맞추고, 글자별 확대·축소 없이 tight crop의 `offset_y`를 보존
- 전경 잘림은 0으로 검증하고 셀 경계의 1픽셀 그림자만 제한적으로 자르도록 계약화
- `HEROWIND.BIN`의 10바이트 `Knowledge` 슬롯을 `지력`으로 결정론적으로 교정하고, `HEROES2.AGG`의 폰트 없는 기반에 유지하는 번역 BIN을 8개로 확대
- 공개 beta.4 기본 글꼴 설치본에서 `INSTALL.cmd`를 실행하면 바로 beta.5로 업그레이드할 수 있도록 추가
- beta.4 사용자 글꼴 설치본은 원본 글꼴 경로를 저장하지 않으므로 `INSTALL_CUSTOM_FONT.cmd`에서 사용할 글꼴을 다시 선택해 바로 업그레이드하도록 추가
- 동봉한 고정 beta.4 manifest와 기존 receipt를 검증하고, 업그레이드 실패 시 beta.4 상태로 롤백하며 beta.5 제거 시 최초 GOG 원본을 복원하도록 함

beta.1~beta.3 사용자는 해당 버전의 `UNINSTALL.cmd`로 GOG 원본을 복구한 뒤 beta.5를 설치해야 합니다.

## v0.9.0-beta.4 — 2026-08-24

- 배포 가능한 나눔명조 Regular(OFL 1.1)를 기본 글꼴로 변경
- 설치 시 874자 매핑을 일반·작은 글꼴로 생성하고 두 AGG의 `FONT.ICN`, `SMALFONT.ICN`을 동적으로 재구성하도록 변경
- `INSTALL_CUSTOM_FONT.cmd`, `--choose-font`, `--font-file`, `--font-index`로 로컬 TTF·OTF·TTC·OTC를 직접 선택할 수 있도록 함
- 설치기가 글꼴 이름이나 라이선스로 사용자 선택을 제한하지 않도록 하고, 선택 파일은 복사·수집·업로드·배포하지 않도록 함
- 선택 글꼴에 없는 매핑 글자는 동봉한 나눔명조로 자동 보완하고 양쪽 글꼴에 모두 없으면 변경 전에 중단
- ICN 배열을 기존 96개 + 원본 sprite 0을 복제한 filler 160개 + 생성 글리프 874개 = 총 1,130개로 고정하고 기존 `@` 인덱스 32를 투명 글리프로 처리
- manifest를 `homm2-korean-release-manifest-v2`로 올리고 48개 고정 BSDIFF40 + 2개 동적 AGG + `KOREAN.BIN` 복사 방식으로 변경
- `HEROES2.AGG`의 폰트 없는 기반에는 당시 번역된 BIN 7개만 유지하고 `HEROES2X.AGG` 기반은 원본 그대로 사용
- beta.3의 바탕체 고정 래스터와 시험적으로 번역한 이미지 UI ICN 4개를 beta.4 배포 기반에서 제거
- 사용자 글꼴에 따라 달라지는 두 AGG의 실제 설치 해시와 글꼴 메타데이터를 로컬 receipt에 기록
- 런타임 글리프 생성을 위해 Pillow 12.0.0과 해당 라이선스 고지를 추가

기존 beta.1~beta.3 사용자는 이전 버전을 제거해 GOG 원본을 복구한 뒤 beta.4를 설치해야 합니다. 설치 후 글꼴을 바꿀 때도 제거 후 재설치가 필요합니다.

## v0.9.0-beta.3 — 2026-08-23

- H2K3 외부 문자열 은행을 첫 문자열 출력 때가 아니라 게임 본체 진입 전에 불러오도록 변경
- Object2 선호 주소를 실행 주소로 잘못 사용하던 155개 descriptor와 로더 허용 범위를 실제 재배치 주소로 교정해 은행 전체가 취소되던 문제 수정
- 대상 주문 메시지 재배치 누락을 고쳐 `영웅: 대상에게 주문 시전.` 형식을 안정화
- 중립 부대 합류 문장을 `%s 중 일부가 … 합류하려 합니다.`로 교정하고 외부 은행과 EXE 예비 문구 양쪽에 수록

## v0.9.0-beta.2 — 2026-08-23

`v0.9.0-beta.1`을 대체하는 정리 배포판입니다. 게임 패치 내용은 beta.1과 같고 저장소·설치 경로 처리를 정리했습니다.

- 내부 분석·시험 작업 아카이브를 저장소와 Git 기록에서 제외
- 최종 번역표·매핑·필수 도구만 공개용 디렉터리로 재구성
- GOG Galaxy 기본 경로 `C:\Program Files (x86)\GOG Galaxy\Games\HoMM 2 Gold` 자동 탐지 추가
- 설치·검증·제거·강제 종료 복구 동작 재검증

## v0.9.0-beta.1 — 2026-08-23

저장소 패키징 범위 문제로 철회되었습니다. 한국어 패치 내용은 beta.2에 그대로 포함됩니다.

- 오리지널·확장 캠페인 맵 47개 번역
- 주요 비이미지 인터페이스와 H2K3 외부 문자열 은행 적용
- 캠페인 전환 정지 수정
- 전투 로그를 `공격: 피해 N`, `손실: N`으로 정리
- 대상 주문을 `영웅: 대상에게 주문 시전.` 어순으로 수정
- `air elementals` 직접 폴백을 `공기정령`으로 수정

알려진 제한:

- 그림에 포함된 영문 버튼과 제목은 아직 번역하지 않음
- 일반 MP2/MX2 지도는 번역 범위에서 제외
- `2000 금`처럼 공용 자원 조합 형식은 파급 분석 전까지 유지

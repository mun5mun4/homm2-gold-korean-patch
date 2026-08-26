# Heroes of Might and Magic II Gold 한국어 패치

Heroes of Might and Magic II Gold GOG DOS 영문판을 위한 비공식 한국어 패치입니다.

## 배포 상태

- 현재 배포 기준은 `v0.9.0-beta.7`입니다.
- beta.7는 오프닝과 캠페인 영상 51편에 57개 장면·388개 한국어 자막을 추가하고 음성 파일 기준으로 싱크를 맞춥니다.
- 공개 beta.4·beta.5·beta.6 설치본은 beta.7로 직접 업그레이드할 수 있습니다.

배포판은 게임 실행 파일이나 원작 리소스 전체를 포함하지 않고, 사용자가 보유한 정확한 GOG 원본에 바이너리 델타를 적용합니다.

## beta.7 설치와 업그레이드

깨끗한 GOG 원본이나 공개 beta.4·beta.5·beta.6 설치본에서 beta.7 ZIP의 `INSTALL.cmd`를 실행합니다. 이전 버전에서 어떤 글꼴을 사용했든 beta.7는 동봉한 나눔고딕코딩으로 글리프를 다시 생성하므로 지원되는 이전 버전을 먼저 제거할 필요가 없습니다.

beta.1~beta.3은 직접 업그레이드 대상이 아닙니다. 해당 버전 배포 폴더의 `UNINSTALL.cmd`로 GOG 원본을 복구한 뒤 beta.7를 설치하세요. 이전 배포 폴더가 없다면 같은 버전 ZIP을 다시 받아 제거할 수 있습니다.

1. GOG Galaxy, Heroes II, DOSBox를 모두 종료합니다.
2. GitHub Releases에서 `homm2-ko-v0.9.0-beta.7-win-gog.zip`을 받습니다.
3. ZIP을 모두 푼 뒤 `INSTALL.cmd`를 실행합니다.

기본 설치 경로는 다음과 같습니다.

```text
C:\Program Files (x86)\GOG Galaxy\Games\HoMM 2 Gold
```

설치기가 자동으로 찾지 못하면 다음처럼 직접 지정할 수 있습니다.

```text
homm2-ko-patcher.exe install --game-dir "C:\Program Files (x86)\GOG Galaxy\Games\HoMM 2 Gold"
```

지원 대상은 GOG gameId `1207658785`, buildId `52745329670822422`, English 설치본입니다.

## beta.7 글꼴 방식

beta.7는 SIL Open Font License 1.1의 `NanumGothicCoding Regular`에서 설치 시점에 874자 한글 글리프를 생성합니다. 배포 ZIP에 들어가는 글꼴과 설치기가 사용하는 글꼴은 이 파일 하나뿐이며, 사용자 글꼴 선택 명령이나 별도 설치 스크립트는 제공하지 않습니다.

렌더러 v2는 일반 글꼴을 13x14 셀·advance 13, 작은 글꼴을 11x12 셀·advance 11로 고정합니다. 한 face의 모든 한글은 공통 ink-bottom 기준선 14/12를 사용하고, 셀에 맞는 가장 큰 정수 픽셀 크기를 face 전체에 한 번만 적용합니다. 글자마다 따로 확대·축소하지 않으며 tight crop의 논리 위치를 보존해 beta.4에서 높이가 들쭉날쭉하던 문제를 없앴습니다.

폰트 없는 `HEROES2.AGG` 기반에는 번역 BIN 8개를 유지합니다. `HEROWIND.BIN`은 고정 10바이트 `Knowledge` 슬롯만 `지력`으로 교정합니다. 시험적으로 번역했던 이미지 ICN 4개는 원본 영어 이미지로 유지합니다. 다만 모집 창의 `Cost per troop:` 한 곳은 설치 시 생성한 작은 글꼴로 `병력당 비용:`을 그려 넣습니다. 정확한 ICN 배열과 AGG 생성 방식은 [동적 폰트 설계](docs/DYNAMIC_FONT_KO.md)에 설명했습니다.

직접 업그레이드는 동봉한 고정 beta.4·beta.5·beta.6 manifest와 기존 receipt를 모두 검증합니다. 중간에 실패하면 업그레이드 직전 버전으로 롤백하고, 업그레이드된 beta.7를 제거하면 이전 베타가 아니라 최초 GOG 원본을 복원합니다.

## 번역 범위

- 오리지널·확장 캠페인 맵 47개
- 영웅·성·전투·주문·아티팩트·모험 지도의 주요 비이미지 UI
- 확장 한글 폰트와 H2K3 외부 문자열 은행 `KOREAN.BIN`
- 피해·부분 손실·대상 주문 등 전투 로그 후속 교정
- 오프닝·캠페인 영상 51편의 흰색/검은 테두리 한국어 자막 388개

일반 MP2/MX2 지도와 그림에 박힌 버튼·제목은 이번 베타 범위에서 제외했습니다. 원본 SMK 영상 파일은 수정하지 않습니다.

## 저장소 구조

```text
.
├─ tools/release/             델타 빌더, 동적 폰트 빌더와 트랜잭션 설치기
├─ tools/localization/        최종 교정·캠페인·H2K3·영상 자막 빌드 도구
├─ translations/             선별된 번역 원장, 874자 글리프 매핑과 자막 큐
├─ packaging/release_assets/ ZIP에 포함되는 문서·스크립트·기본 나눔고딕코딩
├─ tests/                     공개 소스 단위 검사
└─ docs/                      설계 문서와 공개판 활성 파일 해시
```

내부 분석 로그, DOSBox 제어 실험, 캡처, 후보·복구 산출물은 저장소에 포함하지 않습니다. 배포 재포장 방법은 [BUILD_KO.md](BUILD_KO.md), 소스 범위는 [docs/SOURCE_LAYOUT_KO.md](docs/SOURCE_LAYOUT_KO.md), 영상 자막 재현 방법은 [docs/VIDEO_SUBTITLES_KO.md](docs/VIDEO_SUBTITLES_KO.md)에 설명했습니다.

`docs/ACTIVE_FILE_HASHES.json`은 beta.3 번역 기반을 고정한 기존 source pin입니다. beta.7의 실행 파일·자막 은행 결과는 새 release manifest에서 별도로 고정하며, 설치 시 생성된 두 AGG의 실제 해시는 로컬 receipt에 기록합니다.

## 원작 파일 미포함

저장소와 배포 ZIP에는 완성된 `HEROES2.EXE`, AGG, 캠페인 맵, 세이브, 캡처, GOG·DOSBox 파일을 넣지 않습니다. 완성 AGG나 미리 생성한 한글 래스터 대신 정확한 지원 원본 없이는 사용할 수 없는 델타, 프로젝트 파일, 874자 매핑과 기본 나눔고딕코딩을 사용합니다.

## 라이선스

프로젝트 소스와 번역 데이터는 `GPL-2.0-only`로 배포됩니다. 기본 `NanumGothicCoding Regular`는 SIL Open Font License 1.1을 따릅니다. `munument1/-KR-fheroes2`의 한국어 번역을 참고·수정한 범위와 제3자 도구는 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)에 기록했습니다.

원작 게임과 상표의 권리는 각 권리자에게 있으며, 이 프로젝트는 비공식 팬 패치입니다.

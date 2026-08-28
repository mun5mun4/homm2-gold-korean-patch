# 공개 소스 구성

이 저장소는 배포에 필요한 코드와 선별된 번역 소스만 제공합니다. 내부 분석 로그, DOSBox 자동 제어, 캡처, 일회성 승격·복구 스크립트와 후보 파일은 포함하지 않습니다.

아래 항목은 `v0.9.0-beta.10`의 영상 자막, 기본·사용자 선택 동적 폰트와 공개 beta.4·beta.5·beta.6·beta.7·beta.8·beta.9 직접 업그레이드 구성을 설명합니다.

## 배포 도구

- `tools/release/homm2_ko_patcher.py`: 기본·사용자 글꼴 선택, 설치·검증·복구·제거
- `tools/release/homm2_font.py`: 874자 매핑과 선택·대체 face 검사, Pillow 기반 글리프·버튼 생성, ICN·AGG 보존형 재구성
- `tools/release/build_release.py`: 검증된 원본과 활성 패치 트리에서 manifest v2 배포 디렉터리 생성
- `tools/release/package_release.py`: 재현 가능한 ZIP과 독립 해시 manifest 생성
- `tools/release/gog_original_file_hashes.json`: 지원 GOG 원본 50개 해시

## 현지화 소스

- `translations/campaign/`: 캠페인 번역 원장과 fheroes2 provenance
- `translations/interface/`: 이름·설명·주문·기술 등 선별된 번역표
- `translations/font/`: 캠페인 861자 기준 매핑과 최종 874자 매핑
- `translations/subtitles/scene_cues_ko.tsv`: 51개 영상, 57개 장면의 최종 한국어 자막 388개와 표시 시각
- `tools/localization/h2c_rebuilder.py`: H2C 컨테이너 보존형 재구성 도구
- `tools/localization/h2k3_bank.py`: H2K3 외부 문자열 은행 형식과 검증 모델
- `tools/localization/h2_video_subtitles.py`: 공개 beta.6 EXE/BIN에서 KSX2 큐·dual-ms 시계·2배 외곽선 렌더러·화면 갱신 클리퍼와 load-base 독립 중계 코드를 포함한 beta.10 EXE/BIN을 재현하고 검증하는 고정 해시 변환
- `tools/localization/final_text_hotfix.py`: 고정된 pre-beta.2 누적 EXE에서 beta.2 문구와 주문 재배치·공기정령/합류 폴백·H2K3 본체 진입 전 호출·실주소 허용 범위를 함께 재현하는 고정 해시 변환
- `tools/localization/final_bank_hotfix.py`: 고정된 beta.2 외부 문자열 은행에서 합류 문장을 교정하고 Object2 기반 일반 descriptor 155개를 실기 재배치 주소로 바꾸는 고정 해시 변환

## beta.10 글꼴·라이선스·업그레이드 자산

- `packaging/release_assets/fonts/IropkeBatangM.ttf`: 기본 글꼴 Iropke Batang Medium(OFL 1.1)
- `packaging/release_assets/fonts/NanumGothicCoding-Regular.ttf`: 매핑 누락 문자를 위한 보완 글꼴 NanumGothicCoding Regular(OFL 1.1)
- `packaging/release_assets/THIRD_PARTY_LICENSES/IROPKE_BATANG_OFL.txt`: 이롭게 바탕체 라이선스와 Reserved Font Name 고지
- `packaging/release_assets/THIRD_PARTY_LICENSES/NANUM_GOTHIC_CODING_OFL.txt`: 나눔고딕코딩 라이선스와 Reserved Font Name 고지
- `packaging/release_assets/THIRD_PARTY_LICENSES/PILLOW_LICENSE.txt`: Pillow/PIL 고지
- `packaging/release_assets/upgrades/v0.9.0-beta.4-manifest.json`: 공개 beta.4 직접 업그레이드 검증용 고정 manifest
- `packaging/release_assets/upgrades/v0.9.0-beta.5-manifest.json`: 공개 beta.5 직접 업그레이드 검증용 고정 manifest
- `packaging/release_assets/upgrades/v0.9.0-beta.6-manifest.json`: 공개 beta.6 직접 업그레이드 검증용 고정 manifest
- `packaging/release_assets/upgrades/v0.9.0-beta.7-manifest.json`: 공개 beta.7 직접 업그레이드 검증용 고정 manifest
- `packaging/release_assets/upgrades/v0.9.0-beta.8-manifest.json`: 공개 beta.8 직접 업그레이드 검증용 고정 manifest
- `packaging/release_assets/upgrades/v0.9.0-beta.9-manifest.json`: 공개 beta.9 직접 업그레이드 검증용 고정 manifest

`packaging/release_assets/INSTALL_CUSTOM_FONT.cmd`와 설치기의 `--choose-font`, `--font-file`, `--font-index`는 사용자가 보유한 로컬 TTF·OTF·TTC·OTC를 설치 시 선택하는 진입점입니다. 선택 파일은 저장소·배포 자산이나 게임 폴더에 복사하지 않습니다. 배포 ZIP에는 기본 이롭게 바탕체와 보완 나눔고딕코딩만 포함합니다.

`Iropke Batang Medium`은 v3 bearing, 874자와 전경 잘림 0을 확인한 기본 글꼴입니다. 원본 TTF와 OFL 1.1은 포함하지만 후보 AGG와 미리 생성한 래스터는 공개 소스나 배포 자산에 포함하지 않습니다.

## beta.10 재포장 범위

`build_release.py`는 GOG 원본 50개를 검증한 뒤 다음 51개 설치 행을 만듭니다.

- 고정 BSDIFF40 48개: EXE 1개와 캠페인 47개
- 동적 폰트 AGG 2개: `DATA/HEROES2.AGG`, `DATA/HEROES2X.AGG`
- 복사 프로젝트 파일 1개: `KOREAN.BIN`

`HEROES2.AGG`의 폰트 없는 기반은 번역된 BIN 8개(`HEROWIND.BIN` 포함)만 원본과 다르고, `HEROES2X.AGG` 기반은 원본과 같습니다. `HEROWIND.BIN`의 고정 `Knowledge` 슬롯은 `지력`으로 결정론 교정합니다. beta.3의 고정 바탕체 글리프와 미리 완성한 이미지 UI 래스터는 기반에서 제거합니다. 설치 시 일반·작은 글꼴 ICN 2종과 한글 버튼 글씨를 선택 글꼴로 생성하고, 메인 메뉴 배경·장식과 비대상 영역은 원본을 보존합니다. 오리지널 `HEROES2.AGG`의 순정 `RECRBKG.ICN:0`에는 같은 작은 글꼴로 `병력당 비용:`을 생성합니다.

저장소만으로 GOG 원본에서 모든 역사적 한글화 단계를 다시 개발·생성하는 통합 빌더는 아닙니다. 검증된 활성 번역 트리를 공개 배포 형식으로 재포장하며, 설치기가 원본·패키지·고정 target 또는 동적 AGG 구조와 receipt를 검사합니다.

## 해시 문서의 범위

`docs/ACTIVE_FILE_HASHES.json`은 beta.3 번역 기반을 고정하는 기존 source pin입니다. beta.4~beta.10 배포 결과 pin이 아니므로 파일 자체는 변경하지 않습니다. beta.10의 EXE/BIN은 release manifest가 고정하고, 설치 시 생성된 AGG 해시는 각 설치의 `_homm2_ko_install/receipt.json`에 기록합니다.

세부 재포장 절차는 `BUILD_KO.md`, 영상 자막 재현은 `docs/VIDEO_SUBTITLES_KO.md`, 매핑은 `docs/FONT_MAPPINGS_KO.md`, 동적 ICN·AGG 계약은 `docs/DYNAMIC_FONT_KO.md`를 확인하세요.

# beta.14 배포판 재포장

검증된 GOG 원본과 최신 한국어 패치 트리에서 `v0.9.0-beta.14`을 만듭니다. beta.13의 한글 메인 메뉴와 기존 버튼 정렬·영상 자막을 유지하며, v4 렌더러로 이롭게 바탕체의 아래로 처진 글자를 보정합니다. 공개 beta.4~beta.13에서 직접 업그레이드할 수 있습니다.

## 입력과 의존성

- Python 3.13, `bsdiff4` 1.2.6, Pillow 12.0.0
- Windows 설치기를 다시 만들 경우 PyInstaller 6.15.0
- 수정되지 않은 지원 GOG 영문판: gameId `1207658785`, buildId `52745329670822422`
- beta.12의 중앙 정렬과 기존 번역·자막이 반영된 검증된 활성 한국어 패치 트리

```text
python -m pip install -r requirements-build.txt
```

`docs/ACTIVE_FILE_HASHES.json`은 beta.3 번역 기반의 역사적 source pin입니다. 현재 결과 목록으로 바꾸지 않습니다. beta.10에서 승인된 다음 EXE·은행을 beta.14에서도 사용합니다.

| 파일 | 크기 | SHA-256 |
|---|---:|---|
| `HEROES2.EXE` | 1,523,420 | `87B175EF0698C65893BAF6A0581E74BEA60CCECA0D8DF57E9DF7614B27DB2365` |
| `KOREAN.BIN` | 36,159 | `37FDC1F372627E7B637EEEBFC15610E26B427E66947D7AA699B46B807F7338DA` |

자막 EXE·은행 재현은 [영상 자막 설계](docs/VIDEO_SUBTITLES_KO.md), 글꼴·버튼 계약은 [동적 폰트 설계](docs/DYNAMIC_FONT_KO.md)를 따릅니다. 원본 게임 파일·완성 패치 트리·검토 캡처는 저장소에 넣지 않습니다.

## 메인 메뉴와 AGG 기반

`translations/interface/main_menu/`의 BSDIFF40 3개와 `identities.json`을 사용합니다. 빌더는 원본·델타·복원 결과의 해시, 20개 상태의 위치·크기·투명도·편집 영역 밖 픽셀·순환 팔레트 배제와 배경의 일치를 검사합니다. 입력 트리의 메뉴가 정확한 순정 또는 승인 결과일 때만 진행합니다.

| 대상 | 설치 시 글꼴을 넣기 전 AGG 기반 |
|---|---|
| `DATA/HEROES2.AGG` | GOG 원본 + 번역 BIN 8개 + 승인된 `BTNSHNGL.ICN`·`HEROES.ICN` |
| `DATA/HEROES2X.AGG` | GOG 원본 + 승인된 확장 `HEROES.ICN` |

BIN 8개는 `HEROWIND.BIN`, `THIEFWIN.BIN`, `WELLWIND.BIN`, `RECRUIT0.BIN`, `RECRUIT1.BIN`, `RECRUIQ0.BIN`, `RECRUIQ1.BIN`, `TRADPOST.BIN`입니다. `HEROWIND.BIN`의 고정 10바이트 `Knowledge` 슬롯은 `지력`으로 교정합니다. 다른 캠페인 배경은 원본을 유지합니다.

이 기반을 기존 `bsdiff40_font_agg_v1` 두 행에 담습니다. 설치 시 `FONT.ICN`·`SMALFONT.ICN`, 일반 버튼과 `병력당 비용:`은 선택 글꼴에서 생성하며 메인 메뉴는 그대로 보존합니다. ZIP에 새 메뉴 PNG·ICN·AGG를 추가하지 않습니다.

기본 이롭게 바탕체의 기대 결과는 공개 beta.13의 동일한 폰트 없는 기반과 v4 렌더러로 계산하고, 로컬 게임 및 검토 패키지에서 일치를 확인했습니다.

| 파일 | 크기 | SHA-256 |
|---|---:|---|
| `DATA/HEROES2.AGG` | 44,704,652 | `8FA1B61D8DB2EA01836775D4FA0A143B21F6C3550CC3EA06B01559B2A58CCC7F` |
| `DATA/HEROES2X.AGG` | 3,003,781 | `F38620A361531726941A5414E0009AA13CD492F6AEC973B5AA392030FF4000C0` |

사용자 글꼴 AGG에 이 해시를 강제하지 않고 실제 결과를 receipt에 기록합니다. 사용자 글꼴에서도 메인 메뉴 3개 payload는 같아야 합니다.

## 설치기 실행 파일

```text
pyinstaller --noconfirm --clean --onefile ^
  --name homm2-ko-patcher ^
  --paths tools/release ^
  tools/release/homm2_ko_patcher.py
```

beta.14는 v4 글꼴 모듈과 과거 v3 설치 기록 호환성을 포함한 새 설치기 EXE가 필요합니다. 같은 소스·의존성으로 생성해 이미 검증한 높이 보정 검토본 EXE를 재사용할 수 있으며, 최종 배포 디렉터리의 EXE로 공개 beta.13 업그레이드·검증·제거를 검사합니다.

## 배포 디렉터리 생성

```text
python tools/release/build_release.py ^
  --original-root "C:\path\to\clean-gog" ^
  --patched-root "C:\path\to\approved-beta12-tree" ^
  --patcher-exe "dist\homm2-ko-patcher.exe" ^
  --output "release_output\homm2-ko-v0.9.0-beta.14" ^
  --version "v0.9.0-beta.14"
```

출력 폴더는 미리 존재하면 안 됩니다. 지원 원본 50개를 고정 해시로 검사한 뒤 고정 BSDIFF40 48개(EXE·캠페인), 메인 메뉴를 포함한 동적 AGG 기반 델타 2개, `KOREAN.BIN` 1개로 51개 설치 행을 만듭니다. 874자 매핑·OFL 글꼴 2개·설치 도구·고정 업그레이드 manifest 10개와 manifest v2를 함께 포함합니다.

beta.13 업그레이드 manifest는 공개 자산과 같은 35,396바이트·SHA-256 `94646DA92062ECD4CC73BD9EF9EE52D99BFF7584BCEF1E52BC46143EE41AE150`입니다. 기존 beta.4~beta.12 pin은 바꾸지 않습니다.

## GitHub 자산 생성

```text
python tools/release/package_release.py ^
  --release-dir "release_output\homm2-ko-v0.9.0-beta.14" ^
  --output-dir "release_output\github-assets-v0.9.0-beta.14" ^
  --version "v0.9.0-beta.14"
```

정렬된 항목과 고정 ZIP 시간 `2026-09-08 00:00:00`으로 설치 ZIP, 독립 manifest, `SHA256SUMS.txt`를 만듭니다. 모든 항목을 대조하며 허용하지 않은 파일을 거부합니다. 글꼴 allowlist는 `IropkeBatangM.ttf`와 `NanumGothicCoding-Regular.ttf`입니다.

## 검증

```text
python -m unittest discover -s tests -v
git diff --check
```

1. 메뉴 3개 payload와 설치 결과의 일치 및 beta.13의 글꼴 보정 대상 밖 AGG 리소스·EXE·은행·캠페인 보존을 검사합니다.
2. 원본 배경·장식과 20개 상태에서 순환 팔레트 배제를 검사합니다. 최종 메뉴 모습은 사용자 게임 확인을 거쳤습니다.
3. 새 GOG fixture에서 기본·사용자 글꼴 설치·검증·제거를 수행합니다. 기본 설치는 51개 기대 파일과 같아야 합니다.
4. 공개 beta.13을 먼저 실제 설치한 fixture에서 기본·사용자 글꼴 업그레이드·검증·제거를 수행합니다.
5. 업그레이드의 두 번째 AGG 교체 실패를 주입해 이전 51개 파일·receipt 복원과 재시도를 검사합니다.
6. beta.4~beta.13 manifest·receipt 호환성, 잘못된 입력 거부, 일반 버튼 중앙 정렬은 소스 회귀검사를 유지합니다.
7. 제거 시 최초 GOG 원본 50개 복원과 개인 저장 파일 sentinel 보존을 확인합니다.

실제 게임 실행과 설치 검사는 별개입니다. 격리 fixture에서 설치기를 실행하며 사용자의 본 게임 디렉터리를 검사 대상으로 사용하지 않습니다.

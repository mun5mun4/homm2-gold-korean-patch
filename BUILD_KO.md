# beta.9 배포판 재포장

이 문서는 검증된 GOG 원본 트리와 현재 활성 한국어 패치 트리에서 `v0.9.0-beta.9` 패키지를 만드는 절차입니다. 공개 beta.4·beta.5·beta.6·beta.7·beta.8을 직접 업그레이드 입력으로 지원합니다.

beta.9은 48개 고정 BSDIFF40 결과와 설치 시 선택 글꼴로 생성하는 2개 AGG를 manifest v2로 묶고, 직접 업그레이드 검증용으로 공개 beta.4·beta.5·beta.6·beta.7·beta.8 manifest를 고정해 포함합니다. 완성 AGG와 미리 생성한 한글 래스터는 배포하지 않습니다. 배포 ZIP에는 기본 이롭게 바탕체, 보완 나눔고딕코딩과 로컬 파일 선택 진입점을 포함합니다.

## 준비물

- Python 3.13
- `bsdiff4` 1.2.6
- Pillow 12.0.0
- Windows 실행 파일을 다시 만들 경우 PyInstaller 6.15.0
- 수정되지 않은 지원 GOG 영문판
- beta.3 번역 기반에 검증된 beta.7 영상 자막 EXE/BIN과 beta.9 동적 UI 입력을 적용한 활성 패치 트리

빌드 의존성은 다음 명령으로 설치할 수 있습니다.

```text
python -m pip install -r requirements-build.txt
```

원본 게임 파일과 완성 패치 파일은 저장소에 포함되지 않습니다.

## beta.3 활성 pin의 역할

`docs/ACTIVE_FILE_HASHES.json`은 `v0.9.0-beta.3` 번역 기반을 고정한 기존 source pin입니다. beta.9은 이 기반의 캠페인·AGG 현지화에 beta.7에서 검증된 영상 자막 EXE/BIN과 동적 UI 계약을 적용합니다.

이 파일은 beta.4~beta.9 출력 해시 목록이 아니므로 `ACTIVE_FILE_HASHES.json` 자체를 갱신하지 않습니다. beta.9의 최종 EXE/BIN은 release manifest가 고정하며, 설치 시 생성된 두 AGG의 실제 해시는 사용자 PC의 receipt가 보존합니다.

## beta.3 활성 입력의 필수 후단 교정

활성 패치 트리를 다시 만들 때는 앞 단계의 한글화 EXE와 은행을 그대로 쓰지 말고 다음 두 고정 해시 변환을 마지막에 실행합니다.

```text
python tools/localization/final_text_hotfix.py apply ^
  --source "C:\path\to\pinned-5AE509-exe\HEROES2.EXE" ^
  --output "C:\path\to\empty-hotfix-candidate\HEROES2.EXE"

python tools/localization/final_bank_hotfix.py apply ^
  --source "C:\path\to\beta2-tree\KOREAN.BIN" ^
  --mapping "translations\font\mapping874.fixed-interface-font.txt" ^
  --output "C:\path\to\empty-hotfix-candidate\KOREAN.BIN"
```

출력 파일은 미리 존재하면 안 됩니다. 각 도구의 `verify`를 통과한 후보만 입력 트리로 승격하고 루트와 `cloud_saves/KOREAN.BIN`을 동일하게 맞춥니다. EXE와 은행의 활성 pin은 `docs/ACTIVE_FILE_HASHES.json`과 일치해야 합니다.

이 입력은 게임 본체 진입 직전 H2K3를 불러오며, Object2 기반 일반 descriptor 155개와 EXE helper 허용 범위에 실기 재배치 주소 `+0x204000`을 사용합니다. EXE와 은행은 반드시 위 도구로 만든 한 쌍을 사용합니다.

## beta.9 영상 자막 입력 계약

beta.9은 beta.7에서 사용자 수동 시험을 통과한 다음 파일 쌍을 그대로 유지합니다. 재포장에 사용하는 활성 트리도 이 identity와 정확히 일치해야 합니다.

- `HEROES2.EXE`: 1,523,420바이트, SHA-256 `B5416C793354122762B67973ACF86D985C8B5ACA26B74F29FE62E707E7A1548C`
- `KOREAN.BIN`: 36,265바이트, SHA-256 `95EA660215425E34FCB7CFD37405F8D1869845EB2EAED245613D2FF8AAE1D20A`

은행은 57개 장면·388개 KSX2 cue를 포함합니다. 27개 cue는 `primary_ms`, 별도 음성 영상을 쓰는 361개 cue는 `secondary_ms` 시계를 사용합니다. 실행 파일은 자막 활성 중에만 화면 하단의 선행 clean refresh를 억제하며, 영상 generation이 바뀌면 원본 refresh로 복귀합니다. 원본 SMK 파일은 재포장하거나 수정하지 않습니다.

위 EXE/BIN은 공개 beta.6 파일과 `translations/subtitles/scene_cues_ko.tsv`에서 `tools/localization/h2_video_subtitles.py`로 바이트 단위 재현할 수 있습니다. 입력·출력 해시, 빌드·검증 명령과 선택형 통합 검사는 [docs/VIDEO_SUBTITLES_KO.md](docs/VIDEO_SUBTITLES_KO.md)를 확인하세요.

## beta.9 AGG 기반 생성 규칙

빌더는 beta.3 활성 AGG에서 기존 고정 폰트와 시험 이미지 UI를 배포 기반으로 넘기지 않습니다. 대신 `HEROWIND.BIN`의 고정 슬롯 교정을 추가합니다.

| 대상 | beta.9의 폰트 없는 기반 |
|---|---|
| `DATA/HEROES2.AGG` | GOG 원본에 번역된 BIN 8개(`HEROWIND.BIN`, `THIEFWIN.BIN`, `WELLWIND.BIN`, `RECRUIT0.BIN`, `RECRUIT1.BIN`, `RECRUIQ0.BIN`, `RECRUIQ1.BIN`, `TRADPOST.BIN`)만 유지 |
| `DATA/HEROES2X.AGG` | GOG 원본과 동일 |

`HEROWIND.BIN` payload offset 303의 `0A 00` 길이 word는 그대로 두고, offset 305의 10바이트가 정확히 `Knowledge\0`일 때만 `82 D8 82 95 00 00 00 00 00 00`(`지력`)으로 바꿉니다. 이미 교정된 값은 허용하고 그 밖의 값은 빌드를 중단합니다. 나머지 payload와 AGG 엔트리는 바뀌지 않아야 합니다.

beta.3의 고정 바탕체 `FONT.ICN`·`SMALFONT.ICN`과 시험 이미지 UI는 기반에서 제거됩니다. 설치 시 기본 이롭게 바탕체 또는 사용자가 선택한 로컬 글꼴에서 새 `FONT.ICN`·`SMALFONT.ICN`과 한글 버튼 글씨를 생성해 두 AGG에 넣습니다. 선택 글꼴에 없는 매핑 문자는 나눔고딕코딩으로 보완합니다. 메인 메뉴 배경·장식은 원본을 유지하고 선언된 버튼 글씨 ROI만 바꿉니다. 오리지널 `HEROES2.AGG`에서는 순정 `RECRBKG.ICN` identity를 먼저 확인한 뒤 sprite 0의 고정 ROI에 같은 작은 글꼴로 `병력당 비용:`을 생성합니다. 자세한 배열은 [docs/DYNAMIC_FONT_KO.md](docs/DYNAMIC_FONT_KO.md)를 확인하세요.

## 렌더러 v3 고정 계약

- 기본 파일: `fonts/IropkeBatangM.ttf`
- 보완 파일: `fonts/NanumGothicCoding-Regular.ttf`
- 선택 파일: 사용자가 보유한 로컬 TTF·OTF·TTC·OTC; 배포 디렉터리로 복사하지 않음
- 일반 셀 13x14, advance 13
- 작은 셀 11x12, advance 11
- 선택·보완 face의 실제 ink union이 셀에 들어가는 가장 큰 공통 정수 픽셀 크기를 선택하고 글자별 확대·축소는 하지 않음
- 공통 기준선은 `-union_top`, 각 글리프의 셀 위치는 `baseline + glyph.top`으로 계산해 FreeType bearing을 보존함
- tight crop 뒤 논리 셀의 `offset_y`를 보존하며 전경 clip은 0이어야 함
- `(1, 1)` 그림자는 논리 셀 경계에서만 제한적으로 잘릴 수 있음

공개 beta.5·beta.6·beta.7의 렌더러 v2 manifest와 receipt는 직접 업그레이드 확인용 역사 자료로 그대로 고정합니다. 현재 v3 설치 기록과 혼동해 다시 쓰지 않습니다.

기본 `Iropke Batang Medium`은 874자, 공통 기준선과 전경 clip 0을 확인한 원본 파일을 수정하지 않고 배포합니다. 글리프·버튼·AGG는 설치 시 생성하며 미리 만든 래스터는 포함하지 않습니다.

기본 이롭게 바탕체의 SHA-256은 `5910F97BAED6C6E0B8538E40D326B169E0A510357E20DD9003ABABCE2CE1CC69`입니다. 보완 나눔고딕코딩은 Google Fonts commit `90abd17b4f97671435798b6147b698aa9087612f`, SHA-256 `787EFFD7EFED2ABCA88ADE231FAA8191F4E9FCF85B1805A13EE1DC3724B72089`에 고정합니다. 두 글꼴의 OFL 1.1 전문과 Reserved Font Name 고지를 함께 배포합니다.

## 1. 설치기 실행 파일 생성

`homm2_ko_patcher.py`가 같은 디렉터리의 `homm2_font.py`를 가져올 수 있도록 `--paths tools/release`를 지정합니다. Pillow 12.0.0이 설치된 환경에서 실행해야 합니다.

```text
pyinstaller --noconfirm --clean --onefile ^
  --name homm2-ko-patcher ^
  --paths tools/release ^
  tools/release/homm2_ko_patcher.py
```

## 2. beta.9 배포 디렉터리 생성

```text
python tools/release/build_release.py ^
  --original-root "C:\path\to\clean-gog" ^
  --patched-root "C:\path\to\beta9-active-korean-tree" ^
  --patcher-exe "dist\homm2-ko-patcher.exe" ^
  --output "release_output\homm2-ko-v0.9.0-beta.9" ^
  --version "v0.9.0-beta.9"
```

출력 폴더는 미리 존재하면 안 됩니다. 빌더는 GOG 원본 50개를 고정 해시로 확인하고 다음 구성을 만듭니다.

- 고정 BSDIFF40 48개: `HEROES2.EXE` 1개 + 캠페인 맵 47개
- 동적 AGG 행 2개: 원본에서 폰트 없는 기반으로 가는 BSDIFF40과 설치 시 글꼴 ICN·한글 버튼·모집 비용 명패를 재구성하는 계약
- 프로젝트 파일 복사 1개: `KOREAN.BIN`
- 874자 매핑, 기본 `IropkeBatangM.ttf`, 보완 `NanumGothicCoding-Regular.ttf`, `INSTALL_CUSTOM_FONT.cmd`, 동적 폰트 빌더와 두 OFL 1.1 고지
- 공개 beta.4·beta.5·beta.6·beta.7·beta.8의 고정 manifest `upgrades/v0.9.0-beta.4-manifest.json`, `upgrades/v0.9.0-beta.5-manifest.json`, `upgrades/v0.9.0-beta.6-manifest.json`, `upgrades/v0.9.0-beta.7-manifest.json`, `upgrades/v0.9.0-beta.8-manifest.json`
- schema `homm2-korean-release-manifest-v2`의 `manifest.json`

고정 upgrade manifest는 다음 공개 자산과 바이트 단위로 같아야 합니다. 빌더·패키저·설치기 중 어느 단계든 identity가 다르면 중단합니다.

- beta.4: 31,988바이트, SHA-256 `D623C611962CE7F94CC3806DA81B00EDAD7809FB87E489001FE9F0ADF39BAC60`
- beta.5: 32,845바이트, SHA-256 `A9A402E1BD5A8ECD856EABA70BA2F88A828D42F68D37E6F2B82BF7659991B05F`
- beta.6: 33,107바이트, SHA-256 `32E731E43E6D00773867AF89A1BB0C0415099B69359B39C98153CE025279537C`
- beta.7: 33,369바이트, SHA-256 `F71C83895BDC3581F1C8BA4BC7919153E14F0500831D941DAE9B34D17519E2CE`
- beta.8: 33,656바이트, SHA-256 `A6D0DC07FD27ADC73D3925C76CFBC01CBFE7B6727029EACD87A570132E5B5BB5`

설치되는 게임 파일 수는 합계 51개입니다. 정적 49개는 manifest의 고정 target 해시로 검증하고, 설치 시 생성되는 두 AGG는 구조 검증 후 실제 해시를 receipt에 기록합니다.

## 3. GitHub 자산 생성

```text
python tools/release/package_release.py ^
  --release-dir "release_output\homm2-ko-v0.9.0-beta.9" ^
  --output-dir "release_output\github-assets-v0.9.0-beta.9" ^
  --version "v0.9.0-beta.9"
```

이 단계는 고정 ZIP 시간과 정렬된 파일 순서로 ZIP, 독립 manifest와 `SHA256SUMS.txt`를 생성한 뒤 모든 ZIP 항목을 원본 배포 디렉터리와 다시 대조합니다.

## 4. 소스 검사

```text
python -m unittest discover -s tests -v
git diff --check
```

실제 공개 전에는 다음 경로를 각각 격리된 fixture에서 확인합니다.

1. 깨끗한 GOG 원본에서 기본 이롭게 바탕체와 나눔고딕코딩 fallback 설치·검증·제거·재설치
2. 깨끗한 GOG 원본에서 완전·부분 글리프 사용자 글꼴 설치, 나눔고딕코딩 fallback, 버튼·비용 문구의 동일 글꼴 적용, 검증·제거·재설치
3. 공개 beta.4 기본·사용자 글꼴 설치본에서 `INSTALL.cmd`와 `INSTALL_CUSTOM_FONT.cmd` 각각 직접 업그레이드, 실패 주입 시 beta.4 롤백, 제거 시 최초 GOG 원본 복원
4. 공개 beta.5 기본·사용자 글꼴 설치본에서 두 설치 진입점 각각 직접 업그레이드, 실패 주입 시 beta.5 롤백, 제거 시 최초 GOG 원본 복원
5. 공개 beta.6 설치본에서 두 설치 진입점 각각 직접 업그레이드, 실패 주입 시 beta.6 롤백, 제거 시 최초 GOG 원본 복원
6. 공개 beta.7 설치본에서 두 설치 진입점 각각 직접 업그레이드, 실패 주입 시 beta.7 롤백, 제거 시 최초 GOG 원본 복원
7. 공개 beta.8 설치본에서 두 설치 진입점 각각 직접 업그레이드, 실패 주입 시 beta.8 롤백, 제거 시 최초 GOG 원본 복원
8. 오리지널 모집 창의 `Cost per troop:`이 `병력당 비용:`으로 바뀌고 지정 ROI 밖 픽셀·transform과 다른 AGG 엔트리가 보존되는지 확인
9. 메인 메뉴 배경·장식과 비대상 ROI가 원본과 같고 선언된 버튼 글씨만 선택 글꼴로 바뀌는지 확인

beta.1~beta.3 직접 업그레이드는 지원하지 않으며 이전 버전을 제거한 GOG 원본에서 시험합니다. 다섯 upgrade manifest는 크기와 SHA-256이 고정된 공개 beta.4·beta.5·beta.6·beta.7·beta.8 manifest와 정확히 일치해야 합니다. 최종 ZIP의 글꼴 allowlist는 `IropkeBatangM.ttf`와 `NanumGothicCoding-Regular.ttf` 두 파일로 고정합니다. 다른 TTF·OTF·TTC·OTC나 미리 생성한 래스터·AGG를 임의로 추가하면 fail-closed 패키징이 중단되어야 합니다.

이 도구는 번역 개발 전 과정을 GOG 원본부터 반복하는 통합 현지화 빌더가 아니라, 검증된 활성 번역 트리를 beta.9 배포 형식으로 재포장하는 도구입니다.

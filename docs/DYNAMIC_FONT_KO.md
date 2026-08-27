# beta.9 동적 폰트·버튼·모집 비용 명패·업그레이드 설계

이 문서는 `v0.9.0-beta.9`의 설치 시 글리프·버튼·모집 비용 명패 생성과 공개 beta.4·beta.5·beta.6·beta.7·beta.8에서 직접 업그레이드하는 계약을 설명합니다.

## 전환 목적

beta.3까지는 미리 만든 바탕체 비트맵 글리프가 두 AGG 안에 고정돼 있었습니다. beta.4부터 그 고정 래스터를 배포 기반에서 제거하고 설치 시 필요한 874자를 생성합니다.

배포하는 글꼴 파일은 SIL Open Font License 1.1의 `Iropke Batang Medium`과 `NanumGothicCoding Regular`입니다. 기본 설치는 이롭게 바탕체를 사용하고, 없는 매핑 문자는 나눔고딕코딩으로 보완합니다. `INSTALL_CUSTOM_FONT.cmd` 또는 `--font-file`은 사용자가 보유한 로컬 TTF·OTF·TTC·OTC를 설치 시 읽으며 사용자 파일 자체는 복사·수집·업로드·배포하지 않습니다.

beta.4 렌더러 v1은 각 글자를 tight crop한 뒤 모든 `offset_y`를 0으로 잃어버려, 같은 줄의 한글 높이가 들쭉날쭉해 보이는 회귀가 있었습니다. beta.5·beta.6·beta.7의 렌더러 v2는 모든 글리프의 잉크 하단을 셀 바닥에 맞춰 나눔고딕코딩에서는 안정적이었지만, 이롭게 바탕체처럼 글자마다 crop 높이와 bearing이 다른 글꼴에서는 서로 다른 높이에 놓이는 문제가 남았습니다. beta.8 렌더러 v3는 FreeType의 `glyph.top`을 보존하는 typographic 기준선을 사용합니다.

## 생성되는 네 글꼴 ICN

Heroes II Gold는 두 AGG에 각각 일반 글꼴과 작은 글꼴을 보관합니다.

| AGG | 일반 글꼴 | 작은 글꼴 |
|---|---|---|
| `DATA/HEROES2.AGG` | `FONT.ICN` | `SMALFONT.ICN` |
| `DATA/HEROES2X.AGG` | `FONT.ICN` | `SMALFONT.ICN` |

따라서 한 번의 설치에서 총 4개 글꼴 ICN을 재구성합니다. 874자를 일반 요청 크기 14px와 작은 요청 크기 12px로 각각 한 번 렌더링한 뒤 동일한 결과를 두 AGG에 넣습니다. 전경과 `(1, 1)` 1픽셀 그림자는 Heroes II 팔레트 인덱스 10과 21을 사용합니다.

## 모집 비용 명패 한정 생성

오리지널 `DATA/HEROES2.AGG`에는 모집 창 배경 `RECRBKG.ICN`이 있습니다. beta.9 설치기는 먼저 순정 payload가 91,987바이트, SHA-256 `D7B9EF7C819CADACFABF0BCB857976535945DC6F52DC60581D30AC69513E7024`인지 확인합니다. 정확히 일치할 때만 sprite 0의 ROI `(157, 51, 96, 17)`을 같은 행의 안전한 배경으로 지우고, 생성된 `SMALFONT.ICN` 글리프로 `병력당 비용:`을 가운데 배치합니다.

기본 이롭게 바탕체는 원본 TTF 해시와 렌더러 규칙을 고정하고, 생성 결과의 sprite 구조·허용 변경 범위를 검사한 뒤 실제 AGG identity를 receipt에 기록합니다. beta.8의 기본 나눔고딕코딩 결과 payload 102,017바이트와 SHA-256 `F4A2C1B33BDA292E1F4DB06DDE6FF65F1DCF7CA554037FB1011360C6071C505D`는 역사적 고정 identity로 유지합니다. 사용자 글꼴 결과도 글립 모양에 따라 크기와 SHA-256이 달라지므로 같은 구조 검사를 적용하고 실제 identity를 receipt에 기록합니다. 글자 전경은 모집 창 팔레트 인덱스 10, 그림자는 51을 사용합니다. 지정 ROI 밖의 pixel·transform, sprite 1과 다른 AGG 엔트리는 글꼴 모드와 관계없이 디코딩 결과가 원본과 같은지 확인합니다. `HEROES2X.AGG`에는 이 리소스가 없으므로 모집 비용 명패를 만들지 않습니다.

이 처리는 완성된 원작 리소스나 미리 생성한 래스터를 배포하는 방식이 아닙니다. 정확한 GOG 원본, 기본 이롭게 바탕체, 보완 나눔고딕코딩과 필요하면 사용자가 직접 선택한 로컬 글꼴이 있는 PC에서 결정론적으로 생성합니다.

## 한글 버튼 글씨 생성

한글화 대상으로 선언된 버튼 ICN도 완성 래스터를 배포하지 않습니다. 설치기는 순정 버튼 payload와 허용 ROI를 확인하고, 같은 설치에서 만든 일반·작은 글꼴 sprite로 버튼 글씨를 그립니다. 따라서 기본 설치의 버튼은 이롭게 바탕체, 사용자 글꼴 설치의 버튼은 선택 글꼴 모양을 따르며 누락 문자는 같은 fallback 규칙을 사용합니다. 버튼 바탕, 테두리, pressed/released 상태와 허용 ROI 밖 pixel·transform은 글꼴 모드와 관계없이 보존합니다.

장식 메인 메뉴도 원본 배경과 영웅 그림, 버튼 질감·기하를 기반으로 하며 선언된 글씨 mask만 동적으로 바꿉니다. `HEROES.ICN`을 포함한 비대상 영역과 원본 메뉴 구성은 그대로 보존합니다.

## 렌더러 v3 셀·기준선 계약

| 용도 | 논리 셀 | advance | 요청 픽셀 크기 |
|---|---:|---:|---:|
| 일반 | 13x14 | 13 | 14 |
| 작은 글꼴 | 11x12 | 11 | 12 |

렌더러는 선택 글꼴과 보완 글꼴이 실제로 담당하는 모든 글리프를 같은 픽셀 크기로 래스터화합니다. 각 face가 단독으로 맞는지만 보지 않고 양쪽의 실제 ink union을 합쳐 셀에 들어가는 가장 큰 공통 정수 픽셀 크기를 찾습니다. 이 크기는 한 줄 전체에 한 번만 적용하며 글자마다 따로 확대·축소하지 않습니다. 기본 이롭게 바탕체나 사용자 글꼴이 일부 매핑 문자를 지원하지 않으면 그 문자만 나눔고딕코딩 face가 담당하지만 크기와 기준선은 양쪽이 같습니다.

공통 기준선은 `baseline_y = -union_top`으로 정하고, 각 글리프의 셀 좌표는 `offset_y = baseline_y + glyph.top`으로 계산합니다. tight crop의 높이가 다르더라도 FreeType bearing을 버리지 않으므로 `주/조/소`처럼 같은 높이에 있어야 하는 글자가 셀 바닥 때문에 따로 움직이지 않습니다. 전경 clip count는 반드시 0이어야 하며, `(1, 1)` 그림자는 논리 셀 오른쪽·아래 경계에서만 제한적으로 잘릴 수 있습니다. 이 계약과 해석 결과는 manifest 및 설치 receipt의 renderer 메타데이터로 검증합니다.

고정된 공개 beta.5·beta.6·beta.7 manifest와 기존 receipt에는 역사적인 렌더러 v2 계약이 남습니다. 설치기는 이를 직접 업그레이드 입력으로만 해석하며, 현재 v3 receipt와 같은 규칙으로 다시 계산하거나 수정하지 않습니다.

기본 `Iropke Batang Medium`은 일반 글꼴 14px·기준선 12, 작은 글꼴 11px·기준선 10으로 해석됐고 `주/조/소`의 `offset_y`는 모두 1, 874자 전경 clip은 0이었습니다. 원본 TTF와 OFL 1.1은 배포하지만 생성 래스터·AGG는 포함하지 않습니다.

## ICN sprite 배열

각 `FONT.ICN`과 `SMALFONT.ICN`은 정확히 1,130개 sprite를 갖습니다.

| 인덱스 | 개수 | 내용 |
|---|---:|---|
| `0x000`~`0x05F` | 96 | 원본 legacy sprite. 인덱스 32의 `@` 칸만 투명 1×1로 교체 |
| `0x060`~`0x0FF` | 160 | 해당 원본 ICN의 sprite 0을 그대로 복제한 filler |
| `0x100`~`0x469` | 874 | `mapping874.fixed-interface-font.txt` 순서로 설치 시 생성한 글리프 |
| 합계 | 1,130 | 마지막 유효 인덱스 `0x469`, sprite count `0x46A` |

즉 `96 legacy + 160 filler + 874 mapping = 1,130`입니다. filler를 임의의 새 빈 sprite로 만들지 않고 각 원본 글꼴의 sprite 0을 사용합니다. 인덱스 32를 제외한 기존 95개 legacy sprite는 바이트 단위로 보존합니다.

874자 매핑의 인덱스와 2바이트 escape는 이미 EXE, 캠페인 맵과 `KOREAN.BIN`에서 사용 중입니다. 폰트 모양만 바꾸고 매핑 순서는 바꾸지 않으므로 문자열을 다시 인코딩할 필요가 없습니다.

## 폰트 없는 AGG 기반

배포 빌더는 beta.3 활성 AGG를 그대로 델타로 만들지 않습니다. 먼저 고정 바탕체 폰트와 시험 이미지 번역을 제거한 폰트 없는 기반을 만듭니다.

### `DATA/HEROES2.AGG`

GOG 원본을 기준으로 다음 번역 BIN 8개만 유지합니다.

- `HEROWIND.BIN`
- `THIEFWIN.BIN`
- `WELLWIND.BIN`
- `RECRUIT0.BIN`
- `RECRUIT1.BIN`
- `RECRUIQ0.BIN`
- `RECRUIQ1.BIN`
- `TRADPOST.BIN`

`HEROWIND.BIN`은 payload offset 303의 `0A 00` 길이 word를 보존하면서 offset 305의 10바이트 `Knowledge\0`만 `82 D8 82 95 00 00 00 00 00 00`(`지력`)으로 바꿉니다. 이미 교정된 슬롯은 그대로 허용하고 예상 밖의 값이면 배포 빌드를 중단합니다. 이 슬롯 밖 payload와 다른 AGG 엔트리는 변경하지 않습니다.

그 밖의 AGG 기반 리소스는 원본을 사용합니다. 기존 고정 바탕체 `FONT.ICN`, `SMALFONT.ICN`과 미리 완성한 이미지 UI 래스터는 기반에 남기지 않습니다. 설치 결과에서는 글꼴 ICN, 한글화 대상으로 선언된 버튼 ICN과 위에서 설명한 `RECRBKG.ICN:0` 모집 비용 명패만 동적으로 바뀝니다.

### `DATA/HEROES2X.AGG`

폰트 없는 기반은 GOG 원본 `HEROES2X.AGG`와 완전히 같습니다. 설치 단계에서 새 `FONT.ICN`, `SMALFONT.ICN`과 한글화 대상으로 선언된 버튼 글씨를 넣습니다.

이 규칙 때문에 한글화 대상으로 선언하지 않은 이미지 UI는 원본 영어로 보입니다. 이는 의도한 범위 조정이며 문자열 번역 실패가 아닙니다.

## 기본 글꼴과 사용자 글꼴 모드

`INSTALL.cmd`와 옵션 없는 `install` 명령은 배포 ZIP의 `fonts/IropkeBatangM.ttf` face 0을 사용합니다. 설치 전에 매핑, 기본·보완 글꼴 파일, AGG 기반 델타의 크기와 SHA-256을 manifest v2와 대조합니다.

`INSTALL_CUSTOM_FONT.cmd`는 Windows 파일 선택 창을 열고, 명령줄에서는 `install --font-file PATH [--font-index N]`으로 같은 모드를 사용할 수 있습니다. 선택 파일은 즉시 읽어 메모리의 글꼴 계획에 보관하고 배포 폴더나 게임 폴더에 원본 글꼴 파일로 복사하지 않습니다. receipt에는 전체 경로 대신 file name, face index, 크기, SHA-256과 공개 글꼴 메타데이터를 기록합니다. 설치기는 글꼴 이름이나 라이선스로 선택을 막지 않으므로 사용 권한은 사용자가 확인해야 합니다.

기본 이롭게 바탕체 또는 사용자 글꼴의 매핑 누락 문자는 나눔고딕코딩으로 보완합니다. 양쪽 글꼴에 모두 없는 문자가 있거나 face index가 범위를 벗어나면 게임 파일을 바꾸기 전에 중단합니다. 한 번 설치한 뒤 글꼴만 바꾸는 in-place 작업은 지원하지 않으며, 원본을 복구한 뒤 다시 설치합니다.

이롭게 바탕체는 SHA-256 `5910F97BAED6C6E0B8538E40D326B169E0A510357E20DD9003ABABCE2CE1CC69`에 고정합니다. 저작권·Reserved Font Name 고지는 `Copyright (c) 2016, 이롭게(iropke) (www.iropke.com | hello@iropke.com), with Reserved Font Name '이롭게 바탕체', 'iropke batang'.`이며 OFL 1.1 전문은 `THIRD_PARTY_LICENSES/IROPKE_BATANG_OFL.txt`에 들어갑니다. 나눔고딕코딩은 Google Fonts commit `90abd17b4f97671435798b6147b698aa9087612f`, SHA-256 `787EFFD7EFED2ABCA88ADE231FAA8191F4E9FCF85B1805A13EE1DC3724B72089`에 고정하고 `THIRD_PARTY_LICENSES/NANUM_GOTHIC_CODING_OFL.txt`를 함께 배포합니다.

설치기는 나눔고딕코딩 face의 Unicode cmap에 874개 문자가 모두 있는지 검사합니다. 하나라도 없으면 어떤 게임 파일도 교체하기 전에 중단합니다. receipt에는 실제 선택 글꼴과 사용된 fallback의 identity, face·렌더러 메타데이터를 기록합니다.

## manifest와 receipt 검증

beta.9 manifest schema는 `homm2-korean-release-manifest-v2`입니다.

- 48개 파일은 고정 BSDIFF40과 고정 target 해시를 사용합니다.
- 두 AGG는 `bsdiff40_font_agg_v1`으로 폰트 없는 기반을 만든 뒤 네 폰트 ICN과 한글 버튼 글씨를 동적으로 재구성합니다. 오리지널 AGG에서는 순정 identity를 고정한 `RECRBKG.ICN:0`의 모집 비용 명패도 함께 생성합니다.
- `KOREAN.BIN`은 프로젝트 payload로 복사합니다.
- `upgrades/v0.9.0-beta.4-manifest.json`은 공개 beta.4 manifest의 크기 31,988바이트와 SHA-256 `D623C611962CE7F94CC3806DA81B00EDAD7809FB87E489001FE9F0ADF39BAC60`을 고정한 직접 업그레이드 입력입니다.
- `upgrades/v0.9.0-beta.5-manifest.json`은 공개 beta.5 manifest의 크기 32,845바이트와 SHA-256 `A9A402E1BD5A8ECD856EABA70BA2F88A828D42F68D37E6F2B82BF7659991B05F`을 고정한 직접 업그레이드 입력입니다.
- `upgrades/v0.9.0-beta.6-manifest.json`은 공개 beta.6 manifest의 크기 33,107바이트와 SHA-256 `32E731E43E6D00773867AF89A1BB0C0415099B69359B39C98153CE025279537C`를 고정한 직접 업그레이드 입력입니다.
- `upgrades/v0.9.0-beta.7-manifest.json`은 공개 beta.7 manifest의 크기 33,369바이트와 SHA-256 `F71C83895BDC3581F1C8BA4BC7919153E14F0500831D941DAE9B34D17519E2CE`를 고정한 직접 업그레이드 입력입니다.
- `upgrades/v0.9.0-beta.8-manifest.json`은 공개 beta.8 manifest의 크기 33,656바이트와 SHA-256 `A6D0DC07FD27ADC73D3925C76CFBC01CBFE7B6727029EACD87A570132E5B5BB5`를 고정한 직접 업그레이드 입력입니다.
- 전체 설치 파일은 51개입니다.

폰트 없는 AGG 기반의 해시는 manifest에 고정돼 있습니다. 설치기는 기본 이롭게 바탕체와 사용자가 선택한 글꼴로 임시 생성한 AGG의 구조와 변경 리소스 범위를 검사합니다. 기본 이롭게 바탕체는 원본 TTF 해시와 렌더러 규칙을 고정하고, 기본·사용자 글꼴 모드 모두 source identity, sprite 구조, ROI·transform 보존과 허용 변경 리소스 집합을 강제합니다. 최종 두 AGG의 실제 크기와 SHA-256은 두 모드 모두 `_homm2_ko_install/receipt.json`에 기록합니다.

`VERIFY.cmd`는 이 receipt와 현재 파일을 대조합니다. `UNINSTALL.cmd`도 현재 파일이 설치 당시 동적 해시와 같을 때만 백업 원본으로 복구하므로, 사용자가 별도로 수정한 AGG를 덮어쓰지 않습니다.

`docs/ACTIVE_FILE_HASHES.json`은 beta.3 활성 번역 트리의 기존 source pin입니다. beta.4~beta.9 출력 해시 문서가 아니므로 파일 자체를 변경하지 않습니다. 설치 시 생성된 AGG 해시는 이 고정 문서가 아니라 각 설치 receipt의 책임입니다.

## 이전 버전에서 이동

공개 beta.4·beta.5·beta.6·beta.7·beta.8은 beta.9 직접 업그레이드를 지원합니다. 기본 이롭게 바탕체로 만들 때는 `INSTALL.cmd`, 사용자 글꼴로 만들 때는 `INSTALL_CUSTOM_FONT.cmd`를 실행합니다. 이전 receipt는 사용자 글꼴 전체 경로를 저장하지 않으므로 사용자 글꼴 업그레이드에서는 파일을 다시 선택합니다.

업그레이드는 동봉한 고정 beta.4·beta.5·beta.6·beta.7·beta.8 manifest, 이전 receipt와 현재 설치 파일을 검증한 뒤 최초 GOG 원본 백업에서 beta.9 후보를 만듭니다. 실패하면 교체 전 베타 상태로 롤백합니다. 성공한 beta.9의 `UNINSTALL.cmd`는 최초 GOG 원본을 복원합니다.

beta.1~beta.3은 직접 업그레이드를 지원하지 않습니다. 먼저 설치에 사용한 이전 버전의 `UNINSTALL.cmd`로 원본을 복구해야 합니다. 이전 배포 폴더가 없다면 같은 버전 ZIP을 다시 받아 제거할 수 있습니다.

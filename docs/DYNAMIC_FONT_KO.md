# beta.7 동적 폰트·모집 비용 명패·업그레이드 설계

이 문서는 `v0.9.0-beta.7`의 설치 시 글리프·모집 비용 명패 생성과 공개 beta.4·beta.5·beta.6에서 직접 업그레이드하는 계약을 설명합니다.

## 전환 목적

beta.3까지는 미리 만든 바탕체 비트맵 글리프가 두 AGG 안에 고정돼 있었습니다. beta.4부터 그 고정 래스터를 배포 기반에서 제거하고 설치 시 필요한 874자를 생성합니다.

beta.7는 SIL Open Font License 1.1의 `NanumGothicCoding Regular` 하나만 배포하고 사용합니다. 사용자 글꼴 선택 진입점과 관련 명령줄 옵션은 제공하지 않습니다.

beta.4 렌더러 v1은 각 글자를 tight crop한 뒤 모든 `offset_y`를 0으로 잃어버려, 같은 줄의 한글 높이가 들쭉날쭉해 보이는 회귀가 있었습니다. beta.5 렌더러 v2는 face 공통 기준선과 논리 셀 위치를 명시적으로 보존합니다.

## 생성되는 네 글꼴 ICN

Heroes II Gold는 두 AGG에 각각 일반 글꼴과 작은 글꼴을 보관합니다.

| AGG | 일반 글꼴 | 작은 글꼴 |
|---|---|---|
| `DATA/HEROES2.AGG` | `FONT.ICN` | `SMALFONT.ICN` |
| `DATA/HEROES2X.AGG` | `FONT.ICN` | `SMALFONT.ICN` |

따라서 한 번의 설치에서 총 4개 글꼴 ICN을 재구성합니다. 874자를 일반 요청 크기 14px와 작은 요청 크기 12px로 각각 한 번 렌더링한 뒤 동일한 결과를 두 AGG에 넣습니다. 전경과 `(1, 1)` 1픽셀 그림자는 Heroes II 팔레트 인덱스 10과 21을 사용합니다.

## 모집 비용 명패 한정 생성

오리지널 `DATA/HEROES2.AGG`에는 모집 창 배경 `RECRBKG.ICN`이 있습니다. beta.7 설치기는 먼저 순정 payload가 91,987바이트, SHA-256 `D7B9EF7C819CADACFABF0BCB857976535945DC6F52DC60581D30AC69513E7024`인지 확인합니다. 정확히 일치할 때만 sprite 0의 ROI `(157, 51, 96, 17)`을 같은 행의 안전한 배경으로 지우고, 생성된 `SMALFONT.ICN` 글리프로 `병력당 비용:`을 가운데 배치합니다.

결과 payload는 102,017바이트, SHA-256 `F4A2C1B33BDA292E1F4DB06DDE6FF65F1DCF7CA554037FB1011360C6071C505D`로 고정합니다. 글자 전경은 모집 창 팔레트 인덱스 10, 그림자는 51을 사용합니다. 지정 ROI 밖의 pixel·transform, sprite 1과 다른 AGG 엔트리는 디코딩 결과가 원본과 같은지 확인합니다. `HEROES2X.AGG`에는 이 리소스가 없으므로 모집 비용 명패를 만들지 않습니다.

이 처리는 완성된 원작 리소스나 미리 생성한 래스터를 배포하는 방식이 아닙니다. 정확한 GOG 원본과 동봉한 나눔고딕코딩이 모두 있는 사용자 PC에서 결정론적으로 생성합니다.

## 렌더러 v2 셀·기준선 계약

| 용도 | 논리 셀 | advance | face 공통 ink-bottom 기준선 |
|---|---:|---:|---:|
| 일반 | 13x14 | 13 | 14 |
| 작은 글꼴 | 11x12 | 11 | 12 |

렌더러는 동봉한 나눔고딕코딩 face의 해당 한글 전체가 전경 셀에 들어가는 가장 큰 정수 픽셀 크기를 찾습니다. 이 크기는 face 전체에 한 번만 적용하며 글자마다 따로 확대·축소하지 않습니다.

각 글리프는 실제 mask를 tight crop하되 논리 셀 안의 `offset_y`를 유지해 모든 한글의 ink bottom을 같은 기준선에 맞춥니다. 전경 clip count는 반드시 0이어야 하며, `(1, 1)` 그림자는 논리 셀 오른쪽·아래 경계에서만 제한적으로 잘릴 수 있습니다. 이 계약과 해석 결과는 manifest 및 설치 receipt의 renderer 메타데이터로 검증합니다.

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

그 밖의 AGG 기반 리소스는 원본을 사용합니다. 특히 기존 고정 바탕체 `FONT.ICN`, `SMALFONT.ICN`과 시험적으로 수정했던 이미지 UI `SYSTEM.ICN`, `REQUEST.ICN`, `REQUESTS.ICN`, `SYSTEME.ICN`은 beta.7 기반에 남기지 않습니다. 설치 결과에서는 `FONT.ICN`, `SMALFONT.ICN`과 위에서 설명한 `RECRBKG.ICN:0` 모집 비용 명패만 동적으로 바뀝니다.

### `DATA/HEROES2X.AGG`

폰트 없는 기반은 GOG 원본 `HEROES2X.AGG`와 완전히 같습니다. 설치 단계에서만 새 `FONT.ICN`, `SMALFONT.ICN`을 넣습니다.

이 규칙 때문에 이미지에 박힌 일부 UI는 원본 영어로 보입니다. 네 이미지 ICN의 제외는 의도한 범위 조정이며 문자열 번역 실패가 아닙니다.

## 나눔고딕코딩 고정 모드

`INSTALL.cmd`와 `install` 명령은 배포 ZIP의 `fonts/NanumGothicCoding-Regular.ttf` face 0만 사용합니다. 설치 전에 매핑, 글꼴 파일, AGG 기반 델타의 크기와 SHA-256을 manifest v2와 대조합니다.

파일은 Google Fonts commit `90abd17b4f97671435798b6147b698aa9087612f`에 고정했고 SHA-256은 `787EFFD7EFED2ABCA88ADE231FAA8191F4E9FCF85B1805A13EE1DC3724B72089`입니다. Reserved Font Name을 포함한 OFL 1.1 전문은 배포 ZIP의 `THIRD_PARTY_LICENSES/NANUM_GOTHIC_CODING_OFL.txt`에 함께 들어갑니다.

설치기는 나눔고딕코딩 face의 Unicode cmap에 874개 문자가 모두 있는지 검사합니다. 하나라도 없으면 어떤 게임 파일도 교체하기 전에 중단합니다. receipt에는 사용한 나눔고딕코딩 파일 identity와 face·렌더러 메타데이터를 기록합니다.

## manifest와 receipt 검증

beta.7 manifest schema는 `homm2-korean-release-manifest-v2`입니다.

- 48개 파일은 고정 BSDIFF40과 고정 target 해시를 사용합니다.
- 두 AGG는 `bsdiff40_font_agg_v1`으로 폰트 없는 기반을 만든 뒤 네 폰트 ICN을 동적으로 재구성합니다. 오리지널 AGG에서는 순정 identity를 고정한 `RECRBKG.ICN:0`의 모집 비용 명패도 함께 생성합니다.
- `KOREAN.BIN`은 프로젝트 payload로 복사합니다.
- `upgrades/v0.9.0-beta.4-manifest.json`은 공개 beta.4 manifest의 크기 31,988바이트와 SHA-256 `D623C611962CE7F94CC3806DA81B00EDAD7809FB87E489001FE9F0ADF39BAC60`을 고정한 직접 업그레이드 입력입니다.
- `upgrades/v0.9.0-beta.5-manifest.json`은 공개 beta.5 manifest의 크기 32,845바이트와 SHA-256 `A9A402E1BD5A8ECD856EABA70BA2F88A828D42F68D37E6F2B82BF7659991B05F`을 고정한 직접 업그레이드 입력입니다.
- `upgrades/v0.9.0-beta.6-manifest.json`은 공개 beta.6 manifest의 크기 33,107바이트와 SHA-256 `32E731E43E6D00773867AF89A1BB0C0415099B69359B39C98153CE025279537C`를 고정한 직접 업그레이드 입력입니다.
- 전체 설치 파일은 51개입니다.

폰트 없는 AGG 기반의 해시는 manifest에 고정돼 있습니다. 설치기는 나눔고딕코딩으로 임시 생성한 AGG의 구조와 변경 리소스 범위를 검사합니다. 오리지널 AGG의 변경 리소스는 `FONT.ICN`, `SMALFONT.ICN`, `RECRBKG.ICN`, 확장 AGG는 `FONT.ICN`, `SMALFONT.ICN`으로 제한합니다. 최종 두 AGG의 실제 크기와 SHA-256은 `_homm2_ko_install/receipt.json`에 기록합니다.

`VERIFY.cmd`는 이 receipt와 현재 파일을 대조합니다. `UNINSTALL.cmd`도 현재 파일이 설치 당시 동적 해시와 같을 때만 백업 원본으로 복구하므로, 사용자가 별도로 수정한 AGG를 덮어쓰지 않습니다.

`docs/ACTIVE_FILE_HASHES.json`은 beta.3 활성 번역 트리의 기존 source pin입니다. beta.4~beta.7 출력 해시 문서가 아니므로 파일 자체를 변경하지 않습니다. 설치 시 생성된 AGG 해시는 이 고정 문서가 아니라 각 설치 receipt의 책임입니다.

## 이전 버전에서 이동

공개 beta.4·beta.5·beta.6은 beta.7 직접 업그레이드를 지원합니다. 지원되는 이전 설치본은 모두 beta.7의 `INSTALL.cmd`를 실행하며, beta.7는 이전 글꼴 설정을 재사용하지 않고 동봉한 나눔고딕코딩으로 두 AGG를 다시 생성합니다.

업그레이드는 동봉한 고정 beta.4·beta.5·beta.6 manifest, 이전 receipt와 현재 설치 파일을 검증한 뒤 최초 GOG 원본 백업에서 beta.7 후보를 만듭니다. 실패하면 교체 전 베타 상태로 롤백합니다. 성공한 beta.7의 `UNINSTALL.cmd`는 최초 GOG 원본을 복원합니다.

beta.1~beta.3은 직접 업그레이드를 지원하지 않습니다. 먼저 설치에 사용한 이전 버전의 `UNINSTALL.cmd`로 원본을 복구해야 합니다. 이전 배포 폴더가 없다면 같은 버전 ZIP을 다시 받아 제거할 수 있습니다.

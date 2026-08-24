# v0.9.0-beta.6 릴리스 노트

날짜: 2026-08-24

beta.6는 배포 글꼴을 SIL Open Font License 1.1의 `NanumGothicCoding Regular` 하나로 고정하고, 공개 beta.4·beta.5 설치본에서 직접 업그레이드하는 경로를 제공합니다.

## 글꼴 배포 정책

- ZIP에 포함하는 글꼴은 `fonts/NanumGothicCoding-Regular.ttf` 하나뿐입니다.
- `INSTALL_CUSTOM_FONT.cmd`와 `--choose-font`, `--font-file`, `--font-index` 사용자 글꼴 선택 경로를 제거했습니다.
- 깨끗한 GOG 원본과 지원되는 이전 베타 모두 `INSTALL.cmd`로 설치합니다.
- beta.4·beta.5에서 사용자 글꼴을 사용했더라도 별도 재선택 없이 beta.6 나눔고딕코딩으로 자동 전환합니다.

나눔고딕코딩 원본과 렌더러 v2 계약은 beta.5와 같습니다.

- 글꼴 원본: Google Fonts `google/fonts` commit `90abd17b4f97671435798b6147b698aa9087612f`
- 글꼴 SHA-256: `787EFFD7EFED2ABCA88ADE231FAA8191F4E9FCF85B1805A13EE1DC3724B72089`
- 라이선스: SIL Open Font License 1.1
- 일반 글꼴: 13x14 셀, advance 13, 공통 ink-bottom 기준선 14
- 작은 글꼴: 11x12 셀, advance 11, 공통 ink-bottom 기준선 12

## 모집 비용 문구 복구

beta.5에서 다시 영어로 보이던 모집 창의 `Cost per troop:`을 `병력당 비용:`으로 복구했습니다. 완성된 원작 그림이나 미리 만든 글자 이미지를 ZIP에 넣지 않고, 설치기가 순정 `RECRBKG.ICN`을 확인한 뒤 나눔고딕코딩 작은 글리프로 지정 영역만 생성합니다. 지정 영역 밖의 픽셀·transform, 두 번째 sprite와 다른 AGG 리소스는 그대로 보존하도록 검증합니다.

## 설치와 직접 업그레이드

- 깨끗한 GOG 원본: `INSTALL.cmd`
- 공개 beta.4 설치본: beta.6의 `INSTALL.cmd`
- 공개 beta.5 설치본: beta.6의 `INSTALL.cmd`
- beta.1~beta.3 설치본: 해당 버전의 `UNINSTALL.cmd`로 GOG 원본을 복구한 뒤 beta.6 설치

beta.6는 다음 공개 manifest를 ZIP에 원문 그대로 포함하고 descriptor의 버전·경로·크기·SHA-256을 고정합니다.

| 업그레이드 원본 | 경로 | 크기 | SHA-256 |
|---|---|---:|---|
| beta.4 | `upgrades/v0.9.0-beta.4-manifest.json` | 31,988 | `D623C611962CE7F94CC3806DA81B00EDAD7809FB87E489001FE9F0ADF39BAC60` |
| beta.5 | `upgrades/v0.9.0-beta.5-manifest.json` | 32,845 | `A9A402E1BD5A8ECD856EABA70BA2F88A828D42F68D37E6F2B82BF7659991B05F` |

설치기는 고정 manifest, 이전 receipt와 현재 51개 설치 파일을 모두 확인한 뒤 최초 GOG 원본 백업에서 beta.6 후보를 만듭니다. 업그레이드가 실패하면 교체 전 beta.4 또는 beta.5 상태로 롤백합니다. 업그레이드된 beta.6를 제거하면 이전 베타가 아니라 최초 GOG 원본을 복원합니다.

## 범위와 알려진 제한

- 오리지널·확장 캠페인 맵 47개와 주요 비이미지 UI 번역을 포함합니다.
- 일반 MP2/MX2 사용자 지도는 번역 범위에서 제외합니다.
- 그림에 박힌 버튼·제목과 시험 이미지 UI ICN 4개는 원본 영어로 표시됩니다.
- 모집 창의 `Cost per troop:` 한 곳은 예외적으로 `병력당 비용:`으로 표시됩니다.
- 설치 뒤 `VERIFY.cmd`로 51개 설치 파일과 receipt를 확인할 수 있습니다.

`docs/ACTIVE_FILE_HASHES.json`은 beta.3 활성 번역 트리의 source pin입니다. beta.6 출력 해시 목록이 아니므로 이번 배포에서도 파일 자체를 바꾸지 않습니다.

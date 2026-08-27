# 설치·검증·제거 안내

이 문서는 `v0.9.0-beta.9` 기준입니다. 공개 beta.4·beta.5·beta.6·beta.7·beta.8 설치본은 직접 업그레이드할 수 있고, beta.1~beta.3은 먼저 제거해야 합니다.

## 설치·업그레이드 전

- Heroes II, DOSBox, GOG Galaxy를 모두 종료합니다.
- 지원 대상은 GOG 영문 DOS판 build `52745329670822422`뿐입니다.
- 게임 파일과 백업·임시 생성 공간을 합쳐 최소 150MB의 여유를 권장합니다.
- beta.1~beta.3이 설치돼 있다면 그 버전의 `UNINSTALL.cmd`로 원본을 먼저 복구합니다.
- beta.4·beta.5·beta.6·beta.7·beta.8이 설치돼 있다면 제거하지 말고 아래의 직접 업그레이드 절차를 사용합니다.

이전 beta.1~beta.3 배포 폴더가 없다면 같은 버전의 ZIP을 GitHub Releases에서 다시 받아 제거할 수 있습니다. 설치기는 지원 GOG 원본 또는 검증된 공개 beta.4·beta.5·beta.6·beta.7·beta.8 설치본 외의 수정 파일에는 새 델타나 글리프를 겹쳐 적용하지 않습니다.

설치기는 `GAMES`, `*.HS`, `HEROES2.CFG`, 일반 지도와 개인 세이브를 건드리지 않습니다.

## 설치

beta.9 ZIP을 모두 푼 뒤 기본 이롭게 바탕체를 쓰려면 `INSTALL.cmd`를 실행합니다. 설치기는 동봉한 `fonts/IropkeBatangM.ttf`로 게임 글리프·버튼·`병력당 비용:`을 생성하고, 없는 매핑 문자는 `fonts/NanumGothicCoding-Regular.ttf`로 보완합니다. 두 글꼴은 SIL Open Font License 1.1로 배포합니다.

다른 글꼴을 쓰려면 `INSTALL_CUSTOM_FONT.cmd`를 실행하고 사용자가 보유한 TTF·OTF·TTC·OTC 파일을 선택합니다. 선택 파일은 설치 시 이 PC에서만 읽으며 패치 폴더로 복사하거나 수집·업로드·배포하지 않습니다. 설치기는 글꼴 이름이나 라이선스로 선택을 막지 않으므로 해당 파일을 사용할 권한은 사용자가 확인해야 합니다. 설치 후 글꼴만 바꾸려면 `UNINSTALL.cmd`로 원본을 복구한 뒤 원하는 설치 방식을 다시 실행합니다.

설치기는 다음 GOG Galaxy 기본 경로를 자동으로 확인합니다.

```text
C:\Program Files (x86)\GOG Galaxy\Games\HoMM 2 Gold
```

자동 탐지가 실패하면 명령 프롬프트에서 직접 지정합니다.

```text
homm2-ko-patcher.exe preflight --game-dir "C:\Program Files (x86)\GOG Galaxy\Games\HoMM 2 Gold"
homm2-ko-patcher.exe install --game-dir "C:\Program Files (x86)\GOG Galaxy\Games\HoMM 2 Gold"
```

일반 사용자는 필요한 런타임이 포함된 `homm2-ko-patcher.exe`를 사용하면 됩니다. 소스 형태의 `homm2_ko_patcher.py`를 직접 실행하려면 Python 3과 Pillow 12.0.0이 필요합니다.

사용자 글꼴 파일을 명령줄에서 직접 지정할 수도 있습니다. TTC·OTC처럼 여러 face가 든 파일은 0부터 시작하는 `--font-index`를 사용합니다.

```text
homm2-ko-patcher.exe install --font-file "C:\path\to\MyFont.ttf"
homm2-ko-patcher.exe install --font-file "C:\path\to\Collection.ttc" --font-index 1
```

## beta.4·beta.5·beta.6·beta.7·beta.8에서 직접 업그레이드

공개 beta.4·beta.5·beta.6·beta.7·beta.8 중 하나가 설치돼 있다면 기본 이롭게 바탕체로 바꿀 때 `INSTALL.cmd`, 사용자 글꼴로 만들 때 `INSTALL_CUSTOM_FONT.cmd`를 실행합니다. 이전 receipt에는 사용자 글꼴 경로가 저장되지 않으므로 사용자 글꼴 업그레이드에서는 파일을 다시 선택해야 합니다.

설치기는 배포 ZIP에 고정해 둔 beta.4·beta.5·beta.6·beta.7·beta.8 manifest의 크기·SHA-256과 기존 receipt·현재 설치 파일을 함께 확인합니다. 모두 맞을 때만 최초 GOG 원본 백업에서 beta.9 후보를 만들고, 현재 설치 파일을 별도 백업한 뒤 교체합니다. 실패하면 업그레이드 직전 버전으로 롤백합니다. 업그레이드된 beta.9의 `UNINSTALL.cmd`는 이전 베타가 아니라 최초 GOG 원본을 복원합니다.

## beta.9 설치 과정

1. GOG gameId·buildId·언어와 원본 50개 해시 확인
2. manifest v2, 고정 beta.4·beta.5·beta.6·beta.7·beta.8 upgrade manifest, 48개 고정 BSDIFF40, 2개 동적 AGG 기반 델타, `KOREAN.BIN`, 874자 매핑, 기본 이롭게 바탕체와 보완 나눔고딕코딩 해시 확인
3. 기본 또는 사용자가 선택한 글꼴 face의 매핑 문자 포함 여부를 확인하고, 빠진 문자는 나눔고딕코딩으로 보완
4. 렌더러 v3로 일반 13x14·작은 11x12 셀의 874자 글리프를 생성하되 FreeType bearing과 공통 typographic 기준선을 보존하고, 두 AGG의 `FONT.ICN`, `SMALFONT.ICN`과 한글 버튼 글씨를 재구성. 메인 메뉴 배경·장식과 선언된 글씨 영역 밖 픽셀은 원본 보존
5. 오리지널 `HEROES2.AGG`의 순정 `RECRBKG.ICN`을 확인하고 같은 작은 글꼴로 모집 창의 `Cost per troop:` 영역에 `병력당 비용:`을 생성
6. 고정 패치 결과와 동적 AGG를 임시 폴더에 먼저 만들고 구조·해시 검증
7. 원본과 기존 `cloud_saves` 충돌 파일을 `_homm2_ko_install`에 백업
8. AGG·캠페인·은행을 적용한 뒤 `HEROES2.EXE`를 마지막에 교체
9. 51개 설치 결과 전수 검증 및 실제 해시·선택 글꼴 메타데이터·업그레이드 출처를 receipt에 기록

중간에 오류가 나면 이미 변경한 파일을 역순으로 복구합니다. ICN 배열과 두 AGG 기반의 정확한 구성은 [docs/DYNAMIC_FONT_KO.md](docs/DYNAMIC_FONT_KO.md)를 확인하세요.

## 설치 확인

`VERIFY.cmd`를 실행하거나 다음 명령을 사용합니다.

```text
homm2-ko-patcher.exe verify --game-dir "C:\Program Files (x86)\GOG Galaxy\Games\HoMM 2 Gold"
```

`installed_files_verified`와 파일 수 `51`이 나오면 설치 당시 receipt를 기준으로 검증이 완료된 것입니다. 검증기는 설치 시 기록한 두 AGG의 실제 해시를 사용합니다.

## 제거

`UNINSTALL.cmd` 또는 다음 명령으로 제거합니다.

```text
homm2-ko-patcher.exe uninstall --game-dir "C:\Program Files (x86)\GOG Galaxy\Games\HoMM 2 Gold"
```

제거기는 설치 파일이 receipt의 설치 당시 해시와 같을 때만 원본을 복구합니다. 사용자가 설치 파일을 별도로 수정했다면 해당 파일을 덮어쓰거나 삭제하지 않고 중단합니다.

설치나 제거 도중 작업이 끊겼다면 `RECOVER.cmd`를 실행합니다. `_homm2_ko_install`을 수동으로 지우면 자동 검증·제거·복구가 불가능해질 수 있습니다.

## 자주 생기는 오류

- `원본 해시가 맞지 않습니다`: 다른 언어판, 다른 빌드, 지원하지 않는 기존 패치 또는 GOG 복구로 파일이 달라졌습니다.
- `지원하지 않는 직접 upgrade 버전입니다`: beta.1~beta.3을 제거해 GOG 원본으로 돌아간 뒤 설치하세요. beta.4·beta.5·beta.6·beta.7·beta.8은 공개 배포판과 설치 상태가 정확히 일치하는지 확인하세요.
- `cloud_saves 파일이 패치를 가리고 있습니다`: Galaxy 동기화나 다른 모드가 같은 경로의 파일을 다시 만들었습니다.
- `게임·DOSBox·GOG Galaxy를 먼저 종료`: 표시된 프로그램을 종료한 뒤 다시 실행하세요.
- `사용자가 수정한 파일은 제거하지 않습니다`: 해당 파일을 보존하기 위해 제거를 중단한 상태입니다.
- `글꼴 파일을 읽을 수 없습니다`: 기본 설치라면 ZIP을 다시 받아 모두 푼 뒤 `fonts/IropkeBatangM.ttf`와 `fonts/NanumGothicCoding-Regular.ttf`가 있는지 확인하고, 사용자 글꼴 설치라면 선택한 파일이 지원되는 TTF·OTF·TTC·OTC인지 확인하세요.
- `선택 글꼴과 기본 대체 글꼴에 없는 문자가 있습니다`: 필요한 문자를 포함한 다른 글꼴을 선택하세요.
- `글꼴 face 번호 범위`: TTC·OTC에 들어 있는 face 수에 맞는 `--font-index`를 지정하거나 `INSTALL_CUSTOM_FONT.cmd`에서 기본 face 0을 선택하세요.

문제가 생기면 오류 전문과 `_homm2_ko_install/receipt.json`을 함께 제보해 주세요. 개인 세이브는 첨부하지 않아도 됩니다.

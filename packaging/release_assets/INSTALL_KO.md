# 설치·검증·제거 안내

## 설치 전

- Heroes II, DOSBox, GOG Galaxy를 모두 종료합니다.
- 지원 대상은 GOG 영문 DOS판 build `52745329670822422`뿐입니다.
- 디스크에 게임 파일 약 56MB와 백업·임시 생성 공간을 합쳐 최소 150MB의 여유를 권장합니다.

공개 beta.4·beta.5·beta.6·beta.7·beta.8 설치자는 제거하지 말고 아래의 직접 업그레이드 절차를 사용합니다. beta.1~beta.3 설치자는 설치에 사용한 이전 배포 폴더의 `UNINSTALL.cmd`로 원본을 복구한 뒤 beta.9을 설치해야 합니다. 이전 배포 폴더가 없다면 해당 버전 ZIP을 다시 받아 제거할 수 있습니다.

설치기는 게임의 `GAMES`, `*.HS`, `HEROES2.CFG`, 일반 지도와 개인 세이브를 건드리지 않습니다.

## 설치

압축을 푼 뒤 기본 이롭게 바탕체를 쓰려면 `INSTALL.cmd`, 사용자가 보유한 로컬 글꼴을 쓰려면 `INSTALL_CUSTOM_FONT.cmd`를 실행합니다. 기본 파일은 `fonts/IropkeBatangM.ttf`이고, 두 설치 방식 모두 빠진 매핑 문자를 `fonts/NanumGothicCoding-Regular.ttf`로 보완합니다. 두 글꼴은 SIL Open Font License 1.1로 동봉합니다. 설치기는 `C:\Program Files (x86)\GOG Galaxy\Games\HoMM 2 Gold`를 기본 경로로 확인하며, 명령 프롬프트에서는 다음처럼 직접 실행할 수도 있습니다.

```text
homm2-ko-patcher.exe preflight --game-dir "C:\Program Files (x86)\GOG Galaxy\Games\HoMM 2 Gold"
homm2-ko-patcher.exe install --game-dir "C:\Program Files (x86)\GOG Galaxy\Games\HoMM 2 Gold"
```

게임이 기본 위치에 있거나 GOG 레지스트리에 등록돼 있으면 `--game-dir`은 생략할 수 있습니다.

일반 사용자는 필요한 런타임이 모두 포함된 `homm2-ko-patcher.exe`를 사용하면 됩니다. 소스 형태의 `homm2_ko_patcher.py`를 직접 실행하려면 Python 3과 Pillow 12.0.0이 필요합니다.

선택한 글꼴은 설치 시 이 PC에서만 읽고 패치 폴더로 복사하거나 수집·업로드·배포하지 않습니다. 설치기는 글꼴 이름이나 라이선스로 선택을 막지 않으므로 사용할 권한은 사용자가 확인해야 합니다. 명령줄에서는 다음처럼 파일과 TTC·OTC face를 직접 지정할 수 있습니다.

이롭게 바탕체 원본 TTF는 기본 글꼴로 동봉하지만, 이 글꼴에서 만든 글리프·버튼 래스터와 완성 AGG는 포함하지 않고 설치 시 생성합니다.

```text
homm2-ko-patcher.exe install --font-file "C:\path\to\MyFont.ttf"
homm2-ko-patcher.exe install --font-file "C:\path\to\Collection.ttc" --font-index 1
```

설치 후 글꼴만 바꾸려면 `UNINSTALL.cmd`로 원본을 복구한 뒤 원하는 설치 방식을 다시 실행합니다.

## beta.4·beta.5·beta.6·beta.7·beta.8에서 직접 업그레이드

공개 beta.4·beta.5·beta.6·beta.7·beta.8 중 하나가 설치된 상태에서는 기본 이롭게 바탕체로 만들 때 `INSTALL.cmd`, 사용자 글꼴로 만들 때 `INSTALL_CUSTOM_FONT.cmd`를 실행합니다. 이전 receipt는 사용자 글꼴 경로를 저장하지 않으므로 사용자 글꼴 업그레이드에서는 파일을 다시 선택합니다.

설치기는 동봉한 고정 beta.4·beta.5·beta.6·beta.7·beta.8 manifest의 크기·SHA-256, 기존 receipt와 현재 51개 설치 파일을 검증합니다. 최초 GOG 원본 백업에서 beta.9 후보를 만든 뒤에만 교체하며, 실패하면 업그레이드 직전 버전으로 롤백합니다. 업그레이드가 끝난 beta.9의 `UNINSTALL.cmd`는 이전 베타가 아니라 최초 GOG 원본을 복원합니다.

설치 과정은 다음 순서로 진행됩니다.

1. GOG gameId·buildId·언어와 원본 50개 해시 확인
2. 배포 패치, 고정 beta.4·beta.5·beta.6·beta.7·beta.8 upgrade manifest, `KOREAN.BIN`, 글리프 빌더, 기본 이롭게 바탕체와 보완 나눔고딕코딩 확인
3. 기본 또는 사용자가 선택한 글꼴 face의 매핑 문자를 확인하고, 빠진 문자는 나눔고딕코딩으로 보완
4. 모든 고정 패치 결과와 선택 글꼴 AGG를 임시 폴더에 먼저 생성하고, 원본 메인 메뉴가 보존됐는지와 동적으로 만든 한글 버튼 및 모집 창의 `병력당 비용:` 결과까지 검증
5. 원본과 기존 `cloud_saves` 충돌 파일을 `_homm2_ko_install`에 백업
6. AGG·캠페인·은행을 적용하고 `HEROES2.EXE`는 마지막에 교체
7. 51개 설치 결과 전수 검증 및 실제 해시를 receipt에 기록

중간에 오류가 나면 이미 바뀐 파일을 역순으로 복구합니다.

렌더러 v3는 일반 글꼴을 13x14 셀·advance 13, 작은 글꼴을 11x12 셀·advance 11로 생성합니다. 선택·보완 글꼴의 실제 bearing 범위를 함께 셀에 맞춘 뒤 공통 기준선을 정하고, 각 글리프를 `baseline + glyph.top`에 놓습니다. 글자별 확대·축소나 바닥 강제 정렬 없이 원래 수직 관계를 보존합니다.

한글 글리프와 한글화 대상으로 정한 버튼, 모집 창의 `병력당 비용:`은 모두 설치 시 같은 선택 글꼴로 동적으로 만듭니다. 메인 메뉴와 한글화 대상으로 선언하지 않은 이미지 UI는 원본을 보존합니다.

## 설치 확인

`VERIFY.cmd`를 실행하거나 다음 명령을 사용합니다.

```text
homm2-ko-patcher.exe verify --game-dir "C:\Program Files (x86)\GOG Galaxy\Games\HoMM 2 Gold"
```

`installed_files_verified`와 파일 수 `51`이 나오면 설치 당시 receipt를 기준으로 검증이 완료된 것입니다.

## 제거

`UNINSTALL.cmd`를 실행하거나 다음 명령을 사용합니다.

```text
homm2-ko-patcher.exe uninstall --game-dir "C:\Program Files (x86)\GOG Galaxy\Games\HoMM 2 Gold"
```

제거기는 설치 후 파일이 정확히 설치 당시 해시와 같을 때만 원본을 복구합니다. 사용자가 설치 파일을 별도로 수정했다면 덮어쓰거나 삭제하지 않고 중단합니다.

백업과 제거 이력은 `_homm2_ko_install`에 남겨 복구 가능성을 보존합니다. 이 폴더를 수동으로 지우면 자동 제거가 불가능해질 수 있습니다.

설치나 제거 도중 전원 종료 등으로 작업이 끊겼다면 `RECOVER.cmd`를 실행하세요. 설치 중단은 원본으로 되돌리고, 제거 중단은 안전하게 제거를 이어서 끝냅니다.

## 자주 생기는 오류

- `원본 해시가 맞지 않습니다`: 다른 언어판, 다른 빌드, 기존 모드 또는 GOG 복구로 파일이 달라졌습니다.
- `지원하지 않는 직접 upgrade 버전입니다`: beta.1~beta.3을 제거해 GOG 원본으로 돌아간 뒤 설치하세요. beta.4·beta.5·beta.6·beta.7·beta.8은 공개판의 receipt와 설치 파일이 정확히 유지돼 있어야 합니다.
- `cloud_saves 파일이 패치를 가리고 있습니다`: 설치 후 Galaxy 동기화나 다른 모드가 같은 경로의 파일을 다시 만들었습니다.
- `게임·DOSBox·GOG Galaxy를 먼저 종료`: 표시된 프로그램을 종료한 뒤 다시 실행하세요.
- `사용자가 수정한 파일은 제거하지 않습니다`: 해당 파일을 보존하기 위해 제거를 중단한 상태입니다.
- `글꼴 파일을 읽을 수 없습니다`: 기본 설치라면 ZIP의 `fonts/IropkeBatangM.ttf`와 `fonts/NanumGothicCoding-Regular.ttf`, 사용자 설치라면 선택한 TTF·OTF·TTC·OTC 파일을 확인하세요.
- `선택 글꼴과 기본 대체 글꼴에 없는 문자가 있습니다`: 필요한 문자를 포함한 다른 글꼴을 선택하세요.
- `글꼴 face 번호 범위`: TTC·OTC에 맞는 `--font-index`를 지정하거나 파일 선택 창의 기본 face 0을 사용하세요.

문제가 생기면 오류 전문과 `_homm2_ko_install/receipt.json`을 함께 제보해 주세요. 개인 세이브 파일은 첨부하지 않아도 됩니다.

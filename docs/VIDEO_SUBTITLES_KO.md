# 캠페인 영상 한글 자막 빌드

이 문서는 beta.9 이후 일부 PC에서 첫 영상 재생 중 종료되거나 자막이 나타나지 않던 문제를 수정한 `v0.9.0-beta.10` 구현을 설명합니다. 정적 검증과 설치 적용을 마친 뒤 기본 GOG 바로가기에서 게임 실행과 오리지널 캠페인 자막 표시를 사용자 실기로 승인했습니다. 캠페인 영상 자막은 원본 영상이나 음성을 다시 배포하지 않고, 공개된 자막 큐와 빌드 코드만으로 생성합니다. 빌더는 사용자가 제공한 beta6 `HEROES2.EXE`와 `KOREAN.BIN`을 검사한 뒤 새 파일을 별도 출력 폴더에 만듭니다. 저장소 안에 완성 EXE/BIN을 쓰는 작업은 거부합니다.

## 포함 범위와 파일 구조

- `translations/subtitles/scene_cues_ko.tsv`: 51개 영상에 대응하는 57개 게임 장면, 388개 자막 큐. 숫자 표기는 한글 수사로 통일
- `tools/localization/h2_video_subtitles.py`: KSX2 큐 직렬화, dual-ms 시계, 2배 글꼴 합성, 검은색 외곽선, 고정 코드 화면 갱신 클리퍼 및 load-base 독립 LE 패치
- `tests/test_h2_video_subtitles.py`: 미디어나 게임 파일 없이 실행되는 계약 검사와 선택형 통합 검사

TSV의 `track`은 두 종류입니다.

- `primary_ms` 27개: 주 영상의 Smacker 시작 시각을 기준으로 표시
- `secondary_ms` 361개: 내레이션 음성 스트림의 Smacker 시작 시각을 기준으로 표시

두 시계는 한 프레임에서 같은 현재 타이머 값을 한 번만 읽되, 각 스트림의 시작 시각을 따로 빼서 계산합니다. 영상 루프 프레임 수가 아니라 실제 경과 밀리초를 사용하므로 배경 영상 반복과 내레이션 길이가 달라도 자막이 다시 나타나지 않습니다.

## 재현성 해시

입력은 아래 beta6 파일만 허용됩니다.

| 파일 | 크기 | SHA-256 |
|---|---:|---|
| beta6 `HEROES2.EXE` | 1,523,420 | `52AE3BA15AE309327D698EDEE8844684F91B3BA056B9215854002265A9F6E3EF` |
| beta6 `KOREAN.BIN` | 11,286 | `DD30DD967E81BB179BC1D33903D0B8926FB799D969A3C36FFAA6CA3FA0C89AAF` |
| `mapping874.fixed-interface-font.txt` | 42,302 | `3033584F6E65A36220F61EA58F8D7173A493FC83A72807D6FB43488AAE6DF164` |
| `scene_cues_ko.tsv` | 59,955 | `0F5DF72829709851454D73B2A24B8D54752EDE7D96B40C55D86B18BAED136B8E` |

beta.10의 고정 빌드 결과는 다음과 같습니다. 기존 beta.9 결과와는 다른 파일입니다.

| 파일 | 크기 | SHA-256 |
|---|---:|---|
| beta.10 `HEROES2.EXE` | 1,523,420 | `87B175EF0698C65893BAF6A0581E74BEA60CCECA0D8DF57E9DF7614B27DB2365` |
| beta.10 `KOREAN.BIN` | 36,159 | `37FDC1F372627E7B637EEEBFC15610E26B427E66947D7AA699B46B807F7338DA` |
| 복호화된 자막 런타임 | 1,856 | `B2EB2965514009DF9DEEDFF276D0471DE41C08B304EE04FDF394E87B0AD00575` |

런타임은 XOR 키 `0x0D`로 인코딩되어 H2K3의 NUL 종료 descriptor에 저장됩니다. 결과 bank에는 Object2 상대 위치를 사용하는 일반 문자열 155개, 기존 slot 문자열 16개, KSX2 CUE와 KSXR CODE를 합쳐 descriptor 173개와 render row 18개가 들어갑니다. 기존 유닛 이름 7개는 EXE 안의 원래 한글 payload와 바이트 단위로 같고 해당 포인터도 원래 LE fixup이 소유하므로, 중복 외부 descriptor만 제거하고 native 경로를 그대로 사용합니다.

## load-base 독립 외부 문자열 로더

DOSBox-X 디버그 실행과 기본 GOG DOSBox 실행은 LE Object1을 서로 다른 주소에 올릴 수 있습니다. 이전 후보는 자막 런타임 함수 주소와 `KOREAN.BIN`의 direct descriptor에 DOSBox-X에서 관측한 주소를 기록했기 때문에, 기본 실행에서는 H2K3 검증이 bank 전체를 state `0x84`로 폐기해 게임은 켜져도 자막이 하나도 나오지 않을 수 있었습니다.

`-05`는 실행 파일의 LE fixup 표에 37개 record를 추가했지만 기본 GOG DOSBox가 native `0xc0000005`로 종료되어 폐기했습니다. 내장 DOS/4GW 로더를 직접 확인한 결과 self-relative source type 8은 지원되며, fixup 페이지 표·크기·여유 공간도 정상이어서 LE 형식 오류로 단정할 수 없습니다. `-06`은 원인 격리를 위해 교차 오브젝트 self-relative record 5개만 제외했고, 사용자 실기에서 게임 실행과 자막 표시가 모두 정상임을 확인했습니다. 따라서 실패 범위는 신규 type-8 record 5개로 격리됐습니다.

beta.10에 채택한 `-07` 구현은 cross-object rel32와 type-8 record를 모두 없앱니다. Object1의 두 검증된 함수 정렬 공백에 `push imm32; ret` 중계 코드 3개를 넣고, Object3의 기존 36바이트 helper 영역은 크기를 늘리지 않은 채 절대 전송 2개로 바꿉니다. 원래 CALL은 중계 코드에 자신의 반환 주소를 남기므로 대상 함수가 그대로 원 호출자에게 돌아오고, JMP는 스택 변화 없이 tail-transfer됩니다. 중계 주소 5개는 전부 기존에 정상 동작이 확인된 type-7 fixup으로 채웁니다. 로더가 정한 실제 Object1/2/3 주소는 Object3의 10-entry 표로 전달되고, heap 런타임은 첫 호출에서 자기 operand 20개를 한 번만 고친 뒤 즉시 반환합니다.

H2K3의 고정 Object1 descriptor validator도 96바이트 영역 안에서 교체합니다. 일반 문자열 target은 Object2 내부 offset `0x2E920..0x31520`으로, expected 값은 같은 Object2 안의 상대 차이로 저장됩니다. validator는 LE loader가 채운 실제 Object2 base를 더해 target과 expected를 검증하고, 검증이 끝난 private record의 target만 실제 주소로 바꿉니다. 따라서 Object2가 어느 주소에 배치되어도 기존 원자적 검증·게시 순서가 유지됩니다.

## 고정 코드 깜빡임 방지 클리퍼

Smacker가 깨끗한 영상 하단을 먼저 표시하고 자막 런타임이 같은 영역을 다시 표시하면 화면이 `영상 → 자막`으로 반복 갱신되어 깜빡여 보입니다. beta.10은 다음 Smacker 갱신에서 사용할 높이를 Object3 offset `0x3EAC`의 dword에 저장하고 실제 주소는 LE loader가 정합니다. 기본값은 전체 영상 높이 479이고, 자막 띠를 실제로 출력한 프레임만 다음 갱신 높이를 자막 위쪽 406으로 바꿉니다.

Smacker의 원래 31바이트 갱신 context와 surface 포인터 fixup source Object1 `0x7395D`는 그대로 둡니다. 공통 `CALL`만 Object1의 검토된 세 alignment gap에 나뉘어 들어간 고정 클리퍼로 보냅니다. 클리퍼는 LE-relocated Object3 `0x3EAC`의 경계를 읽어 원래 stack height를 줄이거나, 이미 자막 영역에 들어온 갱신이면 원래 ABI대로 인자를 정리하고 반환합니다. forward 경로는 같은 Object1의 원래 `RECT_REFRESH` offset `0x85409`로 tail-jump합니다.

`RECT_REFRESH`의 `CALL` opcode는 원본과 같은 Object1 `0x7396D`에 고정합니다. 영상 루프에는 Object1 `0x739E8`의 `EB 83` 분기가 이 주소로 직접 합류하므로, 호출을 한 바이트라도 옮기면 분기가 rel32 변위 중간으로 들어가 명령 흐름이 깨집니다. 폐기된 초기 데이터-height 후보는 이 호출을 `0x7396C`로 옮겨 즉시 종료됐고, 현재 검사는 inbound branch의 바이트·목적지, `0x7396D`의 `E8`, 최종 대상 `0x95409`를 함께 고정합니다.

부트스트랩은 검토된 113바이트 영역만 사용하며 매 late-hook 진입에서 높이의 low byte를 `0xDF`로 되돌립니다. 자막 출력 경로는 `0x96`을 기록해 dword를 406으로 만들고, 자막이 없는 경로는 `0xDF`를 기록해 479로 복원합니다. H2K3 heap 런타임은 기존 late hook에서 동기 실행될 뿐, 그 주소를 다음 프레임 callback으로 보존하지 않습니다.

자막 화면 갱신에는 heap callback이나 heap에 저장한 다음 프레임 분기가 없습니다. 과거 실행 실패를 일으켰던 Watcom runtime metadata 80바이트는 계속 byte-preserve 계약으로 보호합니다. 정적 검사는 context의 스택 인자, 공유 `CALL` 진입점과 inbound branch, 같은 Object1의 `RECT_REFRESH` 대상, 높이 초기값, runtime의 406/479 상태 전이, 상대 descriptor 155개와 native fallback 7개, 원래 28,095개 fixup 전부 및 새 37개 type-7 fixup을 검사합니다. 최종 28,132개 record 가운데 type 8은 0개입니다.

generation을 코드 실행 안전성보다 단순한 높이 데이터로 바꾼 대가로, 자막 프레임 직후 영상 건너뛰기가 late hook 자체를 생략하면 다음 영상의 첫 inner refresh 한 번이 이전 406 높이를 사용할 수 있습니다. 다음 late hook은 즉시 479로 복원합니다. 이는 최대 한 프레임의 하단 띠 잔류 가능성으로 제한되며 heap 코드 재진입이나 종료 위험은 없습니다. 수동 검사에서 영상 건너뛰기와 연속 영상을 별도로 확인합니다.

이 구현은 고정 입력 통합 검사 12/12, 전체 저장소 검사 130개와 builder build/verify를 통과했습니다. 사용자가 기본 GOG 바로가기에서 직접 실행해 오리지널 캠페인 scene `0x04`의 자막 표시와 이후 게임 진행을 확인했으며 beta.10 배포 입력으로 승인했습니다.

## 빌드와 검증

아래에서 `<beta6-dir>`은 beta6 원본 파일을 보관한 폴더이고 `<output-dir>`은 이 저장소와 `<beta6-dir>` 밖의 비어 있거나 아직 존재하지 않는 전용 폴더입니다. 빌더는 두 입력 파일이 있는 폴더, 파일이 하나라도 든 출력 폴더와 기존 출력 파일을 거부하며 어떤 파일도 덮어쓰지 않습니다.

```powershell
python tools/localization/h2_video_subtitles.py build `
  --source-exe "<beta6-dir>\HEROES2.EXE" `
  --source-bank "<beta6-dir>\KOREAN.BIN" `
  --output-dir "<output-dir>"

python tools/localization/h2_video_subtitles.py verify `
  --source-exe "<beta6-dir>\HEROES2.EXE" `
  --source-bank "<beta6-dir>\KOREAN.BIN" `
  --output-dir "<output-dir>"
```

`build`는 `HEROES2.EXE`, `KOREAN.BIN`, `video_subtitles_manifest.json`을 생성합니다. `verify`는 같은 입력에서 결과를 메모리상으로 다시 만들고 모든 바이트와 고정 해시를 비교합니다.

일반 단위 검사는 게임 파일 없이 실행됩니다.

```powershell
python -m unittest tests.test_h2_video_subtitles
```

beta6 파일을 가진 개발자는 선택형 통합 검사도 실행할 수 있습니다.

```powershell
$env:HOMM2_BETA6_EXE = "<beta6-dir>\HEROES2.EXE"
$env:HOMM2_BETA6_BANK = "<beta6-dir>\KOREAN.BIN"
python -m unittest tests.test_h2_video_subtitles
```

환경 변수가 없으면 정적·계약 검사는 실행되고 proprietary 통합 검사만 skip됩니다. 고정 beta6 입력을 지정하면 실제 `build`와 `verify`까지 수행합니다. 이 검사는 바이트와 빌드 재현성을 확인하며 다른 PC 실기 검증을 대신하지 않습니다.

## 배포 전 수동 확인

정적 검증 이후 실제 게임에서 다음을 확인해야 합니다.

1. 게임이 메뉴까지 정상 실행되는지
2. INTRO와 롤란드 캠페인 첫 영상의 자막 싱크가 유지되는지
3. 내레이션 종료 후 자막이 다시 나타나지 않는지
4. 자막 표시 중 반복 깜빡임이 없는지
5. 영상을 건너뛴 뒤 메뉴 및 화면 하단이 정상인지
6. 영상을 연속 재생하거나 같은 영상에 다시 들어갔을 때 이전 높이 상태가 남지 않는지
7. 문제가 있었던 다른 PC에서 기본 GOG 바탕화면 바로가기로 첫 영상과 메뉴를 통과하는지

이 저장소에는 원본 `.SMK`, 추출 `.WAV`, 영문 transcript, Whisper 모델·캐시·전사 산출물을 포함하지 않습니다. TSV에는 배포 가능한 한국어 자막 문장과 최종 표시 시각만 들어 있습니다.

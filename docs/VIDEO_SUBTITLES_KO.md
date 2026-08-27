# 캠페인 영상 한글 자막 빌드

beta7의 캠페인 영상 자막은 원본 영상이나 음성을 다시 배포하지 않고, 공개된 자막 큐와 빌드 코드만으로 생성합니다. beta.9은 검증된 beta7 결과를 바이트 단위로 그대로 사용합니다. 빌더는 사용자가 제공한 beta6 `HEROES2.EXE`와 `KOREAN.BIN`을 검사한 뒤 새 파일을 별도 출력 폴더에 만듭니다. 저장소 안에 완성 EXE/BIN을 쓰는 작업은 거부합니다.

## 포함 범위와 파일 구조

- `translations/subtitles/scene_cues_ko.tsv`: 51개 영상에 대응하는 57개 게임 장면, 388개 자막 큐
- `tools/localization/h2_video_subtitles.py`: KSX2 큐 직렬화, dual-ms 시계, 2배 글꼴 합성, 검은색 외곽선, 안전한 화면 갱신 게이트 및 LE 실행 파일 패치
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
| `scene_cues_ko.tsv` | 59,940 | `E2A9B763D629D14EB0C661D09F3DACD61CFEF2ED27DE7A86D1CE7209E0E2222D` |

정상 빌드 결과는 다음과 같습니다.

| 파일 | 크기 | SHA-256 |
|---|---:|---|
| beta7 `HEROES2.EXE` | 1,523,420 | `B5416C793354122762B67973ACF86D985C8B5ACA26B74F29FE62E707E7A1548C` |
| beta7 `KOREAN.BIN` | 36,265 | `95EA660215425E34FCB7CFD37405F8D1869845EB2EAED245613D2FF8AAE1D20A` |
| 복호화된 자막 런타임 | 1,856 | `AFB5B05FF8CCBC053A45714DE0F816083131EAA605ACE6ECE3E8639FBD8C9239` |

런타임은 XOR 키 `0x0D`로 인코딩되어 H2K3의 NUL 종료 descriptor에 저장됩니다. KSX2 CUE 388개와 KSXR CODE 1,856바이트 외에 기존 beta6 bank의 178개 descriptor와 16개 render row는 그대로 보존됩니다.

## 깜빡임 방지 게이트

Smacker가 깨끗한 영상 하단을 먼저 표시하고 자막 런타임이 같은 영역을 다시 표시하면 화면이 `영상 → 자막`으로 반복 갱신되어 깜빡여 보입니다. beta7은 다음 조건을 모두 만족하는 동안에만 첫 갱신을 자막 영역 위쪽으로 제한합니다.

- 캠페인 영상 장면 범위 `0x04..0x3F`
- H2K3 bank가 정상적으로 준비됨
- 직전 프레임에 자막이 실제로 활성화됨
- 저장된 주 영상 generation과 현재 Smacker 시작 시각이 일치함

첫 자막 프레임, 자막 종료, 영상 건너뛰기, 장면 전환 또는 generation 불일치 시에는 원래의 전체 갱신으로 돌아갑니다. 간접 dispatch 포인터는 `0x182EAC`이며 초기 대상은 원래 `RECT_REFRESH`인 `0x2A4409`입니다. 부트스트랩은 검토된 113바이트 영역만 사용하고, 시작 코드에 속한 별도 80바이트 span은 내용 자체를 소스에 복사하지 않고 SHA-256 및 byte-preserve 계약으로 보호합니다. LE fixup table과 record도 입력과 byte-exact인지 검사합니다.

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

환경 변수가 없으면 proprietary 통합 검사 한 건만 skip됩니다.

## 배포 전 수동 확인

정적 검증 이후 실제 게임에서 다음을 확인해야 합니다.

1. 게임이 메뉴까지 정상 실행되는지
2. INTRO와 롤란드 캠페인 첫 영상의 자막 싱크가 유지되는지
3. 내레이션 종료 후 자막이 다시 나타나지 않는지
4. 자막 표시 중 반복 깜빡임이 없는지
5. 영상을 건너뛴 뒤 메뉴 및 화면 하단이 정상인지

이 저장소에는 원본 `.SMK`, 추출 `.WAV`, 영문 transcript, Whisper 모델·캐시·전사 산출물을 포함하지 않습니다. TSV에는 배포 가능한 한국어 자막 문장과 최종 표시 시각만 들어 있습니다.

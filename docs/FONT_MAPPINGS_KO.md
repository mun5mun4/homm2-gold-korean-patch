# 글리프·인코딩 매핑

공개 저장소에는 최종 배포 계통에 직접 관련된 두 매핑만 보존합니다.

| 용도 | 경로 | 크기 | SHA-256 |
|---|---|---:|---|
| beta.3 source pin 및 beta.4~beta.10 동적 생성 874자 | `translations/font/mapping874.fixed-interface-font.txt` | 42,302 | `3033584F6E65A36220F61EA58F8D7173A493FC83A72807D6FB43488AAE6DF164` |
| 캠페인 기준 861자 | `translations/font/mapping861.campaign-font.txt` | 41,795 | `2F048A8FAAA4372908E0F4D12709639FABAE097BD0C47092FA3E9A4786D9E000` |

beta.10 설치기는 첫 파일의 874행을 그대로 사용합니다. 각 행은 Unicode 문자 하나, 게임 내부 2바이트 escape와 sprite 인덱스를 연결하며 한글 영역은 `0x100`부터 `0x469`까지 연속입니다. 문자 순서나 인덱스를 바꾸면 EXE, 캠페인과 `KOREAN.BIN`의 기존 인코딩도 함께 바꿔야 하므로 매핑은 해시 고정 입력입니다.

최종 `FONT.ICN`과 `SMALFONT.ICN`의 배열은 다음과 같습니다.

- 인덱스 `0x000`~`0x05F`: 원본 legacy sprite 96개. 인덱스 32의 `@` 칸만 투명 1×1 글리프로 바꿉니다.
- 인덱스 `0x060`~`0x0FF`: 원본 sprite 0을 복제한 filler 160개
- 인덱스 `0x100`~`0x469`: 매핑 순서대로 설치 시 생성하는 글리프 874개
- 합계: 1,130 sprite

이 배열은 `HEROES2.AGG`와 `HEROES2X.AGG`의 일반·작은 글꼴에 똑같이 적용됩니다. 더 자세한 생성·대체·검증 규칙은 [DYNAMIC_FONT_KO.md](DYNAMIC_FONT_KO.md)를 확인하세요.

두 매핑 파일은 `.gitattributes`에서 줄바꿈 정규화를 끕니다. 후보 AGG, raster JSON, PNG, 바탕체에서 만든 고정 글리프 payload는 포함하지 않습니다. 배포에 동봉하는 기본 `IropkeBatangM.ttf`, 보완 `NanumGothicCoding-Regular.ttf`와 각각의 OFL 고지는 beta.10 설치 자산으로 별도 보존합니다. 글리프·버튼 래스터는 두 글꼴과 매핑에서 설치 시 생성합니다.

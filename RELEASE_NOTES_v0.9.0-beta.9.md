# Heroes of Might and Magic II Gold 한국어 패치 v0.9.0-beta.9

배포일: 2026-08-27

beta.9은 사용자가 확인한 이롭게 바탕체 렌더링을 다른 PC의 기본 설치에서도 그대로 만들 수 있도록 글꼴 배포 구성을 바로잡은 버전입니다.

## 주요 변경

- `Iropke Batang Medium` 원본 TTF를 기본 글꼴로 동봉합니다.
- `INSTALL.cmd`를 실행하면 설치기가 게임 글리프 874자, 한글 버튼과 모집 창의 `병력당 비용:`을 이롭게 바탕체로 생성합니다.
- 이롭게 바탕체에 없는 매핑 문자는 동봉한 `NanumGothicCoding Regular`가 보완합니다.
- `INSTALL_CUSTOM_FONT.cmd`와 명령줄 글꼴 선택 기능은 그대로 사용할 수 있습니다.
- 완성 AGG나 미리 생성한 글리프·버튼 이미지는 포함하지 않으며, 지원 GOG 원본을 확인한 뒤 설치할 때 생성합니다.
- 공개 beta.4·beta.5·beta.6·beta.7·beta.8 설치본에서 제거 없이 직접 업그레이드할 수 있습니다.

## 설치

1. Heroes II, DOSBox와 GOG Galaxy를 종료합니다.
2. `homm2-ko-v0.9.0-beta.9-win-gog.zip`을 받아 모두 풉니다.
3. 기본 이롭게 바탕체를 쓰려면 `INSTALL.cmd`를 실행합니다.
4. 다른 글꼴을 쓰려면 `INSTALL_CUSTOM_FONT.cmd`를 실행하고 사용자가 보유한 TTF·OTF·TTC·OTC를 선택합니다.

beta.1~beta.3 설치본은 먼저 해당 버전의 `UNINSTALL.cmd`로 GOG 원본을 복구해야 합니다. beta.4~beta.8은 그대로 beta.9 설치기를 실행하면 됩니다. 업그레이드 도중 실패하면 직전 상태로 롤백하며, beta.9을 제거하면 최초 GOG 원본을 복원합니다.

## 글꼴 라이선스

동봉한 이롭게 바탕체와 나눔고딕코딩은 SIL Open Font License 1.1을 따릅니다.

- 이롭게 바탕체: `Copyright (c) 2016, 이롭게(iropke) (www.iropke.com | hello@iropke.com)`
- Reserved Font Name: '이롭게 바탕체', 'iropke batang'
- 이롭게 바탕체 라이선스: `THIRD_PARTY_LICENSES/IROPKE_BATANG_OFL.txt`
- 나눔고딕코딩 라이선스: `THIRD_PARTY_LICENSES/NANUM_GOTHIC_CODING_OFL.txt`

원작 게임 파일은 포함하지 않습니다. 지원 대상은 GOG gameId `1207658785`, buildId `52745329670822422`의 English 설치본입니다.

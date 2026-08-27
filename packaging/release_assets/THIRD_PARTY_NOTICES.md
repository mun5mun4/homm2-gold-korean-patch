# 제3자 자료 고지

## munument1/-KR-fheroes2

한국어 문안의 비교·보완 과정에서 다음 공개 저장소의 번역을 참고하고 일부 문안을 채택·수정했습니다.

- 저장소: `https://github.com/munument1/-KR-fheroes2`
- 고정 커밋: `29d0a76ceb26d57e9f134b6d682ac857acecfad4`
- 주요 참고 파일: `files/lang/ko.po`
- 원 저장소 라이선스: GNU General Public License v2.0

캠페인 번역 원장과 비이미지 UI 대조표에는 해당 출처를 행 단위 또는 배치 단위로 기록했습니다. DOS판의 제한된 글자 공간, 자체 2바이트 인코딩, 문맥과 화면 폭에 맞추기 위해 다수 문장을 축약하거나 다시 구성했습니다.

이 배포판은 GPL-2.0-only 조건을 따르며 라이선스 전문을 `COPYING.GPL-2.0`에 포함합니다. 대응 번역 원장과 공개 패치 도구는 같은 Git 태그의 소스 저장소에서 제공합니다.

## Iropke Batang Medium

beta.9의 기본 한글 글리프·버튼 생성 글꼴로 `fonts/IropkeBatangM.ttf`를 포함합니다.

- 저작권 고지: Copyright (c) 2016, 이롭게(iropke) (www.iropke.com | hello@iropke.com)
- Reserved Font Name: '이롭게 바탕체', 'iropke batang'
- 라이선스: SIL Open Font License 1.1
- 용도: 기본 한글 글리프·버튼·`병력당 비용:` 생성
- 원본: `https://github.com/iropke/font-iropke-batang`
- 원본 SHA-256: `5910F97BAED6C6E0B8538E40D326B169E0A510357E20DD9003ABABCE2CE1CC69`

TTF는 원본을 수정하지 않고 그대로 동봉합니다. OFL 1.1은 라이선스와 저작권 고지를 함께 포함하는 조건으로 글꼴을 소프트웨어와 묶어 재배포할 수 있도록 허용합니다. OFL 1.1과 Reserved Font Name 고지 전문은 `THIRD_PARTY_LICENSES/IROPKE_BATANG_OFL.txt`에 있습니다. 이 글꼴에서 미리 만든 고정 래스터나 완성 AGG는 포함하지 않으며 설치 시 생성합니다.

## NanumGothicCoding Regular

beta.9의 보완 한글 글꼴로 `fonts/NanumGothicCoding-Regular.ttf`를 포함합니다.

- 저작권 고지: Copyright (c) 2010, NHN Corporation
- 라이선스: SIL Open Font License 1.1
- 용도: 배포판 한글 글리프 생성
- 원본: Google Fonts `google/fonts` commit `90abd17b4f97671435798b6147b698aa9087612f`
- 원본 SHA-256: `787EFFD7EFED2ABCA88ADE231FAA8191F4E9FCF85B1805A13EE1DC3724B72089`

TTF는 위 원본을 수정하지 않고 그대로 동봉합니다. 라이선스와 Reserved Font Name 고지 전문은 `THIRD_PARTY_LICENSES/NANUM_GOTHIC_CODING_OFL.txt`에 있습니다.

## Pillow

Pillow 12.0.0은 설치 시 기본 이롭게 바탕체, 보완 나눔고딕코딩 또는 사용자가 선택한 로컬 글꼴을 한글 비트맵 글리프와 동적 버튼 래스터로 그리는 데 사용되며 Windows 단독 실행 파일에 포함됩니다. Pillow 및 그 기반이 된 PIL의 저작권·라이선스 고지 전문은 `THIRD_PARTY_LICENSES/PILLOW_LICENSE.txt`에 있습니다.

## Python bsdiff4

배포 델타는 빌드 시 `bsdiff4`를 사용해 생성했습니다. 최종 설치 실행 파일에는 bsdiff4 확장 모듈을 포함하지 않으며, 설치기는 Python 표준 라이브러리로 BSDIFF40 형식을 해석합니다. 라이선스 전문은 `THIRD_PARTY_LICENSES/BSDIFF4_LICENSE.txt`에 있습니다.

## PyInstaller

Windows 단독 실행 파일은 PyInstaller 6.15.0으로 묶었습니다. PyInstaller 부트로더 및 런타임 예외의 조건은 PyInstaller 프로젝트의 라이선스를 따릅니다. 동일한 기능의 원본 Python 설치기는 배포 ZIP과 소스 저장소에 함께 포함합니다. 전문은 `THIRD_PARTY_LICENSES/PYINSTALLER_COPYING.txt`에 있습니다.

## Python

단독 실행 파일에는 Python 3.13.7 런타임이 포함됩니다. Python Software Foundation 라이선스 전문은 `THIRD_PARTY_LICENSES/PYTHON_LICENSE.txt`에 있습니다.

# 제3자 자료 고지

## munument1/-KR-fheroes2

한국어 문안의 비교·보완 과정에서 다음 공개 저장소의 번역을 참고하고 일부 문안을 채택·수정했습니다.

- 저장소: `https://github.com/munument1/-KR-fheroes2`
- 고정 커밋: `29d0a76ceb26d57e9f134b6d682ac857acecfad4`
- 주요 참고 파일: `files/lang/ko.po`
- 원 저장소 라이선스: GNU General Public License v2.0

참고·수정한 문안과 provenance는 `translations/campaign/fheroes2_reference_translation_draft.tsv`에 보존했습니다. DOS판의 제한된 글자 공간, 자체 2바이트 인코딩, 문맥과 화면 폭에 맞추기 위해 여러 문장을 축약하거나 다시 구성했습니다.

이 프로젝트의 공개 소스와 번역 데이터는 GPL-2.0-only 조건을 따르며 라이선스 전문을 루트 `LICENSE`에 포함합니다.

## NanumGothicCoding Regular

beta.8의 기본·대체 한글 글리프 생성 글꼴로 `packaging/release_assets/fonts/NanumGothicCoding-Regular.ttf` 하나만 포함합니다.

- 저작권 고지: Copyright (c) 2010, NHN Corporation
- 라이선스: SIL Open Font License 1.1
- 배포 파일: `fonts/NanumGothicCoding-Regular.ttf`
- 원본: Google Fonts `google/fonts` commit `90abd17b4f97671435798b6147b698aa9087612f`
- 원본 SHA-256: `787EFFD7EFED2ABCA88ADE231FAA8191F4E9FCF85B1805A13EE1DC3724B72089`

TTF는 위 원본을 수정하지 않고 그대로 동봉합니다. 라이선스와 Reserved Font Name 고지 전문은 `packaging/release_assets/THIRD_PARTY_LICENSES/NANUM_GOTHIC_CODING_OFL.txt`에 있습니다. 바탕체 파일이나 바탕체에서 미리 만든 고정 래스터는 포함하지 않습니다.

## 사용자 로컬 글꼴 예시

beta.8 개발 검증에서는 사용자가 로컬로 보유한 `Iropke Batang Medium`을 선택해 874자 생성, typographic 기준선과 전경 잘림 0을 확인했습니다. 이 이름은 사용자 글꼴 경로의 동작을 설명하는 검증 예시일 뿐입니다. 해당 글꼴 파일, 라이선스 파일, 그 글꼴로 미리 생성한 래스터·AGG는 저장소나 배포 ZIP에 포함하지 않습니다.

## Pillow

Pillow 12.0.0은 설치 시 기본 나눔고딕코딩 또는 사용자가 선택한 로컬 글꼴을 Heroes II 비트맵 글리프로 그리는 데 사용되며 Windows 단독 실행 파일에 포함됩니다. Pillow 및 그 기반이 된 PIL의 저작권·라이선스 고지 전문은 `packaging/release_assets/THIRD_PARTY_LICENSES/PILLOW_LICENSE.txt`에 있습니다.

## Python bsdiff4

배포 델타는 빌드 시 `bsdiff4`를 사용해 생성했습니다. 최종 설치 실행 파일에는 bsdiff4 확장 모듈을 포함하지 않으며 설치기는 Python 표준 라이브러리로 BSDIFF40을 해석합니다. 라이선스 전문은 `packaging/release_assets/THIRD_PARTY_LICENSES/BSDIFF4_LICENSE.txt`에 있습니다.

## PyInstaller와 Python

Windows 단독 실행 파일은 PyInstaller 6.15.0과 Python 3.13.7로 만들었습니다. 동일한 기능의 Python 원본 설치기와 동적 폰트 빌더를 배포 ZIP과 `tools/release/`에 함께 제공합니다. 해당 라이선스 전문은 다음 경로에 있습니다.

- `packaging/release_assets/THIRD_PARTY_LICENSES/PYINSTALLER_COPYING.txt`
- `packaging/release_assets/THIRD_PARTY_LICENSES/PYTHON_LICENSE.txt`

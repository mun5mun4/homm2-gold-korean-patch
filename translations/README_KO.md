# 번역 소스

- `campaign/`: 캠페인 문장, 도시·영웅 음역, EXE 캠페인 문구와 fheroes2 참고 원장
- `interface/`: 유닛·건물·주문·기술·설명 문구의 선별된 작업표
- `font/`: 캠페인 861자와 최종 874자 인코딩 매핑

일부 TSV 파일명에 `draft`가 남아 있는 이유는 원문 위치와 검토 상태를 보존하기 위해서입니다. 실제 beta.3 적용 결과의 기준은 `docs/ACTIVE_FILE_HASHES.json`과 배포 manifest입니다.

현재 beta.3은 H2K3의 기존 178개 descriptor를 유지합니다. 문장 155개는
실기에서 확인한 Object2 재배치 좌표를 사용하고, 유닛 이름 7개와 렌더 토큰
16개는 기존 좌표를 유지합니다. 합류 문장은 외부 은행과 EXE 폴백에 함께 둡니다.

`fheroes2_reference_translation_draft.tsv`의 출처는 `THIRD_PARTY_NOTICES.md`에 고정했습니다.

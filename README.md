# GHeSS 문서 AI 솔루션 재설계

2026-09-30 기준. 기존 PDF의 전제를 현재 구현과 사내 제약에 맞춰 갱신한 설계안이다. 원본 PDF는 보존했다.

**최신 용량 산정은 Milvus를 제외하고 파일 첨부·필요 시 DeDRM·파싱/OCR·DOCX/PPTX 초안 생성을 포함한다.** 일일 15,000요청, 피크 5요청/초, 첨부 30%·초안 20%, CPU/모델 이용률 60%, 파일 작업자 1개 장애 여유를 둔 보수적 가정이다. 역할별 **354 vCPU·804GiB**, 플랫폼 예약 포함 호스트 풀 편성 **448 vCPU·1,024GiB 이상**, 신규 논리 저장·독립 백업 합계 **24TiB**, 작업자 임시 SSD 합계 **2,900GiB**를 계획한다. 사내 LLM·임베딩 추론 하드웨어 및 객체 저장소 서버는 CPU/RAM 합계에서 제외한다. 높은 첨부/OCR 사용량을 가정한 검증 시작 예산이며 실측 확정값이 아니다.

- [최신 보수 산정 DOCX](docs/권장_서버_용량_추정.docx) · [보고서 Markdown](docs/권장_서버_용량_추정.md)
- [첨부·문서 생성 산정 입력](capacity/workflow_inputs.json) · [계산 결과 JSON](capacity/workflow_result.json)

- [임베딩 완료 이후: Milvus 프로덕션 마이그레이션·메타데이터 보강·검색 최적화 계획서](docs/Milvus_프로덕션_이관_및_검색_최적화.md)
- [새 설계: 현재 구현, FastAPI 로직, 검색 API 연계, Milvus 운영, 단계별 전환](docs/GHeSS_솔루션_재설계.md)
- [트래픽·리소스 산정 방법과 실측 계획](docs/트래픽_리소스_산정.md)
- [1차 오픈: 09~18시 1,500명 트래픽·서버·레플리카 준비안](docs/1차_오픈_용량_계획.md)
- [시나리오별 계산 결과](docs/산정_결과.md)
- [산정 입력값](capacity/inputs.json)
- [권장 서버 용량 추정 보고서 (DOCX)](docs/권장_서버_용량_추정.docx) · [편집 원본](docs/권장_서버_용량_추정.md)
- [사이드바 가로 텍스트 로고와 브랜드 에셋](brand/g-hess/README.md) · [전체 로고 키트 ZIP](brand/g-hess-logo-kit.zip)

사용자가 확인한 현재 상태는 **DeDRM 완료 문서 약 6.1만 건·95GB**, **WeKnora 파서·청커 포팅**, **이미지 추출 후 PaddleOCRv5**, **2026-09-15 기준 7,585,436개 청크 임베딩 완료**, **기존 Milvus에 별도 샤드 설정 없음**이다. 남은 작업은 **프로덕션 컬렉션 이관, 메타데이터 보강, 샤드·인덱스 및 성능 검증**이다. FastAPI와 사내 GLM-5.3-Flash를 사용하며, 기존 G-HeSS 검색 API 재사용은 검토 중이다. 1차 오픈 예상 이용자는 **09~18시 약 1,500명**으로, 산정에서는 일일 이용자 수로 해석했다.

임베딩 모델은 **BGE-M3**, 현재 유사도 척도는 **COSINE**으로 사용자 확인됐다. BGE-M3의 표준 dense 출력은 1,024차원이다. 실제 컬렉션의 차원·저장 dtype·전처리 설정과 dense 외 출력 보존 여부는 별도 확인한다. [BGE-M3 모델 카드](https://huggingface.co/BAAI/bge-m3).

다음 단계는 원본 서버의 새 컬렉션에서 메타데이터 구조를 정한 뒤 **기존 벡터와 COSINE을 유지해 프로덕션 서버로 이관하고 검증 후 전환**하는 안이다. 기존 벡터의 생성 계약·무결성이 불확실하면 동일 로직 전체 재임베딩을 pilot 비교한다. 샤드 1/2개와 HNSW 등의 비교값은 실험 후보이며, 실제 저장 형식·서버 사양이 확인돼야 확정할 수 있다.

최신 보수 혼합 시나리오는 온라인 **LLM 동시 호출 1,300개·924 RPM·합산 664.4만 TPM**과 첨부·질의 임베딩 **2,167.5만 TPM**을 요구한다. 사내 할당량이 아니라 계획 요구량이다. CPU OCR만 176 vCPU·352GiB이므로 실측 처리량·첨부/OCR 비율에 매우 민감하다. 서버를 늘려도 사내 모델 쿼터가 함께 늘어나지 않는다.

2026-09-29의 [1차 오픈 계획](docs/1차_오픈_용량_계획.md)과 기존 `capacity/inputs.json`·`estimate.py`는 검색·짧은 답변 중심의 과거 비교 기준으로 보존한다. 해당 문서의 API+Milvus 38 vCPU·268GiB 및 모델 쿼터를 최신 첨부·문서 생성 계획과 합산하지 않는다.

계산기는 Python 표준 라이브러리만 사용하며 외부 서비스에 접속하지 않는다.

```bash
python3 capacity/estimate.py --output docs/산정_결과.md
python3 capacity/estimate.py --json
python3 capacity/workflow_estimate.py
python3 capacity/workflow_report.py
python3 -m unittest discover -s capacity -v
```

Word 보고서는 생성된 Markdown에서 내보낸다. `workflow_inputs.json`의 가정을 수정한 뒤 `workflow_report.py`로 Markdown·JSON을 갱신하고, 보고서의 스냅샷 설명·운영 정책도 점검한다. DOCX 내보내기에만 별도 의존성이 필요하다.

```bash
python3 -m pip install -r capacity/requirements-docx.txt
python3 capacity/workflow_report.py
python3 capacity/export_docx.py
```

현재 폴더에는 실제 서비스 구현 코드가 없어, 구현 현황은 사용자 설명을 근거로 기록했다. 실제 모델 성능·Milvus 설정·API 계약을 검증한 운영 확정판은 아니다.

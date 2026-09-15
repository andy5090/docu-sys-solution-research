# GHeSS 문서 AI 솔루션 재설계

2026-09-14 기준. 기존 PDF의 전제를 현재 구현과 사내 제약에 맞춰 갱신한 설계안이다. 원본 PDF는 보존했다.

- [새 설계: 현재 구현, FastAPI 로직, 검색 API 연계, Milvus 운영, 단계별 전환](docs/GHeSS_솔루션_재설계.md)
- [트래픽·리소스 산정 방법과 실측 계획](docs/트래픽_리소스_산정.md)
- [시나리오별 계산 결과](docs/산정_결과.md)
- [산정 입력값](capacity/inputs.json)

사용자가 확인한 현재 상태는 **DeDRM 완료 문서 약 6.1만 건·95GB**, **WeKnora 파서·청커 포팅**, **이미지 추출 후 PaddleOCRv5**, **Milvus 임베딩 적재**, **별도 샤드 설정 없음**이다. FastAPI와 사내 GLM-5.3-Flash를 사용하며, 기존 G-HeSS 검색 API 재사용은 검토 중이다. 예상 이용자는 **08~18시 약 1,500명**으로, 산정에서는 일일 이용자 수로 해석했다.

기준 시나리오(1인당 5질문/일, 피크 5배, 생성 비율 75%, 모델 평균 점유 30초)에서는 약 **63질문/분**, 온라인용 **LLM 동시 호출 36개·71 RPM·합산 약 30.9만 TPM**의 배정이 필요하다. 실측 사양이 아닌 가정 기반 요구량이다. 서버를 늘려도 사내 모델의 쿼터는 늘어나지 않는다.

계산기는 Python 표준 라이브러리만 사용하며 외부 서비스에 접속하지 않는다.

```bash
python3 capacity/estimate.py --output docs/산정_결과.md
python3 capacity/estimate.py --json
python3 -m unittest discover -s capacity -v
```

현재 폴더에는 실제 서비스 구현 코드가 없어, 구현 현황은 사용자 설명을 근거로 기록했다. 실제 모델 성능·Milvus 설정·API 계약을 검증한 운영 확정판은 아니다.

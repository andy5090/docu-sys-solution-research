"""Generate the current Markdown report and JSON from workflow_inputs.json."""
from __future__ import annotations

import copy
import json
from pathlib import Path

from workflow_estimate import calculate, up

ROOT = Path(__file__).resolve().parents[1]


def table(headers, rows):
    return "\n".join(["| " + " | ".join(headers) + " |", "|" + "---|"*len(headers)] +
                     ["| " + " | ".join(str(x) for x in row) + " |" for row in rows])


def report(d, r):
    t, a, g, m, s = [d[k] for k in ("traffic", "attachments", "generation", "model", "storage")]
    f = lambda x: f"{x:,.0f}"
    worker_rows = [[w["name"], f'{w["vcpu"]} vCPU / {w["ram_gib"]}GiB', w["count"], f'{w["total_vcpu"]} / {w["total_ram_gib"]}'] for w in r["workers"]]
    fixed_rows = [[w["name"], f'{w["vcpu"]} vCPU / {w["ram_gib"]}GiB', w["count"], f'{w["vcpu"]*w["count"]} / {w["ram_gib"]*w["count"]}'] for w in d["fixed_services"]]
    demands = [[w["name"], f'{w["rate"]:.1f}', f'{w["required_cpu"]:.2f}', w["required_slots"]] for w in r["workers"]]
    scenarios = [("예상 피크", calculate(d, r["expected_peak_qps"])), ("보수 준비", r), ("2배 집중", calculate(d, t["stress_qps"]))]
    sensitivity_rows = [[name, f'{x["qps"]:.3f}', f'{x["total_vcpu"]} / {x["total_ram_gib"]}', f(x["model_concurrency"])] for name, x in scenarios]
    all_ocr = copy.deepcopy(d)
    all_ocr["attachments"]["ocr_page_share"] = 1
    all_ocr_r = calculate(all_ocr)
    all_drm = copy.deepcopy(d)
    all_drm["attachments"]["dedrm_share"] = 1
    all_drm_r = calculate(all_drm)
    long_store = copy.deepcopy(d)
    long_store["attachments"]["retention_days"] = 90
    long_store_r = calculate(long_store)
    host_cpu = up(r['host_vcpu_min']/32)*32
    host_ram = up(r['host_ram_gib_min']/64)*64
    return f"""# G-HeSS AI Agent
## 첨부·DeDRM·문서 생성 포함 보수적 서버 용량

기준일: {d['as_of']} | 문서 버전: 2.0 | Milvus 전체 자원 산정 제외

### 1. 재산정 결론

사용자 요청에 따라 파일 첨부, 필요 시 DeDRM, 파싱·OCR·임베딩 요청, 긴 문서 초안 작성, DOCX/PPTX 조립·미리보기·다운로드를 포함했다. 기존 검색·짧은 답변 중심의 38 vCPU·268GiB 합계를 이번 산정에 사용하지 않는다. Milvus의 CPU·RAM·디스크·보조 서비스는 모두 재산정 대상에서 제외했다.

**보수 준비 목표 {r['qps']}요청/초에서 애플리케이션·CPU 작업자·DB 등 역할별 할당 합계는 {r['total_vcpu']} vCPU / {r['total_ram_gib']}GiB다.** OS·플랫폼 예약 {d['host_reserve_fraction']:.0%}까지 별도로 확보하면 기반 호스트 풀은 최소 {r['host_vcpu_min']} vCPU / {r['host_ram_gib_min']}GiB가 필요하다. 현재 스냅샷의 편성 예산은 **{f(host_cpu)} vCPU / {f(host_ram)}GiB 이상**으로 올려 잡는다. VM/컨테이너 풀 합계이며 물리 서버 대수·물리 코어 수가 아니다.

| 별도 준비 항목 | 보수 계획량 |
|---|---|
| 신규 첨부·결과·메타·백업 논리 저장소 | {r['allocated_tib']:.2f}TiB → {r['rounded_storage_tib']}TiB 준비 |
| 파일 작업자 로컬 임시 SSD | 역할별 합계 {f(r['worker_scratch_gib'])}GiB, OS·DB 디스크 별도 |
| 사내 LLM 온라인 쿼터 | 동시 {f(r['model_concurrency'])} / {f(r['model_rpm'])} RPM / 합산 {f(r['model_total_tpm'])} TPM |
| 사내 임베딩 쿼터 | 첨부 {f(r['embedding_chunks_per_second'])}청크/초 + 질의 {r['query_embeddings_per_second']:.2f}건/초, {f(r['embedding_tpm'])} TPM |

LLM·임베딩은 사내 추론 서비스를 이용하는 전제다. **그 추론 서버 CPU/GPU는 위 합계에 포함되지 않는다.** 자체 추론이 필요하면 모델·하드웨어 실측으로 별도 산정한다. 객체 저장소 하드웨어와 네트워크 장비도 역할별 CPU/RAM 합계 밖이다.

### 확정 정보와 보수적 가정

확정 입력은 약 {f(t['daily_users'])}명/일, 09~18시 {t['service_hours']}시간, Milvus 제외 요청이다. 나머지는 실측 전 계획 가정이다. 총 {f(r['daily_requests'])}요청/일 중 첨부 비율 {a['request_share']:.0%}·첨부당 {a['files_per_request']}파일, 초안 비율 {g['request_share']:.0%}를 가정한다. 즉 신규 파일 **{f(r['daily_files'])}개/일**, 초안 **{f(r['daily_jobs'])}건/일**까지 보는 높은 사용량이다. 실제 수요 확인 없이 이 수치를 구매 확정량으로 해석하지 않는다.

<!-- pagebreak -->

## 2. 요청·첨부·초안의 부하 가정

{table(['항목', '가정', '해석'], [
['요청 빈도', f'1인당 {t["requests_per_user"]}회/일', '검색·답변 또는 초안 생성 요청의 합계'],
['평균 / 예상 피크', f'{r["average_qps"]:.3f} / {r["expected_peak_qps"]:.3f} QPS', f'9시간 평균의 {t["peak_factor"]}배'],
['준비 / 집중 시험', f'{t["target_qps"]} / {t["stress_qps"]} QPS', '피크를 9시간 내내 유지하는 일일량은 아님'],
['첨부', f'{a["request_share"]:.0%}, {a["files_per_request"]}개 × {a["mb_per_file"]}MB', f'파일당 평균 {a["pages_per_file"]}페이지'],
['DeDRM / OCR', f'파일 {a["dedrm_share"]:.0%} / 페이지 {a["ocr_page_share"]:.0%}', '서로 독립 비율, 같은 파일에서 모두 수행 가능'],
['문서 초안', f'{g["request_share"]:.0%}, DOCX {g["docx"]["share"]:.0%} / PPTX {g["pptx"]["share"]:.0%}', f'DOCX {g["docx"]["pages_or_slides"]}쪽 / PPTX {g["pptx"]["pages_or_slides"]}장'],
['CPU/모델 목표 이용률', f'{d["utilization"]:.0%}', '평균 작업 비용 기준에 40% 비점유 여유'],
])}

일반 답변과 초안 요청은 각각 80%·20%로 배타적이다. 첨부 30%는 두 요청 종류에 걸쳐 겹칠 수 있는 속성이다. 따라서 첨부를 제3의 별도 요청으로 더하지 않으며, 초안에 대해 일반 채팅 생성 호출을 중복 가산하지 않는다. 첨부 재사용·캐시 적중·중복 제거로 얻는 절감은 0으로 둔다.

### 작업당 CPU 시간·점유 시간

| 작업 | CPU 시간 가정 | 작업 슬롯 점유 가정 |
|---|---|---|
| DeDRM 대상 파일 | 2 core-second/파일 | 5초/파일, SDK·I/O 대기 포함 |
| 파싱·이미지 추출 | 0.3 core-second/페이지 = 9/파일 | 12초/파일 |
| CPU OCR | 2 core-second/OCR 페이지 | 2초/페이지, 단일 코어 환산 |
| DOCX 조립·미리보기 | 8 core-second/결과 | 10초/결과 |
| PPTX 조립·미리보기 | 20 core-second/결과 | 30초/결과 |

실측 성능이나 라이브러리 벤치마크가 아니다. 템플릿·표·기존 이미지·차트 삽입과 선택적 미리보기까지 위한 예산이다. 생성형 이미지·영상 제작은 포함하지 않는다. OCR은 페이지를 처리 작업의 대용 단위로 사용했으므로 이미지 수·해상도별 실제 비용으로 반드시 교체한다.

{r['qps']} QPS에서는 첨부 {r['files_per_second']:.1f}파일/초, 파싱 {r['pages_per_second']:.0f}페이지/초, OCR {r['ocr_pages_per_second']:.0f}페이지/초, 초안 {r['jobs_per_second']:.1f}건/초를 동시에 준비한다. 100% 스캔 문서 집중 및 큰 파일은 뒤의 민감도·입장 제한 기준을 따른다.

<!-- pagebreak -->

## 3. 서버·작업자별 자원 요청안

{table(['역할', '개별 할당', '개수', '합계 vCPU / GiB'], fixed_rows[:2] + worker_rows + fixed_rows[2:])}

**역할 합계: {r['total_vcpu']} vCPU / {r['total_ram_gib']}GiB.** 기존 RDB·Redis·관측 서비스를 재사용하면 그 역할의 신규 할당량을 차감한다. Redis는 3개 장애 영역의 데이터 복제·감시 프로세스를 수용하는 임시 예산이며 실제 토폴로지와 승격 정책을 확정해야 한다. RDB는 primary가 쓰기 부하 전체를 처리하는 조건이다.

### 작업자 대수 산정식

필요 CPU = 초당 작업 × 작업당 core-second ÷ 0.6. 필요 슬롯 = ceil(초당 작업 × 작업당 점유 초 ÷ 0.6). 필요한 활성 작업자 = max(ceil(필요 CPU ÷ 개별 vCPU), ceil(필요 슬롯 ÷ 개별 슬롯)). 여기에 **예비 작업자 1개**를 더한다. CPU와 I/O 대기·메모리 제약을 함께 반영한다.

{table(['작업', '초당 작업', '필요 CPU', '필요 슬롯'], demands)}

DeDRM/파싱/OCR/조립의 개별 동시 슬롯은 각각 8/16/16/8개다. 슬롯당 RSS는 0.5/1/1/2GiB, 프로세스 여유는 2/4/4/4GiB로 가정해 개별 RAM 안에 들어가는지 계산기가 확인한다. OCR·변환 라이브러리의 내부 스레드와 프로세스 수를 함께 제한한다.

API·작업 조정·DB·Redis·관측 사양은 부하 시험 시작값이다. 초안 요청은 202 + job ID로 접수하고 LLM 대기와 렌더링을 분리한다. 계획상 활동 초안은 약 {r['planned_active_jobs']}개이므로 조정 서비스는 공유 상태 저장소 기반으로 전체 1,200개 활성 작업, 한 개 중단 시 잔여 두 개 각 600개를 검증한다. 진행 조회 10초 간격에서도 평균 약 {r['poll_rps']:.1f} RPS가 추가되며 이를 API 시험에 포함한다.

<!-- pagebreak -->

## 4. LLM 및 임베딩 요구량

### 짧은 답변과 긴 초안을 분리

| 경로 | 호출 및 입력 가정 | 출력 합계 가정 |
|---|---|---|
| 일반 답변 80% | 질문당 평균 1.1회, 호출당 6,000토큰 | 호출당 800토큰 |
| DOCX 초안 | 기본 4회, 호출당 6,000토큰 | 기본 작업 전체 6,000토큰 |
| PPTX 초안 | 기본 5회, 호출당 6,000토큰 | 기본 작업 전체 8,000토큰 |

초안은 계획·본문·검토 등 전체 호출과 중간 출력을 포함한 토큰 예산이다. 결과 쪽 수·장 수에 필요한 실제 토큰은 템플릿·언어로 검증한다. 초안 호출·입출력·점유에는 재시도 계수 1.1을 곱한다. 일반 답변의 1.1회에도 재시도 예산이 들어 있다. 첫 토큰 10초, 출력 16 tok/s로 계산하고 평균 30초의 기존 모델 가정을 폐기한다.

{table(['5 QPS 혼합 요청의 온라인 배정', '요구량', '적용 범위'], [
['동시 모델 호출', f(r['model_concurrency']), '일반 답변 + 초안, 평균 점유 기준'],
['RPM', f(r['model_rpm']), '모든 호출 경로·레플리카 합산'],
['입력 TPM', f(r['model_input_tpm']), '반복 컨텍스트 포함'],
['출력 TPM', f(r['model_output_tpm']), '중간 작성·검토·재시도 출력 포함'],
['합산 TPM', f(r['model_total_tpm']), '분리/합산 제한은 사내 계약에 맞춰 적용'],
])}

동시 호출 = ceil((초당 일반 호출 × 평균 답변 점유 + 초당 초안 × 작업당 모델 점유 합계) ÷ 0.6). RPM·TPM도 합산 수요를 0.6으로 나눠 올림한다. 이용률 여유를 다시 중복 가산하지 않는다. 제공자가 최대 출력·추론 토큰으로 쿼터를 예약하면 그 계약 기준으로 추가 보정해야 한다. 실제 온라인 할당량은 미확인이므로 현재 처리 가능 여부를 확정하지 않는다.

초안당 모델 점유 합계 평균은 {r['model_seconds_per_job']:.1f}초다. 순차 호출·조립·기타 처리까지 계획 평균 약 {r['job_active_seconds']/60:.1f}분이며 첨부 전처리·큐 대기는 별도다. 기존 일반 답변 p95 60초를 긴 초안에 그대로 적용하지 않는다. 초안은 접수 후 비동기로 처리하고 실제 완료시간을 표시한다.

### 첨부 임베딩은 별도 추론 쿼터

30페이지 × 6청크 = 파일당 180청크, 청크당 400토큰을 가정한다. 3파일/초이면 첨부 540청크/초·12,960,000 TPM이 실제 수요다. 이용률 60% 반영 시 **900청크/초**, 질의 임베딩 **8.33건/초**, 합산 **21,675,000 TPM** 배정이 필요하다. 질의 입력은 150토큰, 모든 고수준 요청에 1회로 보수 가정한다. 청크 처리량과 TPM을 모두 충족해야 하며 RPM·배치 크기·최대 동시성은 endpoint 계약으로 추가 확인한다. Milvus 자체의 적재·저장 자원은 계산하지 않는다.

<!-- pagebreak -->

## 5. 저장소·임시 디스크·네트워크

### 신규 파일의 보관량

원본은 하루 {r['raw_upload_gb_per_day']:.0f}GB 증가한다. 원본 1배 + DeDRM 사본 0.5배 + 추출 이미지·텍스트 1배를 30일 보관한다. 결과물은 DOCX 4MB/PPTX 12MB, 평균 7.2MB로 90일 보관한다. 메타·작업 이력·감사 로그는 요청당 50KiB × 90일이다. 주말도 같은 일일량으로 가정하고 압축·중복 제거 절감은 반영하지 않는다.

{table(['항목', '계산 결과', '비고'], [
['첨부 원본·해제본·파생물', f'{r["attachment_retained_tib"]:.3f}TiB', '30일, 원본 대비 합계 2.5배'],
['DOCX/PPTX 생성 결과', f'{r["artifact_retained_tib"]:.3f}TiB', '90일'],
['메타·작업·감사 로그', f'{r["metadata_log_tib"]:.3f}TiB', '90일, 원문 전체 로깅 제외'],
['상시 논리 저장', f'{r["live_tib"]:.3f}TiB', '위 항목 합계'],
['독립 백업', f'{r["live_tib"]:.3f}TiB', '한 세트, 다세대 백업은 별도'],
['여유 포함 전체', f'{r["allocated_tib"]:.2f}TiB', '(상시 + 백업) ÷ 0.7'],
['할당 제안', f'{r["rounded_storage_tib"]}TiB', '운영 저장소와 독립 백업에 분리 배정'],
])}

24TiB는 논리 저장소와 백업 합계이며 단일 디스크·단일 장애 영역에 배치하지 않는다. 스토리지 물리 복제/EC 계수, DB WAL, 장기 백업 정책은 소유 서비스에서 추가한다. 기존 95GB 지식베이스와 Milvus 저장량은 이 표에 포함하지 않는다. 보관 만료 삭제가 동작해야 이 정상상태 용량을 유지한다.

### 로컬 작업 공간과 통신

DeDRM 100GiB × 3, 파싱 100GiB × 5, OCR 100GiB × 11, 조립 200GiB × 5 = **{f(r['worker_scratch_gib'])}GiB**의 로컬 임시 SSD를 별도로 준비한다. 이 값은 파일별 전개 크기 실측 전 시작 예산이다. 작업별 임시 공간 상한·완료/실패 정리·여유 공간 감시를 둔다. OS·DB 볼륨은 별도이며, 대기 중 파일은 RAM/로컬 임시 공간 대신 객체 저장소에 둔다.

업로드 30MB/s, 결과물 2회 다운로드 14.4MB/s를 합쳐 355.2Mbps 수요다. 이용률 60%로 **{r['external_mbps']:.0f}Mbps**를 준비하고 외부 경로는 **1Gbps급 이상**, 내부 전송 3배 예산 **{r['internal_mbps']/1000:.3f}Gbps**를 고려해 **10Gbps급 내부 연결**을 시작점으로 둔다. 양방향 합계로 보수 계산했으며 풀듀플렉스 링크는 방향별로도 검증한다. 실제 OCR 파생물 I/O·백업 창의 속도는 따로 측정한다.

<!-- pagebreak -->

## 6. 민감도와 운영 제한

{table(['조건', 'QPS', '역할 vCPU / GiB', 'LLM 동시 호출'], sensitivity_rows)}

비율·파일 크기·작업 비용은 같고 순간 도착률만 바꾼 표다. 보관량은 일일 15,000요청 기준이므로 피크 QPS를 올렸다는 이유로 다시 배수 적용하지 않는다. 10 QPS는 스트레스 조건이며 5 QPS 구성의 보장 범위가 아니다. 표에서 API·DB 등 고정 시작 사양은 유지했으므로 고부하에서는 별도 검증한다.

| 추가 조건 | 영향 |
|---|---|
| OCR 비율 50% → 100% | 역할 합계 {all_ocr_r['total_vcpu']} vCPU / {all_ocr_r['total_ram_gib']}GiB |
| DeDRM 비율 50% → 100% | 역할 합계 {all_drm_r['total_vcpu']} vCPU / {all_drm_r['total_ram_gib']}GiB, 논리 저장 {all_drm_r['allocated_tib']:.2f}TiB |
| 모델 점유 시간 전체 2배 | 동시 호출 약 {f(r['model_concurrency']*2)}개, 토큰·호출 수 동일 시 RPM/TPM 동일 |
| 첨부 보관 30일 → 90일 | 전체 논리 할당 {long_store_r['allocated_tib']:.2f}TiB |

OCR이 기준안에서 176 vCPU·352GiB를 차지하는 이유는 45페이지/초 × 2 core-second ÷ 0.6 = 150코어 요구량에 16 vCPU 작업자 단위 올림과 예비 1개를 더했기 때문이다. GPU 가속의 절감량은 벤치마크 없이 가정하지 않는다. 현행 OCR 장비의 실측 총 처리량이 있으면 CPU 풀을 그 서비스로 대체해 신규 할당분을 줄일 수 있다.

### 이 추정이 성립하는 처리 경계

파일당 평균 10MB·30페이지는 상한이 아니다. 오픈 정책 초안은 첨부 2개/요청, 파일당 50MB·100페이지까지이며 상한 부근 파일은 별도 긴 작업 큐로 분리한다. 큰 파일이 집중되면 이 평균 비용 산정을 초과하므로 파일 수 외에 대기 페이지 수·OCR 예상 작업량·토큰으로 입장을 제한한다. 제시 상한을 전 요청이 사용하는 부하까지 보장한 수치가 아니다.

DeDRM SDK/외부 서비스 동시 실행·라이선스 한도는 별도 병목이다. 기준 필요 슬롯은 13개, 배치된 3작업자의 설정상 슬롯은 24개다. 전역 한도를 제공자 계약 이하로 두고 13개 미만이면 목표 도착률을 줄이거나 대기를 허용한다. SDK가 Windows 등 특정 OS를 요구하면 해당 역할만 호환 실행 환경에 배치한다.

일반 답변·초안·첨부 임베딩 쿼터를 분리 예약하고 전체 합계를 전역 제어한다. LLM/임베딩 할당량을 확보하지 못하면 CPU 증설만으로 목표 처리량을 만족할 수 없다. 기존 300건/일 지식베이스 증분 작업은 온라인 풀과 겹치지 않는 야간 처리 전제이며, 겹치면 별도 작업량을 합산한다.

<!-- pagebreak -->

## 7. 검증·확정 절차

| 단계 | 시험 및 판단 |
|---|---|
| 작업 비용 실측 | DRM/비DRM·스캔/텍스트·표/이미지별 최소 100파일. core-second·wall time·최대 RSS·임시 디스크 기록 |
| 문서 생성 실측 | DOCX 10쪽/PPTX 20장, 표·차트·이미지 포함 각 30건. 전체 모델 호출/토큰, 조립·미리보기 RSS 측정 |
| 혼합 부하 | 30% 첨부·20% 초안, 3.704→5 QPS. 예열 후 30분 이상, 기준 2시간 안정성 확인 |
| 장애 여유 | 각 작업자 풀에서 한 개 중단. 평균 CPU·슬롯 점유 60% 이하 계획 및 큐 적체 지속 증가 여부 확인 |
| API·작업 조정 | 모델 모사/실제 쿼터 시험 분리. API 1개 중단, 1,200 활성 초안과 10초 진행 조회 시험 |
| 저장소·네트워크 | 최대 파일 전개, 업/다운로드 동시, 야간 백업, 삭제 정책과 디스크 고갈 회복 확인 |
| 결과 품질 | 생성 DOCX/PPTX를 실제 뷰어로 열어 표·차트·글꼴·출처·페이지/슬라이드 누락 확인 |

요청 접수 p95 2초(파일 전송 시간 제외), 일반 답변 p95 120초, DOCX/PPTX 초안 p95 15분(필요 첨부 업로드 완료 이후)을 초기 목표로 제안한다. 평균 모델·작업 시간 계산이 p95 보장을 뜻하지 않는다. 큐 대기·첨부 전처리까지 목표에 포함해 실측 후 조정한다. 실패·재시도·시간초과에서 중복 모델 호출과 중복 산출물이 생기지 않는지도 확인한다.

N+1은 **해당 역할 작업자 1개 장애** 기준이다. 한 물리 호스트에 여러 작업자가 올라가 있다면 그 호스트 장애는 별도 시나리오다. 20% 플랫폼 예약만으로 호스트 전체 장애 복구 자원이 보장되지 않는다. 장애 영역별 배치·실제 호스트 크기·복구 SLO를 확인한 뒤 물리 서버 대수를 정한다.

## 8. 근거 및 재현

내부 입력: capacity/workflow_inputs.json. 계산: capacity/workflow_estimate.py. 수치 스냅샷: capacity/workflow_result.json. 보고서 생성: capacity/workflow_report.py. 모든 사용 비율·CPU 비용·사양은 모델링 가정이며 공식 문서의 성능 보장값이 아니다.

- [FastAPI 파일 업로드](https://fastapi.tiangolo.com/tutorial/request-files/): UploadFile의 메모리/디스크 스풀 동작을 고려해 업로드를 제한한다.
- [FastAPI Background Tasks](https://fastapi.tiangolo.com/tutorial/background-tasks/): 무거운 처리는 별도 프로세스·작업 큐 구성을 검토한다. 본 산정은 영속 작업 큐와 별도 작업자를 전제한다.
- [python-docx](https://python-docx.readthedocs.io/en/latest/) 및 [python-pptx](https://python-pptx.readthedocs.io/en/latest/): 파일 작성 기능의 참고 문서이며 처리 속도의 근거는 아니다. 실제 제품 라이브러리는 미확정이다.

외부 문서 확인일: {d['as_of']}. DeDRM SDK, 사내 GLM/임베딩, 실제 서비스 서버에는 접속하지 않았고 부하 시험도 수행하지 않았다.

재생성 순서: `python3 capacity/workflow_report.py` → `python3 capacity/export_docx.py`. 테스트: `python3 -m unittest discover -s capacity -v`. Markdown과 JSON은 자동 생성되므로 가정 변경 시 입력 JSON과 보고서 생성 문구를 함께 점검한다. 기존 capacity/inputs.json·estimate.py와 검색 중심 문서는 과거 비교 기준으로 보존하며 이번 신규 할당량과 합산하지 않는다.
"""


def main():
    d = json.loads((ROOT / "capacity/workflow_inputs.json").read_text())
    r = calculate(d)
    (ROOT / "capacity/workflow_result.json").write_text(json.dumps(r, ensure_ascii=False, indent=2)+"\n")
    path = ROOT / "docs/권장_서버_용량_추정.md"
    path.write_text(report(d, r))
    print(f"Saved {path.relative_to(ROOT)} and capacity/workflow_result.json")


if __name__ == "__main__":
    main()

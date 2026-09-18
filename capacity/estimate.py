"""Planning arithmetic only. No model, DRM, database, or network calls; stdlib only."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

GIB = 2**30


def ceil_units(value):
    """Round integer planning units up, ignoring at most four ULPs of arithmetic noise."""
    nearest = round(value)
    return nearest if abs(value - nearest) <= 4 * math.ulp(value) else math.ceil(value)


def number(value, name, *, minimum=0, positive=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{name}: finite number required")
    if value < minimum or (positive and value <= 0):
        raise ValueError(f"{name}: value out of range")


def validate(data):
    for section in ("facts", "online", "storage", "ingestion"):
        for key, value in data[section].items():
            if isinstance(value, (dict, list)):
                if section == "facts" and key == "chunks":
                    raise ValueError("facts.chunks: nonnegative integer or null required")
                continue
            if section == "facts" and key == "chunks" and value is None:
                continue
            number(value, f"{section}.{key}")
    chunks = data["facts"].get("chunks")
    if chunks is not None:
        if not isinstance(chunks, int):
            raise ValueError("facts.chunks: nonnegative integer or null required")
        if chunks > 0 and data["facts"]["documents"] == 0:
            raise ValueError("positive chunks require a positive document count")
    for key in ("service_hours",):
        number(data["facts"][key], key, positive=True)
    if data["facts"]["service_hours"] > 24:
        raise ValueError("service_hours must be <=24")
    for key in ("target_utilization",):
        if not 0 < data["online"][key] < 1:
            raise ValueError(f"{key} must be between 0 and 1")
    number(data["online"]["mean_output_tokens_per_second"], "output rate", positive=True)
    for key in ("input_tokens_per_call", "output_tokens_per_call"):
        number(data["online"][key], key, positive=True)
    for key in ("milvus_memory_utilization", "storage_free_fraction"):
        if not 0 < data["storage"][key] < 1:
            raise ValueError(f"{key} must be between 0 and 1")
    for key in ("embedding_dimensions", "bytes_per_dimension", "embedding_tokens_per_chunk", "query_replicas", "keyword_storage_copies"):
        number(data["storage"][key], key, positive=True)
    for key in ("milvus_resident_vector_factor", "milvus_persisted_vector_factor", "retained_revision_factor"):
        number(data["storage"][key], key, minimum=1)
    for section in ("online", "storage"):
        if not data[section]["scenarios"]:
            raise ValueError(f"{section}: scenarios required")
        for scenario in data[section]["scenarios"]:
            for key, value in scenario.items():
                if key != "name":
                    number(value, key)
    for scenario in data["online"]["scenarios"]:
        if not 0 <= scenario["llm_share"] <= 1:
            raise ValueError("llm_share must be between 0 and 1")
        number(scenario["peak_factor"], "peak_factor", minimum=1)
        number(scenario["calls_per_generated_query"], "calls_per_generated_query", minimum=1)
    for key, value in data["online"]["allocated_limits"].items():
        if value is not None:
            number(value, key)
    ing = data["ingestion"]
    if not 0 < ing["effective_utilization"] <= 1 or not 0 <= ing["ocr_page_fraction"] <= 1:
        raise ValueError("invalid ingestion utilization or OCR fraction")
    if not 0 < ing["batch_hours_per_day"] <= 24:
        raise ValueError("batch_hours_per_day must be in (0,24]")
    for key in ("read_megabytes_per_second", "parse_cpu_seconds_per_page", "parse_cores", "ocr_cpu_seconds_per_page", "ocr_cores", "embedding_chunks_per_second", "embedding_tpm", "index_chunks_per_second"):
        number(ing[key], key, positive=True)


def online(data, scenario):
    f, a = data["facts"], data["online"]
    u = a["target_utilization"]
    daily = f["daily_users"] * scenario["questions_per_user"]
    avg_qps = daily / (f["service_hours"] * 3600)
    peak_qps = avg_qps * scenario["peak_factor"]
    multiplier = scenario["llm_share"] * scenario["calls_per_generated_query"]
    call_rps = peak_qps * multiplier
    service = a["mean_ttft_seconds"] + a["output_tokens_per_call"] / a["mean_output_tokens_per_second"]
    rpm = call_rps * 60
    input_tpm = rpm * a["input_tokens_per_call"]
    output_tpm = rpm * a["output_tokens_per_call"]
    mean_request = scenario["llm_share"] * (service * scenario["calls_per_generated_query"] + a["other_generated_seconds"]) + (1 - scenario["llm_share"]) * a["no_llm_seconds"]
    limits = a["allocated_limits"]
    denominators = {"concurrent_calls": service, "rpm": 60, "input_tpm": 60 * a["input_tokens_per_call"], "output_tpm": 60 * a["output_tokens_per_call"], "total_tpm": 60 * (a["input_tokens_per_call"] + a["output_tokens_per_call"])}
    ceilings = {key: value / denominators[key] * u for key, value in limits.items() if value is not None}
    return {
        "name": scenario["name"], "daily_questions": daily, "average_qps": avg_qps,
        "peak_qps": peak_qps, "peak_qpm": peak_qps * 60,
        "llm_rpm": rpm, "daily_llm_calls": daily * multiplier,
        "input_tpm": input_tpm, "output_tpm": output_tpm,
        "required_input_tpm": ceil_units(input_tpm / u), "required_output_tpm": ceil_units(output_tpm / u),
        "required_total_tpm": ceil_units((input_tpm + output_tpm) / u),
        "required_rpm": ceil_units(rpm / u), "mean_model_seconds": service,
        "required_concurrent_calls": ceil_units(call_rps * service / u),
        "mean_active_model_calls": call_rps * service,
        "mean_active_http_requests": peak_qps * mean_request,
        "planned_http_slots": ceil_units(peak_qps * mean_request / u),
        "slot_sensitivity": {str(s): ceil_units(call_rps * s / u) for s in (15, 30, 60, 90)},
        "known_limit_bottleneck": min(ceilings, key=ceilings.get) if ceilings else None,
        "known_limits_supported_qps_ceiling": min(ceilings.values()) / multiplier if ceilings and multiplier else None,
        "quota_status": "미확인" if not ceilings else "확인된 한도만 반영한 상한; 미확인 한도와 지연 실측 필요",
    }


def storage(data, scenario):
    f, a = data["facts"], data["storage"]
    pages = f["documents"] * scenario["pages_per_document"]
    reported_chunks = f.get("chunks")
    chunks = reported_chunks if reported_chunks is not None else pages * scenario["chunks_per_page"]
    raw = chunks * a["embedding_dimensions"] * a["bytes_per_dimension"]
    scalar = chunks * a["milvus_scalar_bytes_per_chunk"]
    retained = a["retained_revision_factor"]
    # Load the selected chunk set once per replica; retained data adds storage headroom only.
    memory = (raw * a["milvus_resident_vector_factor"] + scalar) / GIB / a["milvus_memory_utilization"] + a["milvus_process_overhead_gib_per_replica"]
    objects = (f["source_gb"] * 1e9 * (1 + scenario["extracted_asset_source_ratio"]) + chunks * a["normalized_bytes_per_chunk"]) * retained
    milvus = (raw * a["milvus_persisted_vector_factor"] + scalar) * retained
    keyword = chunks * a["keyword_index_bytes_per_chunk"] * a["keyword_storage_copies"] * retained
    metadata = (chunks * a["rdb_bytes_per_chunk"] + f["documents"] * a["rdb_bytes_per_document"]) * retained
    live = objects + milvus + keyword + metadata
    rebuild = (milvus + keyword) * a["extra_index_generations"]
    backups = live * a["independent_backup_copies"]
    return {
        "name": scenario["name"], "pages": pages, "chunks": chunks,
        "chunks_source": "reported" if reported_chunks is not None else "estimated",
        "raw_vector_gib": raw / GIB, "milvus_gib": milvus / GIB,
        "query_ram_gib_per_replica": memory, "query_ram_gib_all_replicas": memory * a["query_replicas"],
        "objects_gib": objects / GIB, "keyword_gib": keyword / GIB, "metadata_gib": metadata / GIB,
        "live_gib": live / GIB, "rebuild_extra_gib": rebuild / GIB, "backup_gib": backups / GIB,
        "allocated_logical_gib": (live + rebuild + backups) / (1 - a["storage_free_fraction"]) / GIB,
    }


def ingestion(data, stored):
    f, a, s = data["facts"], data["ingestion"], data["storage"]
    u = a["effective_utilization"]
    emb_rate = min(a["embedding_chunks_per_second"], a["embedding_tpm"] / 60 / s["embedding_tokens_per_chunk"])
    hours = {
        "원본 읽기": f["source_gb"] * 1000 / a["read_megabytes_per_second"] / u / 3600,
        "본문 파싱": stored["pages"] * a["parse_cpu_seconds_per_page"] / a["parse_cores"] / u / 3600,
        "OCR": stored["pages"] * a["ocr_page_fraction"] * a["ocr_cpu_seconds_per_page"] / a["ocr_cores"] / u / 3600,
        "임베딩": stored["chunks"] / emb_rate / u / 3600,
        "색인 쓰기": stored["chunks"] / a["index_chunks_per_second"] / u / 3600,
    }
    peak_hours = max(hours.values())
    delta_ratio = a["daily_changed_documents"] / f["documents"] if f["documents"] else 0
    return {
        "name": stored["name"], "stage_hours": hours, "bottleneck": max(hours, key=hours.get),
        "ideal_overlapped_nights": peak_hours / a["batch_hours_per_day"],
        "serial_equivalent_nights": sum(hours.values()) / a["batch_hours_per_day"],
        "embedding_input_tokens": stored["chunks"] * s["embedding_tokens_per_chunk"],
        "daily_delta_bottleneck_hours": peak_hours * delta_ratio,
    }


def calculate(data):
    validate(data)
    disk = [storage(data, scenario) for scenario in data["storage"]["scenarios"]]
    return {"as_of": data["as_of"], "online": [online(data, scenario) for scenario in data["online"]["scenarios"]], "storage": disk, "ingestion": [ingestion(data, result) for result in disk]}


def markdown(data, result):
    f, a, s, ing = data["facts"], data["online"], data["storage"], data["ingestion"]
    chunk_note = f" 사용자 확인 청크 {f['chunks']:,}개." if f.get("chunks") is not None else " 청크 수는 페이지 기반 시나리오로 추정."
    lines = ["# 트래픽·리소스 계산 결과", "", f"기준일: {data['as_of']}. `capacity/inputs.json`에서 자동 계산. 실측 성능 또는 구매 확정 사양이 아니다.", "", f"입력: 일일 사용자 약 {f['daily_users']:,.0f}명, 일 {f['service_hours']}시간, DeDRM 완료 문서 약 {f['documents']:,.0f}건, 파일 약 {f['source_gb']}GB.{chunk_note} GB=10^9 bytes, GiB=2^30 bytes. 나머지는 계획 가정이며 원리와 한계는 [산정 방법](트래픽_리소스_산정.md)을 참조한다.", "", "## 1. 온라인 요청과 모델 쿼터", "", f"평균 모델 시간 = 첫 토큰 {a['mean_ttft_seconds']}초 + 출력 {a['output_tokens_per_call']}토큰 / {a['mean_output_tokens_per_second']} tok/s = {result['online'][0]['mean_model_seconds']:.1f}초. 계획 이용률 {a['target_utilization']:.0%}. 질문 수·피크·생성 비율은 시나리오별 가정.", "", "| 지표 | " + " | ".join(x['name'] for x in result['online']) + " |", "|---|" + "---:|" * len(result['online'])]
    def row(label, key, values, digits=0):
        lines.append("| " + label + " | " + " | ".join(f"{x[key]:,.{digits}f}" for x in values) + " |")
    for label, key, digits in [("하루 질문", "daily_questions", 0), ("평균 QPS", "average_qps", 3), ("피크 질문/분", "peak_qpm", 1), ("피크 LLM 호출/분", "llm_rpm", 1), ("하루 LLM 호출 기대값", "daily_llm_calls", 0), ("피크 입력 TPM 수요", "input_tpm", 0), ("피크 출력 TPM 수요", "output_tpm", 0), ("필요 입력 TPM 배정", "required_input_tpm", 0), ("필요 출력 TPM 배정", "required_output_tpm", 0), ("필요 합산 TPM 배정", "required_total_tpm", 0), ("필요 RPM 배정", "required_rpm", 0), ("필요 LLM 동시 호출 슬롯", "required_concurrent_calls", 0), ("평균 처리 중 HTTP 요청", "mean_active_http_requests", 1), ("계획 HTTP 처리 슬롯", "planned_http_slots", 0)]:
        row(label, key, result["online"], digits)
    lines += ["", "필요 배정량에는 계획 이용률 목표가 반영돼 있다. 다시 여유율을 가산하지 않는다. TPM 분리/합산은 제공자의 실제 계약에 해당하는 항목을 사용한다. 동시 호출 슬롯과 HTTP 슬롯은 서로 다른 자원이다.", "", "### 지연 변화에 따른 LLM 동시 슬롯", "", "| 평균 모델 점유 시간 | " + " | ".join(x['name'] for x in result['online']) + " |", "|---|" + "---:|" * len(result['online'])]
    for seconds in (15, 30, 60, 90):
        lines.append(f"| {seconds}초 | " + " | ".join(str(x["slot_sensitivity"][str(seconds)]) for x in result["online"]) + " |")
    lines += ["", "### 실제 쿼터 입력 상태", ""]
    for item in result["online"]:
        limit = item["known_limits_supported_qps_ceiling"]
        lines.append(f"- {item['name']}: {item['quota_status']}" + (f". 알려진 한도 중 병목={item['known_limit_bottleneck']}, 질문 처리 상한={limit:.3f} QPS." if limit is not None else ". 처리 가능 여부를 판정하지 않음."))
    scope_note = (f"세 시나리오 모두 사용자 확인 청크 {f['chunks']:,}개를 사용한다. 청크당 dense 벡터 1개와 전체 load를 가정하며 이력·삭제·고유 PK 범위는 이관 전에 대사한다. 페이지 수·파생자산 비율은 별도 가정이다."
                  if f.get("chunks") is not None else "청크 수는 문서 수 × 문서당 페이지 × 페이지당 청크의 시나리오 추정값이다.")
    lines += ["", "## 2. 문서·Milvus·저장소", "", scope_note, "", f"임베딩 {s['embedding_dimensions']:,}차원, 차원당 {s['bytes_per_dimension']} bytes, 산정 청크 전체를 메모리에 적재, 질의 복제본 {s['query_replicas']}개 가정. 복제본당 RAM은 해당 데이터 전체의 합산값이며 프로세스 여유 {s['milvus_process_overhead_gib_per_replica']}GiB 포함. 차원 입력의 근거는 [산정 방법](트래픽_리소스_산정.md)을 참조한다. 실제 schema 대조가 필요하며 저장 dtype·색인·메모리 계수는 계획 가정이다.", "", "| 지표 | " + " | ".join(x['name'] for x in result['storage']) + " |", "|---|" + "---:|" * len(result['storage'])]
    for label, key, digits in [("페이지 (가정)", "pages", 0), ("청크 (dense 1개/청크 가정)", "chunks", 0), ("원시 dense 벡터 GiB", "raw_vector_gib", 1), ("Milvus 저장 GiB", "milvus_gib", 1), ("질의 복제본당 RAM GiB", "query_ram_gib_per_replica", 1), ("복제본 2개 RAM 합계 GiB", "query_ram_gib_all_replicas", 1), ("원본·파생 자산 GiB", "objects_gib", 1), ("키워드 색인 GiB", "keyword_gib", 1), ("문서 메타 DB GiB", "metadata_gib", 1), ("상시 논리 저장 GiB", "live_gib", 1), ("재색인 추가 공간 GiB", "rebuild_extra_gib", 1), ("독립 백업 공간 GiB", "backup_gib", 1), ("여유 포함 전체 논리 할당 GiB", "allocated_logical_gib", 1)]:
        row(label.replace("복제본 2개", f"복제본 {s['query_replicas']}개"), key, result["storage"], digits)
    lines += ["", f"개정 보유 계수 {s['retained_revision_factor']}, 재색인 {s['extra_index_generations']}세트, 전체 백업 {s['independent_backup_copies']}세트, 빈 공간 {s['storage_free_fraction']:.0%} 반영. 오브젝트 스토리지 물리 복제/EC, WAL·compaction 임시공간, 대화·감사 로그, 장기 성장, 파서 임시공간은 별도. 질의 복제본 수는 저장소 전체 복제 배수가 아니다. 새 인덱스까지 동시에 load하면 RAM도 추가로 필요하다. 키워드 색인은 서비스 전체 용량 기준으로 포함했으며 기존 G-HeSS API 재사용 시 신규 할당분과 분리한다.", "", "## 3. 전체 재처리 참고 및 증분 적재", "", f"현재 문서는 이미 파싱·OCR·임베딩 적재됨. 다음 표는 동일 규모를 전부 다시 처리할 경우의 비교값으로, 즉시 재적재를 권고하는 일정이 아니다. DeDRM은 완료됐으므로 처리 시간에서 제외. 하루 배치 {ing['batch_hours_per_day']}시간, 효율 {ing['effective_utilization']:.0%} 가정. VLM 판독·문서 요약은 제외.", "", "| 단계별 유효 경과 시간 | " + " | ".join(x['name'] for x in result['ingestion']) + " |", "|---|" + "---:|" * len(result['ingestion'])]
    for stage in result["ingestion"][0]["stage_hours"]:
        lines.append(f"| {stage} (시간) | " + " | ".join(f"{x['stage_hours'][stage]:,.1f}" for x in result["ingestion"]) + " |")
    for label, key, digits in [("완전 중첩 시 최소 배치일", "ideal_overlapped_nights", 1), ("완전 직렬 처리 환산 배치일", "serial_equivalent_nights", 1), ("임베딩 입력 토큰", "embedding_input_tokens", 0), (f"일 {ing['daily_changed_documents']}건 증분의 병목 단계 시간", "daily_delta_bottleneck_hours", 2)]:
        row(label, key, result["ingestion"], digits)
    lines += ["", "중첩 최소값은 계획 하한이고 직렬 환산값은 비교 기준이다. 실제 완료 기간의 신뢰구간이나 보장 범위가 아니다. 큐 대기, 파일별 편차, 수동 검수, 야간 쿼터, 단계 간 경쟁에 따라 더 길어질 수 있다. OCR의 페이지 비율은 현재 이미지 개수·처리 시간의 대용값이다. 실측 이미지 단위 처리량으로 보정해야 한다.", "", "재생성: `python3 capacity/estimate.py --output docs/산정_결과.md`", ""]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=Path(__file__).with_name("inputs.json"))
    parser.add_argument("--output", type=Path)
    parser.add_argument("--json", action="store_true", help="Output machine-readable calculations")
    args = parser.parse_args()
    data = json.loads(args.input.read_text(encoding="utf-8"))
    result = calculate(data)
    rendered = json.dumps(result, ensure_ascii=False, indent=2) if args.json else markdown(data, result)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + ("\n" if not rendered.endswith("\n") else ""), encoding="utf-8")
        print(f"Wrote {args.output}")
    else:
        print(rendered)


if __name__ == "__main__":
    main()

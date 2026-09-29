"""Conservative attachment and authoring capacity; no Milvus or inference hardware.

CPU times, wall times and per-slot RSS are independent planning assumptions.
Worker pools retain 60% target utilization with one worker unavailable.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def up(value):
    nearest = round(value)
    return nearest if abs(value - nearest) <= 4 * math.ulp(value) else math.ceil(value)


def validate(d):
    def walk(value, path="input"):
        if isinstance(value, dict):
            for key, item in value.items():
                walk(item, f"{path}.{key}")
        elif isinstance(value, list):
            for item in value:
                walk(item, path)
        elif not isinstance(value, str):
            if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value) or value < 0:
                raise ValueError(f"{path}: finite nonnegative number required")
    walk(d)
    for value in (d["utilization"], 1-d["host_reserve_fraction"], 1-d["storage"]["free_fraction"]):
        if not 0 < value < 1:
            raise ValueError("utilization and reserve fractions must be between 0 and 1")
    for section, key in (("attachments", "request_share"), ("attachments", "dedrm_share"), ("attachments", "ocr_page_share"), ("generation", "request_share")):
        if not 0 <= d[section][key] <= 1:
            raise ValueError(f"{section}.{key}: fraction required")
    if not 0 < d["traffic"]["service_hours"] <= 24:
        raise ValueError("service_hours must be in (0,24]")
    if d["traffic"]["peak_factor"] < 1:
        raise ValueError("peak_factor must be >=1")
    if d["generation"]["retry_factor"] < 1 or d["model"]["chat_calls"] < 1:
        raise ValueError("call factors must be >=1")
    if d["model"]["output_tokens_per_second"] <= 0 or d["generation"]["poll_interval_seconds"] <= 0:
        raise ValueError("token rate and polling interval must be positive")
    formats = [d["generation"][key] for key in ("docx", "pptx")]
    if not math.isclose(sum(x["share"] for x in formats), 1):
        raise ValueError("docx/pptx shares must sum to 1")
    if any(x["calls"] < 1 for x in formats):
        raise ValueError("each format requires at least one model call")
    for w in d["workers"].values():
        if w["vcpu"] <= 0 or w["slots"] < 1 or int(w["slots"]) != w["slots"]:
            raise ValueError("worker CPU must be positive and slots a positive integer")
        if w["slots"] * w["slot_ram_gib"] + w["overhead_gib"] > w["ram_gib"]:
            raise ValueError("worker slots exceed available RAM")


def pool(spec, rate, cpu_seconds, wall_seconds, utilization):
    cpu = rate * cpu_seconds / utilization
    slots = up(rate * wall_seconds / utilization)
    active = max(up(cpu / spec["vcpu"]), up(slots / spec["slots"]))
    count = active + 1 if rate else 0
    return {**spec, "rate": rate, "required_cpu": cpu, "required_slots": slots,
            "count": count, "total_vcpu": count*spec["vcpu"], "total_ram_gib": count*spec["ram_gib"],
            "total_scratch_gib": count*spec["scratch_gib"]}


def calculate(d, qps=None):
    validate(d)
    t, a, g, m, s = (d[k] for k in ("traffic", "attachments", "generation", "model", "storage"))
    u = d["utilization"]
    qps = t["target_qps"] if qps is None else qps
    if isinstance(qps, bool) or not isinstance(qps, (int, float)) or not math.isfinite(qps) or qps < 0:
        raise ValueError("qps must be finite and nonnegative")
    formats = [g[key] for key in ("docx", "pptx")]
    avg = lambda key: sum(f["share"]*f[key] for f in formats)
    daily = t["daily_users"]*t["requests_per_user"]
    files = qps*a["request_share"]*a["files_per_request"]
    pages = files*a["pages_per_file"]
    jobs = qps*g["request_share"]
    chat = qps-jobs
    chat_call_s = m["ttft_seconds"]+m["chat_output_tokens"]/m["output_tokens_per_second"]
    author_call_work = avg("calls")*m["ttft_seconds"]+avg("total_output_tokens")/m["output_tokens_per_second"]
    cc, dc = chat*m["chat_calls"], jobs*avg("calls")*g["retry_factor"]
    input_s = cc*m["chat_input_tokens"]+dc*g["input_tokens_per_call"]
    output_s = cc*m["chat_output_tokens"]+jobs*avg("total_output_tokens")*g["retry_factor"]
    model_work = cc*chat_call_s+jobs*author_call_work*g["retry_factor"]
    workers = [
        pool(d["workers"]["dedrm"], files*a["dedrm_share"], a["dedrm_cpu_seconds_per_file"], a["dedrm_wall_seconds_per_file"], u),
        pool(d["workers"]["parse"], files, a["pages_per_file"]*a["parse_cpu_seconds_per_page"], a["parse_wall_seconds_per_file"], u),
        pool(d["workers"]["ocr"], pages*a["ocr_page_share"], a["ocr_cpu_seconds_per_page"], a["ocr_wall_seconds_per_page"], u),
        pool(d["workers"]["render"], jobs, avg("render_cpu_seconds"), avg("render_wall_seconds"), u),
    ]
    fixed = d["fixed_services"]
    total_cpu = sum(w["total_vcpu"] for w in workers)+sum(x["count"]*x["vcpu"] for x in fixed)
    total_ram = sum(w["total_ram_gib"] for w in workers)+sum(x["count"]*x["ram_gib"] for x in fixed)
    daily_files = daily*a["request_share"]*a["files_per_request"]
    daily_jobs = daily*g["request_share"]
    raw_daily = daily_files*a["mb_per_file"]*1e6
    attachments = raw_daily*(1+a["dedrm_share"]+a["derived_size_ratio"])*a["retention_days"]
    artifacts = daily_jobs*avg("result_mb")*1e6*g["retention_days"]
    logs = daily*s["metadata_log_bytes_per_request"]*s["metadata_log_days"]
    live = attachments+artifacts+logs
    allocated = live*(1+s["backup_copies"])/(1-s["free_fraction"])
    external_mbps = (files*a["mb_per_file"]+jobs*avg("result_mb")*g["downloads_per_result"])*8/u
    chunks = pages*a["chunks_per_page"]
    embed_tpm = (chunks*a["tokens_per_chunk"]+qps*m["query_embedding_tokens"])*60/u
    job_seconds = author_call_work*g["retry_factor"]+avg("render_wall_seconds")+g["other_workflow_seconds"]
    return {"as_of": d["as_of"], "daily_requests": daily, "daily_files": daily_files, "daily_jobs": daily_jobs,
            "average_qps": daily/(t["service_hours"]*3600), "expected_peak_qps": daily/(t["service_hours"]*3600)*t["peak_factor"],
            "qps": qps, "files_per_second": files, "pages_per_second": pages, "ocr_pages_per_second": pages*a["ocr_page_share"],
            "jobs_per_second": jobs, "workers": workers, "total_vcpu": total_cpu, "total_ram_gib": total_ram,
            "host_vcpu_min": up(total_cpu/(1-d["host_reserve_fraction"])), "host_ram_gib_min": up(total_ram/(1-d["host_reserve_fraction"])),
            "worker_scratch_gib": sum(w["total_scratch_gib"] for w in workers),
            "model_concurrency": up(model_work/u), "model_rpm": up((cc+dc)*60/u),
            "model_input_tpm": up(input_s*60/u), "model_output_tpm": up(output_s*60/u), "model_total_tpm": up((input_s+output_s)*60/u),
            "model_seconds_per_job": author_call_work*g["retry_factor"], "job_active_seconds": job_seconds,
            "planned_active_jobs": up(jobs*job_seconds/u), "poll_rps": jobs*job_seconds/g["poll_interval_seconds"],
            "embedding_chunks_per_second": chunks/u, "query_embeddings_per_second": qps/u, "embedding_tpm": up(embed_tpm),
            "raw_upload_gb_per_day": raw_daily/1e9, "attachment_retained_tib": attachments/2**40,
            "artifact_retained_tib": artifacts/2**40, "metadata_log_tib": logs/2**40,
            "live_tib": live/2**40, "allocated_tib": allocated/2**40, "rounded_storage_tib": up(allocated/2**40/4)*4,
            "external_mbps": external_mbps, "internal_mbps": external_mbps*s["network_internal_factor"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path, default=Path(__file__).with_name("workflow_inputs.json"))
    parser.add_argument("--qps", type=float)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = calculate(json.loads(args.inputs.read_text()), args.qps)
    text = json.dumps(result, ensure_ascii=False, indent=2)+"\n"
    if args.output:
        args.output.write_text(text)
    else:
        print(text, end="")


if __name__ == "__main__":
    main()

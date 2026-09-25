# Research Report: Kỹ thuật JEV (TypeSafe Jev, "System One" decision model) cho AI flow insight

Ngày nghiên cứu: 2026-09-25 15:42 (Asia/Saigon)

## 1. Executive Summary

**JEV = "Jev"**, decision model của TypeSafe (typesafe.ai), tự gọi là "System One model". Không phải kỹ thuật prompting, không phải viết tắt Judge/Execute/Verify. Jev không sinh text: nhận `state` (JSON/string) + `questions` có kiểu (Noul yes/no, Choice, Score) → trả **xác suất đã hiệu chuẩn (calibrated)** + `confidence`. Đầu ra bị ràng buộc cứng theo schema câu hỏi, không thể "bịa" giá trị ngoài tập cho trước. Mô tả ngắn gọn của TypeSafe: "smart `if` statement".

Phù hợp cho các **điểm quyết định** trong pipeline LLM: gate trước khi gọi LLM (routing, triage), review sau khi LLM sinh (kiểm chứng, xếp hạng, lọc), vòng lặp "task done?" của agent. Rẻ ($0.042/1M input, output free) và nhanh (70–500 ms, median ~100 ms). Có trên OpenRouter (`typesafe/jev-1.13`, endpoint riêng `/api/v1/systemone`, không dùng `/chat/completions`) → repo đã dùng OpenRouter nên tái dùng key/billing, không thêm vendor account.

**Khuyến nghị cho scrapebooking**: giữ nguyên pipeline 1 LLM call + validation deterministic; **bổ sung Jev như lớp "judge" hậu kiểm ngữ nghĩa** cho từng highlight/pricing_opportunity/risk (điều mà `validation.py` hiện KHÔNG làm: chỉ kiểm tra ref tồn tại, không kiểm tra claim có đúng với evidence không). Mở rộng sau: chọn `reasoning_effort` theo độ "sôi động" của kỳ dữ liệu, xếp hạng highlight cho dashboard, grader rẻ cho bộ kịch bản test prompt. Không dùng Jev cho việc đếm/so số/ngày (Jev yếu số học) — giữ trong code.

## 2. Methodology

- Nguồn: 5 (HuggingFace blog, flaviocopes.com deep-dive, OpenRouter docs, 2 lượt WebSearch tổng hợp: OpenRouter/AIMLAPI/Requesty/Bifrost/Pydantic/MarkTechPost 23-09-2026).
- Gemini CLI lỗi auth (`GOOGLE_CLOUD_PROJECT`), fallback WebSearch/WebFetch.
- Từ khóa: `JEV technique LLM`, `Jev TypeSafe decision model`, `jev judgment policy API`, `openrouter jev`.
- Đối chiếu mã nguồn: `backend/app/insight/{client,service,prompt,validation,input_builder,schema}.py`, `backend/app/config.py`.

## 3. Key Findings

### 3.1 Jev là gì
- Model ra quyết định, không sinh text/code. Train bằng RLCD (Reinforcement Learning for Calibrated Decisions): trả 90% thì đúng ~90%.
- Mọi câu hỏi trong 1 request chạy **song song** trên cùng state → "speculative fan-out": hỏi 10 câu ≈ chi phí token, không nhân latency.
- Context: ~64K tokens tổng (trực tiếp TypeSafe), 32K/câu; trên OpenRouter ghi 32K.
- Input text-only (chưa có ảnh/audio).

### 3.2 Ba primitive
| Kiểu | Hỏi | Trả về |
|---|---|---|
| `noul` | Yes/No | `noul` ∈ [0,1] |
| `choice` | Chọn 1 trong N (`criteria` mô tả từng option, nên có `other`) | `choice`, `probabilities`, `confidence` |
| `score` | Vị trí trên thang thứ tự (`criteria` là list mô tả từng mức) | `score` (mean có trọng số), `probabilities`, `confidence` |

Ví dụ định nghĩa câu hỏi (JSON):
```json
{
  "supported": {
    "type": "noul",
    "instructions": "Does `claim` follow from the facts in `evidence` only?",
    "criteria": {"true": "Every statement in claim is backed by evidence", "false": "Claim adds facts or direction not in evidence"}
  },
  "urgency": {
    "type": "score",
    "instructions": "How urgent is `claim` for a hotel manager today?",
    "criteria": ["Informational; nothing to do this week", "Worth acting within 7 days", "Act today; revenue at stake within 48h"]
  }
}
```

### 3.3 API
- Trực tiếp: `POST https://api.typesafe.ai/v1/systemone`, model `jev-latest` / `jev-1.13.0`. SDK: `typesafe-sdk` (Python), `@typesafe-ai/sdk` (JS), Vercel AI SDK, Pydantic AI (`pydantic.dev/docs/ai/models/typesafe/`).
- Qua OpenRouter: `POST https://openrouter.ai/api/v1/systemone` (hoặc `/api/alpha/decisions`), model `typesafe/jev-1.13` hoặc `~typesafe/jev-latest`. Cùng giá, response có `usage.cost` USD. **Không** đi qua `/chat/completions`.
- Body: `{"model": ..., "state": <str|json>, "questions": {<id>: {type, instructions, criteria}}}` → `{"answers": {<id>: {...}}, "usage": {...}}`.

### 3.4 Giá / hiệu năng
| Metric | Giá trị |
|---|---|
| Input | $0.042 / 1M tokens |
| Output | free |
| Latency | 70–500 ms, median ~100 ms (US West) |
| Rate limit (trực tiếp) | 250K tok/s, 1.200 req/min |
| Ví dụ | ~300 tokens/call ≈ $0.0000126 |

So với GPT-6 Luna hiện dùng ($0.10 in / $0.50 out): 1 lượt hậu kiểm 10 item × ~600 tokens ≈ $0.00025. Không đáng kể.

### 3.5 Giới hạn (quan trọng khi thiết kế)
- Đọc **rất literal**: câu hỏi mơ hồ → sai. Một câu hỏi = một phán đoán.
- **Không làm toán**: không đếm, không so số/ngày/%; trích bằng Choice rồi tính trong code.
- Score không tuyến tính (1.4 ≠ "40% giữa 2 mức") → chỉ dùng để threshold/xếp hạng.
- **Context rot**: state thừa làm giảm chính xác → lọc state theo câu hỏi trước khi gửi.
- Tránh phủ định kép, tránh instructions mâu thuẫn criteria.
- Không giải thích được lý do (không có rationale) → khác LLM-as-judge.
- Endpoint OpenRouter còn `alpha`/community guide → theo dõi breaking change; pin version `jev-1.13`.

### 3.6 Best practices viết câu hỏi (TypeSafe)
1. Một judgment/câu. 2. Mô tả *tình huống*, không mô tả *mức độ* ("feature hỏng nhưng có workaround" thay vì "khá nghiêm trọng"). 3. Điều kiện chính xác. 4. Choice luôn có lối thoát `other`. 5. Score có ví dụ ở mức mơ hồ. 6. Score một chiều. 7. Trỏ thẳng vào state bằng backtick path (`` `claim` ``, `` `evidence` ``). 8. **Test với bộ nhãn** → chỉnh threshold theo confidence vs accuracy.

## 4. AI flow hiện tại (scrapebooking) và khoảng trống

```
build_input()  ──► CompletionRequest (GPT-6 Luna, JSON schema strict, reasoning=medium)
   │                       │
   │ payload + valid_refs  ▼
   │               validate_output()  ── pydantic parse
   │                       │            ── ref ∈ valid_refs ?      (deterministic)
   │                       │            ── date ∈ period ?        (deterministic)
   │                       │            ── hotel_id known ?       (deterministic)
   ▼                       ▼
 Insight.input_json   Insight.output_json + dropped_highlights → dashboard insight-view.tsx
```

Khoảng trống:
1. **Không kiểm chứng ngữ nghĩa**: model có thể cite `metric:12:2026-10-03` hợp lệ nhưng viết ngược chiều dữ liệu (nói "đối thủ hết phòng" trong khi ô đó `available`). `validation.py` cho qua.
2. **Không có chất lượng/độ ưu tiên**: highlights hiển thị theo thứ tự model trả; không lọc mục vô nghĩa ("giá không đổi").
3. **`reasoning_effort` cố định** cho mọi tenant/ngày, kể cả ngày không có sự kiện.
4. **Test prompt** (`test_insight_scenarios.py`, 4 test) dựa FakeInsightClient; đổi prompt không có grader đo hồi quy chất lượng.

## 5. Phương án áp dụng Jev

### 5.1 Nguyên tắc
- LLM sinh, code quyết định luật cứng, **Jev quyết định các phán đoán ngữ nghĩa có tập trả lời hữu hạn**.
- Jev luôn là *tùy chọn* (`jev_enabled=false` → hành vi như hiện tại). Lỗi Jev → log + giữ item (fail-open), không làm fail bản tin.
- State gửi Jev = **item + các ref đã resolve** từ `input_json` (vài trăm token), không gửi cả payload.

### 5.2 Phase 1 — Hậu kiểm ngữ nghĩa (ROI cao nhất, ~1 ngày)
Sau `validate_output()` (đã lọc ref/date), với mỗi item trong `highlights`, `pricing_opportunities`, `risks`:

```python
state = {
    "claim": {"title": h["title"], "recommendation": h["recommendation"]},
    "evidence": [resolve_ref(input_json, e["ref"]) for e in h["evidence"]],  # rows metric/evt/compset
    "period": {...}, "language": ...,
}
questions = {
    "supported": noul("Is every fact in `claim` present in `evidence`? Direction of change must match."),
    "actionable": score("How useful is `claim.recommendation` for a hotel revenue manager?",
                        ["Restates data; no action", "Suggests a direction without specifics",
                         "Concrete action with date range and price/inventory lever"]),
    "contradicts_stock_rule": noul("Does `claim` state an exact room count while evidence `stock_confidence` is capped or hidden?"),
}
```
Quyết định trong code:
- `supported < 0.5` hoặc `contradicts_stock_rule > 0.7` → drop, ghi `dropped_highlights` với `reasons=["jev:unsupported p=0.31"]` (tái dùng cấu trúc hiện có, dashboard đã hiển thị).
- `0.5 ≤ supported < 0.8` → giữ nhưng hạ `confidence` xuống `low` (schema đã có field).
- `actionable.score < 0.5` → giữ nhưng đẩy cuối danh sách.
- Fan-out: 1 request Jev/item, hoặc 1 request với N×3 câu hỏi (state gộp, key theo index) nếu tổng < 32K tokens.

Chỉnh sửa:
- Mới: `backend/app/insight/judge.py` (JevClient Protocol + `OpenRouterJevClient` gọi `{base_url}/systemone` + `FakeJevClient`), `judge_output()` trả `(output, dropped_extra, demoted)`.
- `service.py::_apply_result`: gọi `judge_output` sau `validate_output`; lưu `tokens`/`cost` Jev cộng vào `cost_usd`; metric `INSIGHT_JEV_DECISIONS{outcome}`.
- `config.py`: `jev_enabled: bool=False`, `jev_model="typesafe/jev-1.13"`, `jev_supported_threshold=0.5`, `jev_demote_threshold=0.8`.
- Test: `tests/unit/test_insight_judge.py` với FakeJevClient; 1 integration test skip nếu không có key.

### 5.3 Phase 2 — Triage trước khi gọi LLM (tối ưu cost/latency, ~0.5 ngày)
Trước `CompletionRequest`, gửi Jev state rút gọn (events_24h count theo type, compset sold_out_share, holidays trong 7 ngày, `data_quality`) — đã tính sẵn trong code, Jev chỉ phán đoán:
- `activity = score("How eventful is the next 30 days for this hotel set?", ["Quiet; prices and stock flat", "Some movement", "Many sold-outs, price swings or holidays"])` → `reasoning_effort = {0:"low",1:"medium",2:"high"}`.
- Không dùng Jev để *bỏ qua* bản tin ngày (bản tin daily phải luôn tồn tại); chỉ chỉnh effort/model.
Lưu ý: phần lớn tín hiệu này là số → có thể thay Jev bằng rule đơn giản (`len(events_24h) > X`). Chỉ làm nếu đo thấy chi phí LLM đáng kể. **YAGNI: hoãn** cho tới khi có > ~50 tenant.

### 5.4 Phase 3 — Grader cho bộ kịch bản prompt (chất lượng dài hạn)
- `test_insight_scenarios.py`: thêm chế độ `INSIGHT_EVAL=1` chạy thật GPT + Jev trên fixture, assert `supported ≥ 0.8` cho ≥ 90% item, xuất bảng vào `plans/reports/`. Đổi `PROMPT_VERSION` → chạy eval để thấy hồi quy.
- Xếp hạng highlight trên dashboard theo `actionable` + `urgency` (Score) thay vì thứ tự model.

### 5.5 Không dùng Jev cho
- Kiểm tra ref tồn tại, ngày trong kỳ, hotel_id — code đã làm, deterministic, miễn phí.
- So sánh số (delta %, giá A > B), đếm phòng, tính ngày — Jev yếu; đã có `HotelDateMetric`/`compset`.
- Sinh summary/recommendation — Jev không sinh text.
- Quyết định nghiệp vụ cứng (quyền, thanh toán).

## 6. So sánh lựa chọn cho lớp hậu kiểm

| Tiêu chí | Chỉ deterministic (hiện tại) | LLM-as-judge (GPT call thứ 2) | Jev |
|---|---|---|---|
| Bắt claim sai chiều dữ liệu | Không | Có | Có |
| Giải thích lý do drop | – | Có (rationale) | Không (chỉ xác suất) |
| Calibrated confidence | – | Kém, phải tự prompt | Có, threshold được |
| Chi phí/bản tin (10 item) | 0 | ~$0.003–0.01 + reasoning | ~$0.0003 |
| Latency thêm | 0 | 5–30 s | ~0.1–0.5 s |
| Rủi ro output sai schema | – | Có (cần parse) | Không (structural) |
| Vendor mới | – | Không | Không (qua OpenRouter) |
| Độ chín | – | Cao | Mới (2026), endpoint OpenRouter alpha |

Kết luận: Jev thắng về chi phí/độ trễ/calibration cho phán đoán có tập trả lời hữu hạn; LLM-judge chỉ hơn khi cần *rationale* hiển thị cho người dùng. Với `dropped_highlights` chỉ cần lý do ngắn (`jev:unsupported p=0.31`), Jev đủ.

## 7. Pitfalls khi triển khai
- Gửi cả `input_json` làm state → context rot + tốn token; luôn resolve ref và gửi tối thiểu.
- Đặt câu hỏi kiểu "Is this highlight good?" → mơ hồ; tách thành `supported`, `actionable`, `contradicts_stock_rule`.
- Threshold chọn bừa → cần bộ ~30 item gán nhãn tay (đúng/sai) từ tenant 9 (dữ liệu thật) để chỉnh `jev_supported_threshold`.
- Ngôn ngữ: claim tiếng Việt, evidence JSON tiếng Anh → cần test calibration với tiếng Việt; nếu kém, thêm field `claim_en` do model chính sinh (tăng schema) hoặc giữ threshold thấp hơn.
- Batch path (`poll_batches`) cũng phải qua judge → đặt judge trong `_apply_result` để cả sync và batch dùng chung.
- Pin `typesafe/jev-1.13`; log `model` từ response để audit.

## 8. Resources
- HF blog "Jev AI vs LLMs": https://huggingface.co/blog/sora-2/jev-ai-vs-llms-when-should-you-use-a-decision-mode
- Deep dive (flaviocopes): https://flaviocopes.com/jev/
- OpenRouter guide: https://openrouter.ai/docs/guides/community/jev
- TypeSafe docs/playground: https://typesafe.ai · https://console.typesafe.ai · https://thejevai.com/docs
- Pydantic AI provider: https://pydantic.dev/docs/ai/models/typesafe/
- Coding guide (MarkTechPost 23-09-2026): https://www.marktechpost.com/2026/09/23/a-coding-guide-to-typesafe-ai-jev/
- Project reference gist: https://gist.github.com/pjburnhill/adf8d28efcad9df037bfdece178ef965
- Requesty explainer: https://www.requesty.ai/blog/typesafe-jev-explained
- Community builds: shipwithjev.com; jevsearch / JevQL / Oko (GitHub kylemclaren, bartlomein)

## 9. Next steps
1. Xác nhận với user phạm vi Phase 1 (hậu kiểm ngữ nghĩa) → tạo plan `plans/260925-*-jev-insight-judge/`.
2. Lấy 20–30 highlight thật từ tenant 9, gán nhãn tay, chạy playground Jev để chốt câu hỏi + threshold trước khi code.
3. Implement `judge.py` + config + tests; bật `jev_enabled` cho tenant 9 trước, so sánh `dropped_highlights` 1 tuần.
4. Hoãn Phase 2/3 tới khi có số liệu Phase 1.

## Unresolved questions
- OpenRouter `/api/v1/systemone` có nhận `state` dạng JSON object hay chỉ string? (docs community chưa ghi rõ; cần thử 1 request.)
- Độ chính xác của Jev với claim tiếng Việt chưa có benchmark công khai.
- Người dùng có muốn hiển thị lý do drop từ Jev trên dashboard (đã có UI `dropped_highlights`) hay chỉ log?

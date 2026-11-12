# Spec: AI-agent chuyển tiếp phản hồi người dùng từ hỗ trợ kỹ thuật sang đội sản phẩm

- Ngày: 2026-11-06 · Hạn nộp case: 2026-11-26 (Intelligence Cup, Gazprom Neft)
- Nguồn đề: `Кейс_Искусственный интеллект .pdf`
- Trạng thái: chờ duyệt spec

## 0. Mục tiêu và quyết định đã chốt

**Bài toán:** khoảng 40 nhân viên hỗ trợ nhận ticket qua điện thoại (có ghi âm) và cổng hỗ trợ một cửa (form + file/ảnh). Dữ liệu lưu 1 năm. Các yêu cầu **không nghiêm trọng nhưng lặp lại** không đến được đội sản phẩm. Cần một agent tự phát hiện chúng và báo cho đội sản phẩm, **không tạo thêm việc cho bộ phận hỗ trợ**.

**Ràng buộc:** chỉ dùng model nội bộ Qwen 3.8, Qwen-ASR, Qwen-VL (tên lấy nguyên văn từ đề). Không dùng API bên ngoài. Mô hình tài chính chỉ tính lợi ích, nhưng phải giữ cân bằng giữa độ đơn giản và hiệu quả.

**Bài nộp (tiếng Nga):**
1. Bài chính gồm mục 1–4 và 6, tối đa 15.000 ký tự, định dạng docx hoặc pdf.
2. Mục 5 là file `.md` riêng.
3. Slide khoảng 10 trang.
4. AI Footnotes (tùy chọn).

**Quyết định đã chốt:**

| # | Quyết định |
|---|---|
| D1 | Tài liệu + **demo nhỏ** chạy được (không làm prototype microservice đầy đủ) |
| D2 | Demo chạy **Qwen local qua Ollama** (`qwen3:8b`, embedding `bge-m3`) |
| D3 | Dữ liệu demo: **chỉ text**, khoảng 400 ticket synthetic có nhãn đúng sẵn. Kiến trúc chừa chỗ cắm audio |
| D4 | Thảo luận và spec bằng tiếng Việt. **Mọi thứ nộp viết thẳng bằng tiếng Nga** |
| D5 | Kiến trúc **pipeline lai**: LLM chỉ dùng ở bước enrich và agent-digest, phần đếm và thống kê do code xác định |
| D6 | Hai nhịp: **cảnh báo sớm spike** (15–60 phút, gửi trưởng ca hỗ trợ) và **digest hằng tuần** (gửi đội sản phẩm) |

**Ngoài phạm vi:** xử lý ticket khẩn cấp. Agent chạy song song và chỉ đọc (read-only), quy trình SLA hiện có giữ nguyên.

## 1. Kiến trúc

```
[Hệ thống ticket] ──read-only──► ① ingest ──► ② media (ASR/VL, GPU, chỉ khi cần)
                                     │              │
                                     ▼              ▼
                              ③ enrich (Qwen: phân loại + JSON + embedding)  [micro-batch 15–60 phút]
                                     ▼
                              ④ cluster & aggregate  ── spike rule ──► trưởng ca hỗ trợ
                                     ▼                [gán cụm: micro-batch; chạy lại toàn bộ: hằng tuần]
                              ⑤ agent-digest (Qwen + tools) ──► đội sản phẩm  [hằng tuần]
                                     ▲                                  │
                                     └──── feedback accepted/rejected ──┘
                     PostgreSQL + pgvector (dữ liệu chung, audit)
```

| Service | Trách nhiệm | Lý do tách riêng |
|---|---|---|
| ① ingest | Kéo ticket mới theo con trỏ `updated_at`, chống trùng, che PII (module bên trong) | Service duy nhất chạm vào hệ thống nguồn: tài khoản read-only, rate limit |
| ② media | Qwen-ASR cho cuộc gọi, Qwen-VL cho ảnh | Chạy trên GPU, có hàng đợi riêng, scale riêng |
| ③ enrich | Mỗi ticket gọi LLM 1 lần ra JSON, thêm 1 lần embedding | Khối tải LLM chính: batching và retry |
| ④ cluster | Gán cụm gần nhất, chạy lại HDBSCAN hằng tuần, đếm, xu hướng, ngưỡng, spike | Không dùng LLM, là nguồn số liệu duy nhất |
| ⑤ agent-digest | Chỉ chạy với cụm vượt ngưỡng: tools, viết digest, nhận feedback | Phần agent thật, có quyền ghi ra ngoài |

**Cố ý không dùng:** Kafka hoặc streaming, vector DB riêng, service che PII riêng.

**Tính tải (giả định, sẽ ghi rõ là giả định trong bài):**
- Lượng ticket: khoảng 1.500 ticket/ngày (50% là cuộc gọi), tức khoảng 375 nghìn ticket/năm.
- ASR: khoảng 50 giờ audio/ngày, với RTF 0,05 thì cần khoảng 2,5 giờ GPU.
- LLM enrich: khoảng 1 triệu token/ngày, khoảng 15 phút ở mức 1.000 tok/s.
- Agent: 10–30 cụm/tuần.
- Lưu trữ embedding: khoảng 1,5 GB.

## 2. Tools của agent

**Đọc:**

| Tool | Trả về |
|---|---|
| `get_cluster_stats` | Số liệu thống kê, nguồn số liệu duy nhất |
| `get_cluster_examples` | Trích đoạn đã che PII, kèm ticket ID |
| `search_tickets` | Tìm kiếm hybrid (BM25 + vector) |
| `search_backlog` | Các issue đang có trong tracker |
| `get_product_owner` | Đội sở hữu và kênh nhận tin |
| `get_cluster_history` | Các digest trước và phản hồi của đội |

**Ghi (qua lớp kiểm soát policy gate):**

| Tool | Kiểm soát |
|---|---|
| `submit_digest_item` | ≥ N ticket bằng chứng, không lộ PII, kênh nằm trong allowlist, số khớp với stats |
| `update_backlog_item` | Chỉ được comment |
| `request_human_review` | |
| `label_cluster` | `noise`, `service_request` hoặc `merge_with` |

**Quy tắc:**
- Tối đa 8 lần gọi tool trên mỗi cụm. Vượt quá thì chuyển `request_human_review`.
- Agent được phép kết luận "không báo" (abstain).
- Agent **không tự tạo issue**: issue chỉ được tạo khi đội sản phẩm bấm accept.
- Cảnh báo spike là quy tắc code, không phải tool của agent.

## 3. Prompt

**3.1. Prompt agent-digest** (tiếng Nga, có chú thích từng phần): РОЛЬ → ЦЕЛЬ (4 kết cục) → ВХОДНЫЕ ДАННЫЕ (chỉ ID) → ИНСТРУМЕНТЫ И ПОРЯДОК (stats → examples → history → backlog → owner → hành động, ≤ 8 lần gọi) → ПРАВИЛА → ФОРМАТ → ПРИМЕР.

- **ПРАВИЛА:** số chỉ lấy từ stats; mỗi khẳng định có ticket_id; yêu cầu dịch vụ không phải lỗi sản phẩm; không PII; không chắc thì chuyển review.
- **ФОРМАТ:** Tiêu đề | Bản chất vấn đề | Quy mô | 3 ví dụ + ID | Giả thuyết nguyên nhân (gắn nhãn) | Hành động đề xuất.
- **ПРИМЕР:** few-shot từ cụm "không nhận được mã SMS".

**3.2. Prompt enrich:** schema `{type: bug|feature_request|service_request|consultation|other, product, feature, problem_summary, user_impact: blocker|degraded|cosmetic, confidence}`. Chạy với `temperature=0` và guided JSON. Ticket có confidence thấp chuyển sang hàng đợi kiểm tra mẫu ngẫu nhiên.

**Ngân sách:** khoảng 4.000 trên 15.000 ký tự.

## 4. Test và nghiệm thu

**Golden set:**
- Khoảng 800 ticket thật, 2 người gán nhãn, đo κ (yêu cầu ≥ 0,7 trước khi test model).
- Danh sách vấn đề lặp lại đã biết lấy từ backlog.

**Ngưỡng offline:**

| Tầng | Metric | Ngưỡng |
|---|---|---|
| enrich | JSON hợp lệ | 100% |
| enrich | macro-F1 cho `type` | ≥ 0,85 |
| enrich | recall `service_request` | ≥ 0,90 |
| cluster | cụm mạch lạc | ≥ 90% |
| cluster | recall vấn đề đã biết | ≥ 80% |
| agent | số liệu khớp stats | 100% |
| agent | trích dẫn hợp lệ | 100% |
| agent | báo trùng với backlog | ≤ 10% |
| agent | rubric | ≥ 4,0 |
| Toàn hệ thống | rò rỉ PII | 0 |

**Backtest 1 năm** theo từng tuần, ra lead time so với thời điểm vấn đề vào backlog thực tế.

**Phi chức năng:**
- Tải: xử lý xong trong cửa sổ thời gian; backfill ≤ 3 đêm.
- Prompt injection.
- Idempotent khi chạy lại.
- Retry khi model không khả dụng.

**Ba giai đoạn:**

| Giai đoạn | Phạm vi | Điều kiện qua cửa |
|---|---|---|
| Shadow | 4 tuần, Вебнефть | ≥ 70% mục digest hữu ích |
| Pilot | 6–8 tuần, 2–3 sản phẩm | accepted ≥ 50% |
| Rollout | Toàn bộ | Đạt DoD |

**Definition of Done:** đạt các ngưỡng, accepted ≥ 50%, không có sự cố PII, chạy xong trong cửa sổ thời gian, có dashboard và rollback.

**Sau release theo dõi:**
- Tỷ lệ accepted. Dưới 40% trong 3 tuần liên tiếp thì xem xét lại.
- Drift: tỷ lệ `other` tăng.
- Tỷ lệ chuyển review.

## 5. Metric hiệu quả (file .md riêng)

| Cấp | Metric |
|---|---|
| Chính | **M1.** Ticket lặp lại được ngăn chặn = tốc độ cụm × (T_thực tế − T_agent) |
| Chính | **M2.** Giờ tổng hợp thủ công được tiết kiệm |
| Dẫn dắt | **M3.** Lead time vào backlog |
| Dẫn dắt | **M4.** Tỷ lệ accepted |
| Guardrail | Báo sai; thời gian nhân viên hỗ trợ dành cho agent ≈ 0; PII |

**Thu thập hồi cứu, có phương án dự phòng cho từng nguồn:**

| Dữ liệu | Nguồn chính | Phương án dự phòng |
|---|---|---|
| Liên kết ticket với issue | Liên kết sẵn trong tracker | So khớp ngữ nghĩa, người kiểm tra mẫu |
| Ngày sửa | Release notes | Changepoint |
| AHT | Mốc thời gian trong hệ thống | Đo time-and-motion → benchmark có dẫn nguồn |
| M2 | Log xuất dữ liệu | Khảo sát 40 người + phỏng vấn → quan sát |
| Giá giờ công | Dữ liệu HR | hh.ru |

- Mỗi con số gắn nhãn độ tin cậy: đo / ước lượng / benchmark.
- **Theo dõi về sau:** dashboard hằng tuần. Rollout so le theo sản phẩm và so bằng **difference-in-differences**. Cập nhật AHT và giá giờ công mỗi quý.
- **Nếu không đo được M1:** báo cáo M3 + M2, dùng M1 làm cận dưới. M2 lấy từ khảo sát thì nhân hệ số 0,7.

## 6. Mô hình tài chính

**Cách tiếp cận:** tính **Max CAPEX cho hoàn vốn ≤ 3 năm** từ dòng lợi ích có chiết khấu.

**Dòng lợi ích:**
- B1: ticket được ngăn chặn × AHT × giá giờ công.
- B2: 40 × h × 48 × giá giờ công.
- B3: giữ chân khách B2B, chỉ là upside, không đưa vào kịch bản cơ sở.

**Ước tính cơ sở:** khoảng 5 triệu ₽/năm, tức Max CAPEX khoảng 10–12 triệu ₽. **Phải kiểm tra lại toàn bộ giả định.**

**Vĩ mô:** lãi suất điều hành ЦБ (3 đường đi) + phần bù rủi ro; chỉ số hóa lương; tăng trưởng lượng ticket. Tra nguồn thật: ЦБ, Минэкономразвития, Росстат.

**Kịch bản và độ nhạy:**
- 3 kịch bản bi quan / cơ sở / lạc quan, thay đổi theo h, tỷ lệ accepted, Δt và lãi suất.
- Biểu đồ tornado.

**Phương án thay thế để so sánh:** tiền gửi hoặc ОФЗ (so với IRR), thuê 1 analyst, BI theo từ khóa, agent tự do.

**Thông điệp chốt:** ngân sách cho phép chỉ đủ cho kiến trúc gọn.

## 7. Demo

```
demo/
  data/       seeds.yaml, generate.py, mocks/{backlog,owners}.json
  pipeline/   ingest.py, enrich.py, cluster.py, tools.py, agent.py
  eval/       evaluate.py → out/eval_report.md
  finance/    model.py → PNG kịch bản + tornado
  tests/      pytest cho PII, stats, policy gate, spike
  run.py      → out/digest.md, out/alerts.md, out/eval_report.md
```

**Lựa chọn kỹ thuật:**
- Ollama `qwen3:8b` (dự phòng `qwen3:4b`) + `bge-m3`.
- SQLite (production dùng PostgreSQL + pgvector).
- Cache kết quả enrich.

**Dữ liệu:**
- Khoảng 15 cụm Вебнефть + nhiễu dạng `service_request`, rải trong 12 tuần.
- 1 đợt spike (404 hàng đợi điện tử), PII giả, prompt injection.
- Backlog giả lập có sẵn 2–3 vấn đề trùng.
- Seed do Claude viết, Qwen local diễn đạt lại. Ghi vào AI Footnotes.

**Quy trình làm:** TDD cho phần xác định. Phần LLM đánh giá bằng evaluate.py.

**Ngoài phạm vi:** UI web, ASR/VL, microservice thật.

## 8. Thứ tự sản phẩm bàn giao
1. Demo (cho ra số liệu thật cho mục 4 và 6).
2. Bài chính, tiếng Nga, ≤ 15.000 ký tự, có script đếm ký tự.
3. File .md mục 5.
4. Slide khoảng 10 trang (kiến trúc, tải, kết quả eval, tài chính).
5. AI Footnotes.

## 9. Bổ sung sau khi tham khảo repo team (quangtuanitmo18/hackathon-gazprom, nhánh feat/webneft-case-v2)

| # | Bổ sung | Áp dụng vào |
|---|---|---|
| R1 | **Đa sản phẩm:** mỗi ticket có `product_id` do backend gán. Clustering, đếm và routing tách riêng theo `product_id`. Product không rõ → `request_human_review`. Demo dùng 2 sản phẩm (`webneft`, `fuel_cards`) | Phần 1, 2, 7 |
| R2 | **Hai mốc thời gian:** `source_created_at` (thời điểm tạo trong hệ thống nguồn) và `ingested_at` (thời điểm agent thật sự thấy ticket). Backtest chỉ dùng dữ liệu có trước thời điểm mô phỏng, không để dữ liệu tương lai lọt vào | Phần 4.3, 5 |
| R3 | **Phân tích 7 ticket mẫu:** №3 là 1 ticket có 2 triệu chứng (đếm là 1); №1 và №2 cùng chủ đề nhưng chưa chứng minh cùng lỗi; №4 là yêu cầu dịch vụ khẩn, đi luồng SLA; №6 và №7 không bao giờ được cấp mật khẩu hoặc OTP | Phần 3 (few-shot), bài nộp |
| R4 | **Nghiệm thu bằng cận dưới Wilson 95%** của actionable precision. Với p ≈ 0,8 và sai số ±5 điểm % cần khoảng 246 mẫu | Phần 4 |
| R5 | **Quy tắc C phải thắng B:** so pipeline Qwen với baseline rules + BM25 trên cùng holdout. Không thắng thì chọn B. Demo tính cả baseline BM25 để có số so sánh | Phần 4, 6, 7 |
| R6 | **Ticket là dữ liệu, không phải lệnh:** prompt có khối chống injection, model chỉ thấy alias `E1..En`, backend tự ánh xạ sang ID thật | Phần 3 |
| R7 | **5 service logic, chỉ 3 tiến trình triển khai cho MVP:** ingest worker; model workers (ASR/VL/LLM); app gồm cluster + agent + delivery | Phần 1 |
| R8 | **Script export DOCX/PPTX kèm kiểm tra giới hạn ký tự**, làm ở plan bài nộp | Phần 8 |

**Thay đổi so với Phần 7:** demo lưu dữ liệu bằng file JSON/JSONL và cache trong `demo/.cache/` thay cho SQLite. Demo chạy theo batch nên không cần DB, bớt được một phụ thuộc.

## 10. Rủi ro và câu hỏi còn mở
- Qwen 8B local chậm hoặc JSON không ổn định → dùng `qwen3:4b`, guided JSON, cache.
- Số liệu vĩ mô 2026 cần tra cứu tại thời điểm viết. Không dùng số từ trí nhớ.
- Lượng ticket thật/ngày không có trong đề → ghi rõ là giả định, có phân tích độ nhạy.

## 11. Bổ sung 12.11.2026 — tối ưu sau khi audit toàn bộ giải pháp

| # | Phát hiện | Sửa |
|---|---|---|
| O1 | Bài chính có một khối cũ của cuối mục 4 bị lặp (hình rollout, tiêu chí readiness, bảng 369 ticket), chiếm ~1.300 ký tự | Xoá khối lặp |
| O2 | Holdout: chủ đề `webneft_queue_404` (19 ticket) bị tách thành 2 cụm và gửi 2 mục digest; metric cũ không bắt được | Bước gộp thứ hai: cùng product, cùng feature chủ đạo, khoảng cách centroid < 0,28 (`MERGE_THRESHOLD`). Trên hai bộ synthetic, cặp cùng chủ đề cách 0,26, cặp khác chủ đề cùng feature ≥ 0,30. Thêm metric «Дубли тем внутри дайджеста» |
| O3 | Mẫu số recall gồm chủ đề 1 ticket, không thể tìm được với min_cluster_size 4 | Báo thêm `cluster_recall_reachable` (chỉ chủ đề ≥ 4 ticket) |
| O4 | Nhãn xu hướng «снижение» xuất hiện trên chủ đề phẳng do cửa sổ 14 ngày với 1–3 ticket/tuần | Cửa sổ 28 ngày so với 28 ngày trước, chỉ gắn nhãn khi lệch ≥ 1,5× và ≥ 3 ticket |
| O5 | Agent xem đúng 5 ví dụ và phải trích ≥ 5, nên luật trích dẫn là hình thức | `EXAMPLES_K = 8`, giữ `MIN_EVIDENCE = 5`; model phải chọn |
| O6 | Hai bước đầu của agent luôn giống nhau nhưng tốn 2 vòng LLM | Backend prefetch stats + examples vào message đầu; ghi vào trace với `prefetched: true`. Holdout: 162 thay vì 182 lượt gọi model, 186 nghìn thay vì 231 nghìn prompt token, thời gian agent 26 s thay vì 29 s mỗi cụm |
| O7 | Enrich chạy tuần tự, 2,3 s/ticket | `enrich_all(..., workers=4)` bằng ThreadPool; CLI `--workers`. Lưu ý: Ollama qua brew services mặc định xử lý 1 request một lúc, đo lại 496 s cho 204 ticket, tức không nhanh hơn. Cần chạy server với `OLLAMA_NUM_PARALLEL=4` để có hiệu quả |
| O8 | Không lưu enrichments và assignment nên khó audit | Ghi `enrichments.jsonl`, `assignment.json` vào `out/` |
| O9 | B2 chiếm 76% lợi ích cơ sở nhưng dựa trên số giờ mà đề nói là chưa biết | Thêm cột và đoạn «только B1» (0,1 / 2,5 / 10,9 triệu ₽) làm sàn ngân sách pilot |
| O10 | Thiếu ghi chú production cho PII tên người và baseline spike | Ghi trong bài chính: NER local cho tên; baseline cùng giờ trong 7 ngày |

Chưa làm (tuỳ thời gian trước 20.11): mô phỏng vòng feedback accepted/rejected qua `get_cluster_history`; chế độ replay theo tuần `--as-of` để vẽ đường lead time.

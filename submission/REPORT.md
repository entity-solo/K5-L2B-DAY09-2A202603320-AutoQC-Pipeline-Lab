# Báo cáo Day 09 — Nguyễn Thế Tùng: 2A202603320 - Nguyễn Thế Tùng

## 1. Kết luận trước
Pipeline tự động kết luận: **Release** (mã thoát 0).
- **Số ảnh đầu vào:** 224 ảnh thô (`data/raw`).
- **Số ảnh đầu ra:** 203 ảnh được đưa vào bộ dữ liệu chuẩn (`submission/export/clean_v1/`). Đã loại bỏ 21 ảnh không đạt tiêu chuẩn (2 ảnh hỏng, 3 ảnh quá nhỏ, 11 ảnh trùng lặp, 5 ảnh rò rỉ từ tập test).
- **Lý do quyết định:** Toàn bộ 36 lỗi bắt buộc (severity ERROR) đã được máy tự động sửa (35 lỗi) và người duyệt giải quyết triệt để (6 ảnh thiếu nhãn). Sau khi người duyệt xử lý 80 ảnh theo ngân sách, tỉ lệ ảnh còn chứa cảnh báo đạt **7.88%** (16/203 ảnh), thấp hơn ngưỡng cửa chặn 10.00% (`warn_ratio_hold`), đủ điều kiện đóng gói phát hành.

---

## 2. Lỗi và phân việc
Dưới đây là thống kê toàn bộ các mã lỗi được phát hiện từ vòng QC 1 (`02_error_list_v1.csv`):

| Mã lỗi | Số lượng | Ai sửa (máy/người) | Vì sao |
|---|---:|---|---|
| `CORRUPT_IMAGE` | 2 ảnh | Máy (intake) | Ảnh lỗi định dạng không thể giải mã bằng Pillow, loại bỏ an toàn. |
| `BAD_SIZE` | 3 ảnh | Máy (intake) | Cạnh ngắn ảnh < 250px không đạt độ phân giải yêu cầu của dự án. |
| `DUP_IMAGE_EXACT` | 8 ảnh | Máy (intake) | Trùng lặp chính xác 100% byte (so sánh hash MD5), xóa bản sao. |
| `DUP_IMAGE_NEAR` | 3 ảnh | Máy (intake) | Ảnh gần trùng lặp (pHash distance $\le 8$), loại bỏ để chống thiên vị dữ liệu. |
| `LEAK_TEST` | 5 ảnh | Máy (intake) | Trùng với tập `test` hoặc `gold_val`, bắt buộc loại bỏ để tránh rò rỉ dữ liệu. |
| `BAD_FORMAT` | 3 dòng | Máy (autofix) | Dòng thiếu cột hoặc chứa ký tự không thể parse số, xóa dòng lỗi (`drop_line`). |
| `BAD_CLASS_ID` | 6 dòng | Máy (autofix) | ID lớp ngoài dải 0..3 (ví dụ class 93), xóa dòng lỗi (`drop_line`). |
| `BOX_ZERO` | 4 dòng | Máy (autofix) | Bounding box có chiều rộng hoặc chiều cao $\le 0$, xóa dòng lỗi (`drop_line`). |
| `BOX_OUT_OF_IMAGE` | 8 dòng | Máy (autofix) | Box tràn viền quá dung sai 0.002, máy tự động cắt xén (`clip_box`) về dải [0, 1]. |
| `DUP_BOX` | 7 dòng | Máy (autofix) | Hai box cùng lớp trùng nhau với IoU > 0.9, xóa box lặp xuất hiện sau. |
| `BAD_CLASS_NAME` | 2 lần | Máy (autofix) | Sai danh sách tên lớp trong `data.yaml`, máy ghi đè chuẩn theo cấu hình. |
| `MISSING_LABEL_FILE` | 6 ảnh | **Người** (hàng đợi) | Có ảnh nhưng không có file `.txt`. Máy không thể bịa nhãn nên chuyển người gán. |
| `POSSIBLE_WRONG_CLASS`| 14 lần | **Người** (hàng đợi) | Model `yolo26l` và nhãn lệch lớp; chỉ người mới phân biệt được ngữ nghĩa đúng. |
| `POSSIBLE_MISSING` | 32 lần | **Người** (hàng đợi) | Model thấy vật thể rõ mà nhãn bỏ sót; người cần xem xét có phải vật cần gán không. |
| `POSSIBLE_FALSE_POS` | 29 dòng | **Người** (hàng đợi) | Box nhãn không có dự đoán tương ứng; người cần thẩm định xem vẽ thừa hay AI mù. |
| `POSSIBLE_LOOSE_BOX` | 12 lần | **Người** (hàng đợi) | Box vẽ lỏng/lệch (IoU thấp); người chỉnh lại viền bounding box. |
| `EMPTY_LABEL` | 12 ảnh | **Người** (hàng đợi) | File nhãn rỗng; người kiểm tra xem đây là ảnh nền (background) hay quên gán nhãn. |
| `BOX_TINY` / `BOX_HUGE` | 9 dòng | Giữ nguyên / Người | Cảnh báo kích thước dị biệt; người quan sát xem có cần lọc bỏ không. |
| `CLASS_RARE` | 4 lần | Giữ nguyên | Cảnh báo mất cân bằng dữ liệu ở cấp dataset. |

### Cơ chế hàng đợi người duyệt (`05_review_queue.csv`):
- **Thứ tự ưu tiên:** Hàng đợi đẩy 6 ảnh dính lỗi `MISSING_LABEL_FILE` lên đầu tiên (ưu tiên tuyệt đối vì đây là lỗi nghiêm trọng `ERROR`, nếu không xử lý thì pipeline chắc chắn kết luận `Rework`). Các ảnh tiếp theo được sắp xếp theo trọng số cảnh báo giảm dần (ưu tiên cao cho `POSSIBLE_WRONG_CLASS` và `POSSIBLE_MISSING` có độ tin cậy `conf` cao).
- **Hiệu quả ngân sách:** Với ngân sách duyệt tối đa 80 ảnh, người duyệt mô phỏng đã xử lý thành công 6 ảnh thiếu nhãn và 74 ảnh có cảnh báo ngữ nghĩa phức tạp nhất, đưa số ảnh còn nghi vấn từ 102 ảnh xuống chỉ còn 16 ảnh (tỉ lệ 7.88%).

---

## 3. Calibration (2 ngưỡng)

| Tham số | Khởi đầu | Đã chọn | Precision / Recall (trước → sau) | Lý do (đánh đổi) |
|---|---|---|---|---|
| `duplicates.phash_dist` | 2 | **8** | DUP_IMAGE_NEAR: 1.00 / 0.50 → **1.00 / 0.67** (F1: 0.67 → 0.80) | Tăng khả năng bắt ảnh gần trùng từ 50% lên 67% mà vẫn giữ Precision tuyệt đối 100% (không xóa nhầm ảnh tốt). Ngưỡng 16 tuy cho Recall cao hơn (0.83) nhưng rủi ro loại nhầm ảnh góc máy tương tự trên tập dữ liệu thật. |
| `second_opinion.conf` | 0.25 | **0.8** | WRONG_CLASS: 0.56 / 0.83 → **1.00 / 0.83**<br>MISSING: 0.50 / 1.00 → **0.67 / 0.75** | Ngưỡng 0.25 khiến model AI phát ra quá nhiều báo động giả (Precision chỉ 50-56%), làm hàng đợi phình to lên 145 ảnh và vượt ngân sách 80 ảnh, dẫn đến việc bị kẹt ở trạng thái `Hold`. Chọn ngưỡng 0.8 giúp bộ lọc chỉ tin các phát hiện chắc chắn nhất của AI (Precision đạt 100% cho WRONG_CLASS), tập trung công sức người duyệt vào các lỗi thật sự. |

### Điểm calibration có thể đánh lừa:
- **Tập calib quá nhỏ (chỉ 39 ảnh):** Mỗi ca lỗi chèn chỉ có từ 2 đến 6 mẫu, nên Precision và Recall nhảy vọt từng bước lớn (ví dụ từ 50% lên 67% hay 83%).
- **Lỗi nhân tạo khác lỗi tự nhiên:** Các lỗi chèn trong calib (như đổi `person` thành `car`) rất rõ ràng và tách biệt; trong khi trên dữ liệu thô thật (`raw`), model AI thường nhầm lẫn giữa các lớp tương đồng (`car`, `truck`, `bus`) hoặc trong điều kiện khuất tầm nhìn, bóng râm.
- **Bằng chứng dữ liệu:** Nếu đẩy `phash_dist` lên mức 16 hoặc 20 theo điểm số cao nhất của bảng sweep calib, khi chạy trên dữ liệu thật bước intake sẽ loại bỏ thêm nhiều ảnh có cùng khung cảnh đường phố (dù là các xe khác nhau di chuyển), dẫn đến hiện tượng "diệt nhầm" ảnh tốt. Vì vậy chọn `phash_dist = 8` là điểm cân bằng an toàn.

---

## 4. Cửa chặn và điều pipeline KHÔNG bắt được

### (a) Bằng chứng Quality Gate hoạt động chính xác:
Để kiểm chứng cửa chặn, ta giả lập kịch bản dự án không có ngân sách duyệt người (`--budget 0`):
```powershell
python -m pipeline.run --budget 0 --reports work/rep_nb --export-dir work/exp_nb
```
- **Kết quả:** Pipeline phát hiện 6 ảnh thiếu nhãn (`MISSING_LABEL_FILE`) chưa được người xử lý.
- **Kết luận:** **`REWORK`** — *"Còn 6 lỗi bắt buộc (severity ERROR) chưa giải quyết"*.
- **Mã thoát (Exit code):** `20`.
- **Hành vi xuất:** Hoàn toàn **không xuất** thư mục dữ liệu sạch (`work/exp_nb/clean_v1` không được tạo ra). Điều này chứng minh cửa chặn đã ngăn chặn tuyệt đối việc phát hành dữ liệu bẩn ra môi trường sản xuất.

### (b) Điểm mù mà pipeline không thể bắt được:
1. **Box lỏng nhẹ (Loose Box vi mô):** Nếu người gán nhãn vẽ viền hơi rộng ra ngoài vật thể nhưng vẫn đạt $\text{IoU} \ge 0.5$, cả quy tắc cú pháp lẫn model đối chứng đều coi đây là "trùng khớp chấp nhận được" và bỏ qua.
2. **Lỗi ngụy trang ngữ cảnh mà cả hai model cùng nhầm:** Ví dụ một xe bán tải lớn bị cả người gán nhãn lẫn model `yolo26l` nhận diện nhầm thành xe tải nhỏ (`truck`), hoặc người ngồi trên xe máy bị dán nhãn thành người đi bộ mà model không phân biệt được.
3. **Ảnh biến dạng phi tuyến tính:** Ảnh bị crop sâu 80% rồi xoay góc nghiêng và thay đổi ánh sáng mạnh; giá trị pHash thay đổi quá nhiều khiến thuật toán không nhận diện được là ảnh trùng lặp.

---

## 5. Train: raw vs clean (tùy chọn, chấm riêng)
Chưa chạy — Pipeline được thiết lập, kiểm thử và chạy hoàn thiện trên môi trường máy trạm cục bộ (Windows, CPU). Thí nghiệm huấn luyện so sánh mô hình (YOLO26n, 20 epochs, 2 seeds) sẽ được thực hiện trên Google Colab có GPU T4 theo tài liệu [docs/COLAB.md](file:///C:/Users/hanng/.gemini/antigravity/scratch/K5-L2B-DAY09-NguyenTheTung-2A202603320-AutoQC-Pipeline-Lab/docs/COLAB.md).

---

## 6. Quyết định và ghi chú AI

### (a) Quyết định cuối cùng:
- **Quyết định:** **Release** (Phát hành chính thức).
- Toàn bộ các lỗi nghiêm trọng đã được máy và người dọn dẹp sạch sẽ. Tỉ lệ cảnh báo tồn đọng là **7.88%** nằm dưới ngưỡng trần 10%. Bộ dữ liệu xuất ra tại [`submission/export/clean_v1/`](file:///C:/Users/hanng/.gemini/antigravity/scratch/K5-L2B-DAY09-NguyenTheTung-2A202603320-AutoQC-Pipeline-Lab/submission/export/clean_v1) đi kèm tệp truy vết [`manifest.json`](file:///C:/Users/hanng/.gemini/antigravity/scratch/K5-L2B-DAY09-NguyenTheTung-2A202603320-AutoQC-Pipeline-Lab/submission/export/clean_v1/manifest.json) đã sẵn sàng để huấn luyện.

### (b) Ghi chú sử dụng AI hỗ trợ:
- **Prompt chính:** Yêu cầu AI hiện thực hóa 4 module Python (`label_format.py`, `gate.py`, `autofix.py`, `second_opinion.py`) dựa trên docstring đặc tả kỹ thuật, tuân thủ nguyên tắc TDD và vượt qua 79 bài unit test có sẵn.
- **Cách kiểm tra mã AI:** Chạy kiểm thử tự động `python -m pytest -q`, kiểm tra trực quan các ảnh nhãn bằng `scripts/viz_labels.py`, chạy thử nghiệm pipeline đầu cuối `pipeline.run` và rà soát bằng công cụ `scripts/check_submission.py`.
- **Tình huống AI từng nhầm lẫn & cách khắc phục:** Trong module `autofix.py`, thiết kế ban đầu dễ mắc bẫy xóa từng dòng nhãn tuần tự khiến chỉ số dòng ban đầu bị xê dịch (lệch vị trí của các dòng lỗi tiếp theo). Giải pháp là yêu cầu đọc toàn bộ file vào danh sách, gom lỗi theo từng file, đối chiếu số dòng gốc từ 1 đến $N$ trong một lượt duyệt duy nhất rồi mới ghi đè ra đĩa.

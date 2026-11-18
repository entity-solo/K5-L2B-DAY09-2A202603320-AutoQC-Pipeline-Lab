"""CHECK 6 — Ý kiến thứ hai: so nhãn với một model LỚN HƠN (yolo26l).   ★★★ (khó nhất, đáng điểm nhất)

Test:  pytest tests/test_second_opinion.py -q

Máy kiểm quy tắc, người kiểm ý nghĩa (slide). Các lỗi như thiếu nhãn / gán nhầm lớp hợp lệ / box lỏng
KHÔNG bắt được bằng quy tắc cú pháp. Ta nhờ một model mạnh hơn "nhìn lại" và CHỈ CẢNH BÁO (model cũng có thể sai):
những ảnh bị cờ sẽ vào hàng đợi cho NGƯỜI duyệt.

`preds[stem]` = list `[id_lớp, conf, cx, cy, w, h]` của model (lấy qua `get_preds(ds, cfg, "checker")` nếu preds=None).
`L = ds.valid_boxes(stem)` = list `(id_lớp, cx, cy, w, h)` của nhãn (đã bỏ dòng hỏng).
Ngưỡng ở `cfg["second_opinion"]`: conf, min_area_px, fp_conf, iou_missing, iou_match, iou_loose.
"""
from ..common import WARN, Issue, iou_xywh, parse_yolo_line
from ..model_cache import get_preds


def run(ds, cfg, preds=None):
    if preds is None:
        preds = get_preds(ds, cfg, "checker")

    so_cfg = cfg.get("second_opinion", {})
    conf_thresh = so_cfg.get("conf", 0.25)
    min_area_px = so_cfg.get("min_area_px", 600)
    fp_conf = so_cfg.get("fp_conf", 0.1)
    iou_missing = so_cfg.get("iou_missing", 0.3)
    iou_match = so_cfg.get("iou_match", 0.5)
    iou_loose = so_cfg.get("iou_loose", 0.5)

    issues = []

    for img_p in ds.image_files():
        stem = img_p.stem

        if stem not in preds:
            continue
        if not ds.label_path(stem).exists():
            continue

        size = ds.image_size(stem)
        if not size:
            continue
        img_w, img_h = size

        raw_preds = preds[stem]

        # 1. Lọc các dự đoán mạnh: conf >= conf VÀ diện tích px >= min_area_px
        P = [
            r for r in raw_preds
            if r[1] >= conf_thresh and (r[4] * img_w) * (r[5] * img_h) >= min_area_px
        ]

        # 2. Lấy các nhãn hợp lệ
        L = ds.valid_boxes(stem)

        # 3. Duyệt từng dự đoán trong P
        for r in P:
            p_cls, p_conf, p_cx, p_cy, p_w, p_h = r
            p_box = (p_cx, p_cy, p_w, p_h)

            cands = []
            for l_box in L:
                l_cls = l_box[0]
                iou = iou_xywh(p_box, l_box[1:])
                if iou >= iou_missing:
                    cands.append((l_cls, iou))

            if not cands:
                issues.append(
                    Issue(
                        "second_opinion",
                        WARN,
                        "POSSIBLE_MISSING",
                        stem,
                        "model thấy vật mà nhãn không có box",
                        line=None,
                        extra={"conf": p_conf},
                    )
                )
            else:
                same_cands = [iou for l_cls, iou in cands if l_cls == p_cls]
                if same_cands:
                    best_same_iou = max(same_cands)
                    if best_same_iou < iou_loose:
                        issues.append(
                            Issue(
                                "second_opinion",
                                WARN,
                                "POSSIBLE_LOOSE_BOX",
                                stem,
                                f"box lỏng (IoU={best_same_iou:.2f} < {iou_loose})",
                                line=None,
                                extra={"conf": p_conf, "iou": round(best_same_iou, 4)},
                            )
                        )
                    else:
                        # Đã phủ đúng lớp với IoU tốt -> không cờ
                        pass
                else:
                    diff_cands = [iou for l_cls, iou in cands if l_cls != p_cls]
                    best_diff_iou = max(diff_cands)
                    if best_diff_iou >= iou_match:
                        issues.append(
                            Issue(
                                "second_opinion",
                                WARN,
                                "POSSIBLE_WRONG_CLASS",
                                stem,
                                f"nghi gán nhầm lớp (IoU={best_diff_iou:.2f})",
                                line=None,
                                extra={"conf": p_conf, "iou": round(best_diff_iou, 4)},
                            )
                        )
                    else:
                        # Mơ hồ [iou_missing, iou_match) -> không cờ
                        pass

        # 4. Kiểm tra POSSIBLE_FALSE_POS cho từng dòng nhãn hợp lệ
        fp_preds = [r for r in raw_preds if r[1] >= fp_conf]
        label_lines = ds.read_label_lines(stem) or []

        for line_no, raw_line in label_lines:
            try:
                l_cls, l_cx, l_cy, l_w, l_h = parse_yolo_line(raw_line)
            except ValueError:
                continue

            if not (0 <= l_cls < len(ds.classes)):
                continue

            l_box = (l_cx, l_cy, l_w, l_h)
            matched = any(iou_xywh(l_box, pr[2:]) >= iou_missing for pr in fp_preds)

            if not matched:
                issues.append(
                    Issue(
                        "second_opinion",
                        WARN,
                        "POSSIBLE_FALSE_POS",
                        stem,
                        f"dòng {line_no}: box nhãn không khớp vật nào model thấy",
                        line=line_no,
                        extra={},
                    )
                )

    return issues

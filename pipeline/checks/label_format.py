"""CHECK 2 — Dòng nhãn YOLO: sai định dạng, ID lớp lạ, box tràn ảnh, box rỗng, box lặp.   (Script 2 trong slide)   ★★

Test:  pytest tests/test_label_format.py -q

Mỗi dòng nhãn: `id cx cy w h` (5 số, toạ độ 0–1). Trả về list[Issue]; `Issue.line` = số dòng (đếm từ 1).

| code             | severity | khi nào                                                                  |
|------------------|----------|--------------------------------------------------------------------------|
| BAD_FORMAT       | ERROR    | không đúng 5 cột số (dùng `parse_yolo_line`, bắt `ValueError`)           |
| BAD_CLASS_ID     | ERROR    | id lớp ngoài 0..len(ds.classes)-1                                        |
| BOX_ZERO         | ERROR    | w <= 0 hoặc h <= 0                                                       |
| BOX_OUT_OF_IMAGE | ERROR    | mép box vượt [0,1] quá `cfg["label_format"]["overflow_tol"]`; extra={"overflow": mức tràn} |
| DUP_BOX          | ERROR    | cùng lớp với một dòng TRƯỚC ĐÓ và IoU > `dup_box_iou`; báo ở dòng SAU    |
| BOX_TINY         | WARN     | cạnh ngắn của box (px) < `min_box_px`  (cần `ds.image_size(stem)`)       |
| BOX_HUGE         | WARN     | w*h > `max_box_frac`                                                     |
"""
from ..common import ERROR, WARN, Issue, iou_xywh, parse_yolo_line


def run(ds, cfg):
    fmt_cfg = cfg.get("label_format", {})
    overflow_tol = fmt_cfg.get("overflow_tol", 0.002)
    min_box_px = fmt_cfg.get("min_box_px", 12)
    max_box_frac = fmt_cfg.get("max_box_frac", 0.95)
    dup_box_iou = fmt_cfg.get("dup_box_iou", 0.9)
    num_classes = len(ds.classes)

    issues = []

    for lf in ds.label_files():
        stem = lf.stem
        lines_data = ds.read_label_lines(stem)
        if not lines_data:
            continue

        size = ds.image_size(stem)
        img_w, img_h = size if size else (None, None)

        prev_boxes = []  # list of (cls, (cx, cy, w, h))

        for line_no, raw_line in lines_data:
            try:
                cls, cx, cy, w, h = parse_yolo_line(raw_line)
            except ValueError as e:
                issues.append(
                    Issue("label_format", ERROR, "BAD_FORMAT", stem, f"dòng {line_no} sai định dạng: {e}", line=line_no)
                )
                continue

            if cls < 0 or cls >= num_classes:
                issues.append(
                    Issue("label_format", ERROR, "BAD_CLASS_ID", stem, f"dòng {line_no}: id lớp {cls} ngoài 0..{num_classes-1}", line=line_no)
                )
                continue

            if w <= 0 or h <= 0:
                issues.append(
                    Issue("label_format", ERROR, "BOX_ZERO", stem, f"dòng {line_no}: box rộng={w} hoặc cao={h} <= 0", line=line_no)
                )
                continue

            # Geometry check
            x1 = cx - w / 2
            x2 = cx + w / 2
            y1 = cy - h / 2
            y2 = cy + h / 2

            overflow = max(0.0, -x1, x2 - 1.0, -y1, y2 - 1.0)
            if overflow > overflow_tol:
                issues.append(
                    Issue(
                        "label_format",
                        ERROR,
                        "BOX_OUT_OF_IMAGE",
                        stem,
                        f"dòng {line_no}: box tràn ảnh {overflow:.4f}",
                        line=line_no,
                        extra={"overflow": overflow},
                    )
                )

            # Duplicate box check with earlier lines of same class
            curr_box = (cx, cy, w, h)
            is_dup = False
            for p_cls, p_box in prev_boxes:
                if p_cls == cls and iou_xywh(curr_box, p_box) > dup_box_iou:
                    is_dup = True
                    break

            if is_dup:
                issues.append(
                    Issue("label_format", ERROR, "DUP_BOX", stem, f"dòng {line_no}: trùng box cùng lớp với dòng trước", line=line_no)
                )

            prev_boxes.append((cls, curr_box))

            # Warnings: Tiny & Huge
            if img_w is not None and img_h is not None:
                short_side_px = min(w * img_w, h * img_h)
                if short_side_px < min_box_px:
                    issues.append(
                        Issue(
                            "label_format",
                            WARN,
                            "BOX_TINY",
                            stem,
                            f"dòng {line_no}: cạnh ngắn {short_side_px:.1f}px < {min_box_px}px",
                            line=line_no,
                        )
                    )

            if (w * h) > max_box_frac:
                issues.append(
                    Issue(
                        "label_format",
                        WARN,
                        "BOX_HUGE",
                        stem,
                        f"dòng {line_no}: diện tích box {(w * h):.2f} > {max_box_frac}",
                        line=line_no,
                    )
                )

    return issues

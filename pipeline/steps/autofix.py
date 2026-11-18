"""BƯỚC 2/4 — Sửa tự động những lỗi bắt buộc mà máy sửa được AN TOÀN.   ★★

Test:  pytest tests/test_autofix.py -q

`fix(ds, issues, cfg) -> list[dict]`: duyệt `issues` (chỉ lỗi severity ERROR), sửa thẳng vào thư mục `ds`,
và trả về danh sách thay đổi; mỗi phần tử có khoá: image, line, action, before, after
(đây chính là file `03_fixes.csv` — bằng chứng pipeline đã làm gì, người có thể kiểm lại).

| code lỗi                                       | cách sửa                                    | action           |
|------------------------------------------------|---------------------------------------------|------------------|
| BAD_FORMAT, BAD_CLASS_ID, BOX_ZERO, DUP_BOX    | xoá dòng đó khỏi file nhãn                  | "drop_line"      |
| BOX_OUT_OF_IMAGE                               | cắt box về trong [0,1] (giữ nguyên lớp)     | "clip_box"       |
| MISSING_LABEL_FILE                             | KHÔNG sửa file (máy không thể bịa nhãn): ghi 1 dòng fix, before="(không có file)", after="chuyển người gán" | "needs_label" |
| BAD_CLASS_NAME                                 | ghi lại `names` trong data.yaml đúng `cfg["classes"]` | "rename_classes" |
| DUP_IMAGE_*, LEAK_TEST, CORRUPT_IMAGE, BAD_SIZE| xoá ảnh + nhãn khỏi `ds`                    | "remove_image"   |
"""
from collections import defaultdict
from pathlib import Path

import yaml

from ..common import ERROR, parse_yolo_line

REMOVE_IMAGE_CODES = {
    "LEAK_TEST",
    "CORRUPT_IMAGE",
    "BAD_SIZE",
}
DROP_LINE_CODES = {"BAD_FORMAT", "BAD_CLASS_ID", "BOX_ZERO", "DUP_BOX"}


def fix(ds, issues, cfg):
    # Chỉ xử lý các lỗi có mức độ nghiêm trọng ERROR
    err_issues = [i for i in issues if i.severity == ERROR]
    if not err_issues:
        return []

    fixes = []
    removed_images = set()

    # 1. Xử lý xóa ảnh (remove_image)
    for i in err_issues:
        code = i.code
        stem = i.image
        if code in REMOVE_IMAGE_CODES or code.startswith("DUP_IMAGE_"):
            if stem not in removed_images:
                removed_images.add(stem)
                img_p = ds.image_path(stem)
                if img_p and img_p.exists():
                    img_p.unlink()
                lbl_p = ds.label_path(stem)
                if lbl_p and lbl_p.exists():
                    lbl_p.unlink()
                fixes.append({
                    "image": stem,
                    "line": "",
                    "action": "remove_image",
                    "before": f"loại ảnh ({code})",
                    "after": "đã xoá ảnh + nhãn",
                })

    # 2. Xử lý chuẩn hóa tên lớp trong data.yaml (rename_classes)
    bad_class_name_issues = [i for i in err_issues if i.code == "BAD_CLASS_NAME"]
    if bad_class_name_issues:
        y_data = {}
        if ds.yaml_path.exists():
            try:
                y_data = yaml.safe_load(ds.yaml_path.read_text(encoding="utf-8")) or {}
            except Exception:
                y_data = {}
        before_names = str(y_data.get("names", ""))
        y_data["names"] = list(cfg["classes"])
        ds.yaml_path.write_text(yaml.safe_dump(y_data, sort_keys=False, allow_unicode=True), encoding="utf-8")
        fixes.append({
            "image": "data.yaml",
            "line": "",
            "action": "rename_classes",
            "before": before_names,
            "after": str(cfg["classes"]),
        })

    # 3. Xử lý ảnh thiếu file nhãn (needs_label)
    needs_label_handled = set()
    for i in err_issues:
        if i.code == "MISSING_LABEL_FILE":
            stem = i.image
            if stem not in removed_images and stem not in needs_label_handled:
                needs_label_handled.add(stem)
                fixes.append({
                    "image": stem,
                    "line": "",
                    "action": "needs_label",
                    "before": "(không có file)",
                    "after": "chuyển người gán",
                })

    # 4. Xử lý các lỗi theo dòng trong file nhãn (drop_line, clip_box)
    # Gom issues theo (stem, line)
    line_issues_by_img = defaultdict(lambda: defaultdict(list))
    for i in err_issues:
        stem = i.image
        if stem in removed_images or stem in ("data.yaml", "<dataset>"):
            continue
        if i.line is not None and i.line != "":
            line_issues_by_img[stem][int(i.line)].append(i.code)

    for stem, lines_map in line_issues_by_img.items():
        lbl_p = ds.label_path(stem)
        if not lbl_p.exists():
            continue

        raw_lines = lbl_p.read_text(encoding="utf-8", errors="replace").splitlines()
        output_lines = []

        for ln_idx, raw_line in enumerate(raw_lines, 1):
            if ln_idx not in lines_map:
                output_lines.append(raw_line)
                continue

            codes = set(lines_map[ln_idx])

            # Nếu dòng dính lỗi xoá (drop_line codes)
            if any(c in DROP_LINE_CODES for c in codes):
                fixes.append({
                    "image": stem,
                    "line": ln_idx,
                    "action": "drop_line",
                    "before": raw_line,
                    "after": "",
                })
                # Bỏ qua dòng này (không thêm vào output_lines)
            elif "BOX_OUT_OF_IMAGE" in codes:
                # Cắt box về [0, 1]
                try:
                    c, cx, cy, w, h = parse_yolo_line(raw_line)
                    x1 = cx - w / 2
                    x2 = cx + w / 2
                    y1 = cy - h / 2
                    y2 = cy + h / 2

                    x1_c = max(0.0, min(1.0, x1))
                    x2_c = max(0.0, min(1.0, x2))
                    y1_c = max(0.0, min(1.0, y1))
                    y2_c = max(0.0, min(1.0, y2))

                    w_c = x2_c - x1_c
                    h_c = y2_c - y1_c

                    if w_c <= 0.0 or h_c <= 0.0:
                        # Box nằm hẳn ngoài ảnh -> xoá dòng
                        fixes.append({
                            "image": stem,
                            "line": ln_idx,
                            "action": "drop_line",
                            "before": raw_line,
                            "after": "",
                        })
                    else:
                        cx_c = (x1_c + x2_c) / 2
                        cy_c = (y1_c + y2_c) / 2
                        after_str = f"{int(c)} {cx_c:.6g} {cy_c:.6g} {w_c:.6g} {h_c:.6g}"
                        fixes.append({
                            "image": stem,
                            "line": ln_idx,
                            "action": "clip_box",
                            "before": raw_line,
                            "after": after_str,
                        })
                        output_lines.append(after_str)
                except ValueError:
                    fixes.append({
                        "image": stem,
                        "line": ln_idx,
                        "action": "drop_line",
                        "before": raw_line,
                        "after": "",
                    })
            else:
                output_lines.append(raw_line)

        # Ghi lại file nhãn
        new_content = "\n".join(output_lines) + ("\n" if output_lines else "")
        lbl_p.write_text(new_content, encoding="utf-8")

    return fixes

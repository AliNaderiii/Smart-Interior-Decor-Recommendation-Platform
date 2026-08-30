#!/usr/bin/env python3
"""Validate a client-supplied product catalog (CSV) against CATALOG_SPEC.fa.md.

Stage 4 / T-4.6. The client fills `docs/client/catalog-template.csv` in Excel
and runs this before sending the file back. Every rule stated in
`docs/client/CATALOG_SPEC.fa.md` is enforced here, and every message is in
Persian with a spreadsheet row number, because the person fixing the file is
the client's catalog admin, not an engineer.

Design notes
------------
* Row numbers reported are **spreadsheet** row numbers (header = row 1), not
  zero-based indices, so "سطر ۷" means what the client sees in Excel.
* Persian/Arabic-Indic digits are normalised before numeric checks: a catalog
  typed in Excel with a Persian keyboard is a *correct* catalog, not an error.
* Links are checked for shape only. Liveness is a separate, network-bound
  concern already covered by the seller-link job; this tool must run offline.
* Exit code is 1 if any ERROR exists, 0 otherwise. Warnings never fail the run
  but are printed, because "your file is fine but 40 products share one photo"
  is worth saying.

Usage
    python scripts/validate_catalog.py my-catalog.csv
    python scripts/validate_catalog.py my-catalog.csv --json report.json
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

# --- the spec, in one place -------------------------------------------------
# These lists are the ones published in CATALOG_SPEC.fa.md. If they change,
# change them here and in that document together.

REQUIRED_COLUMNS = [
    "id",
    "title_fa",
    "title_en",
    "category",
    "room_type",
    "price_toman",
    "seller",
    "seller_link",
    "image_url",
    "dimensions_cm",
    "color_palette",
    "style_tags",
    "material_tags",
    "description_for_embedding",
]

ALLOWED_CATEGORY = {"sofa", "chair", "coffee_table", "rug", "lighting", "storage", "decor"}
ALLOWED_ROOM_TYPE = {"living_room"}
ALLOWED_STYLE = {"modern", "minimal", "classic", "industrial", "scandinavian", "boho"}
ALLOWED_MATERIAL = {"wood", "metal", "fabric", "leather", "rattan"}

MIN_PRODUCTS = 50
MIN_PRICE_TOMAN = 1_000
MAX_PRICE_TOMAN = 5_000_000_000
MIN_DESCRIPTION_CHARS = 15

ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")
HEX_COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")
DIMENSIONS_RE = re.compile(
    r"^\s*(\d+(?:\.\d+)?)\s*[xX×]\s*(\d+(?:\.\d+)?)\s*[xX×]\s*(\d+(?:\.\d+)?)\s*$"
)

PERSIAN_LABEL = {
    "id": "شناسه",
    "title_fa": "نام فارسی",
    "title_en": "نام انگلیسی",
    "category": "دسته",
    "room_type": "نوع فضا",
    "price_toman": "قیمت",
    "seller": "فروشنده",
    "seller_link": "لینک فروشنده",
    "image_url": "نشانی تصویر",
    "dimensions_cm": "ابعاد",
    "color_palette": "رنگ‌ها",
    "style_tags": "سبک",
    "material_tags": "جنس",
    "description_for_embedding": "توصیف",
}


def to_persian_digits(value: object) -> str:
    """Render a number in Persian digits, so messages read naturally."""
    table = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")
    return str(value).translate(table)


def normalise_digits(text: str) -> str:
    """Fold Persian (۰-۹) and Arabic-Indic (٠-٩) digits to ASCII."""
    out = []
    for ch in text:
        if "0" <= ch <= "9":
            out.append(ch)
            continue
        try:
            out.append(str(unicodedata.digit(ch)))
        except (TypeError, ValueError):
            out.append(ch)
    return "".join(out)


@dataclass
class Finding:
    severity: str  # "error" | "warning"
    row: int | None
    column: str | None
    message: str

    def render(self) -> str:
        where = ""
        if self.row is not None:
            where = f"سطر {to_persian_digits(self.row)}"
            if self.column:
                where += f" · ستون «{PERSIAN_LABEL.get(self.column, self.column)}»"
            where += ": "
        elif self.column:
            where = f"ستون «{PERSIAN_LABEL.get(self.column, self.column)}»: "
        return where + self.message


@dataclass
class Report:
    findings: list[Finding] = field(default_factory=list)
    rows_checked: int = 0

    def error(self, message: str, row: int | None = None, column: str | None = None) -> None:
        self.findings.append(Finding("error", row, column, message))

    def warn(self, message: str, row: int | None = None, column: str | None = None) -> None:
        self.findings.append(Finding("warning", row, column, message))

    @property
    def errors(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == "error"]

    @property
    def warnings(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == "warning"]


# --- per-field checks -------------------------------------------------------


def check_tag_list(
    raw: str, allowed: set[str], column: str, row: int, report: Report, *, required: bool = True
) -> None:
    items = [t.strip() for t in raw.split(",") if t.strip()]
    if not items:
        if required:
            report.error("خالی است و باید پر شود.", row, column)
        return
    for item in items:
        if item not in allowed:
            allowed_txt = " · ".join(sorted(allowed))
            report.error(
                f"مقدار «{item}» مجاز نیست. مقادیر مجاز: {allowed_txt}",
                row,
                column,
            )


def check_url(raw: str, column: str, row: int, report: Report) -> None:
    if not raw:
        report.error("خالی است و باید پر شود.", row, column)
        return
    if raw.startswith("http://"):
        report.error("باید با https:// شروع شود (نه http://).", row, column)
        return
    if not raw.startswith("https://"):
        report.error("باید یک نشانی کامل باشد و با https:// شروع شود.", row, column)
        return
    if " " in raw:
        report.error("نباید فاصله داشته باشد.", row, column)


def check_row(row_num: int, row: dict[str, str], report: Report, seen_ids: dict[str, int]) -> None:
    def val(col: str) -> str:
        return (row.get(col) or "").strip()

    # id — unique, restricted charset
    pid = val("id")
    if not pid:
        report.error("خالی است و باید پر شود.", row_num, "id")
    else:
        if not ID_RE.match(pid):
            report.error(
                "فقط حروف انگلیسی، عدد، خط تیره و زیرخط مجاز است (مثلاً sofa-014).",
                row_num,
                "id",
            )
        if pid in seen_ids:
            first = to_persian_digits(seen_ids[pid])
            report.error(f"شناسهٔ «{pid}» تکراری است؛ پیش‌تر در سطر {first} آمده.", row_num, "id")
        else:
            seen_ids[pid] = row_num

    # simple required text fields
    for col in ("title_fa", "title_en", "seller"):
        if not val(col):
            report.error("خالی است و باید پر شود.", row_num, col)

    # controlled vocabularies
    category = val("category")
    if not category:
        report.error("خالی است و باید پر شود.", row_num, "category")
    elif category not in ALLOWED_CATEGORY:
        report.error(
            f"مقدار «{category}» مجاز نیست. مقادیر مجاز: {' · '.join(sorted(ALLOWED_CATEGORY))}",
            row_num,
            "category",
        )

    room = val("room_type")
    if not room:
        report.error("خالی است و باید پر شود.", row_num, "room_type")
    elif room not in ALLOWED_ROOM_TYPE:
        report.error(
            f"مقدار «{room}» مجاز نیست. فعلاً فقط {' · '.join(sorted(ALLOWED_ROOM_TYPE))} "
            "پشتیبانی می‌شود.",
            row_num,
            "room_type",
        )

    # price — digits only, sane range
    price_raw = val("price_toman")
    if not price_raw:
        report.error("خالی است و باید پر شود.", row_num, "price_toman")
    else:
        cleaned = normalise_digits(price_raw).replace(",", "").replace("٬", "").strip()
        if not cleaned.isdigit():
            report.error(
                f"«{price_raw}» عدد صحیح نیست. فقط رقم بنویسید، بدون کاما و بدون کلمهٔ تومان "
                "(مثلاً 24500000).",
                row_num,
                "price_toman",
            )
        else:
            price = int(cleaned)
            if price < MIN_PRICE_TOMAN:
                report.error(
                    f"قیمت {to_persian_digits(price)} تومان غیرواقعی به نظر می‌رسد. "
                    "آیا قیمت به تومان نوشته شده؟",
                    row_num,
                    "price_toman",
                )
            elif price > MAX_PRICE_TOMAN:
                report.error(
                    f"قیمت {to_persian_digits(price)} تومان بیش از حد بزرگ است. "
                    "شاید اشتباهی صفر اضافه شده باشد.",
                    row_num,
                    "price_toman",
                )

    # links
    check_url(val("seller_link"), "seller_link", row_num, report)
    check_url(val("image_url"), "image_url", row_num, report)

    # dimensions
    dims = normalise_digits(val("dimensions_cm"))
    if not dims:
        report.error("خالی است و باید پر شود.", row_num, "dimensions_cm")
    else:
        match = DIMENSIONS_RE.match(dims)
        if not match:
            report.error(
                "قالب درست «طول×عرض×ارتفاع» به سانتی‌متر است، مثلاً 220x95x85.",
                row_num,
                "dimensions_cm",
            )
        elif any(float(g) <= 0 for g in match.groups()):
            report.error("ابعاد باید بزرگ‌تر از صفر باشد.", row_num, "dimensions_cm")

    # colours
    colors = [c.strip() for c in val("color_palette").split(",") if c.strip()]
    if not colors:
        report.error("خالی است و باید پر شود (مثلاً #2D8C50).", row_num, "color_palette")
    else:
        for color in colors:
            if not HEX_COLOR_RE.match(color):
                report.error(
                    f"«{color}» کد رنگ معتبر نیست. قالب درست شش‌رقمی است، مثلاً #2D8C50.",
                    row_num,
                    "color_palette",
                )

    check_tag_list(val("style_tags"), ALLOWED_STYLE, "style_tags", row_num, report)
    check_tag_list(val("material_tags"), ALLOWED_MATERIAL, "material_tags", row_num, report)

    # description
    desc = val("description_for_embedding")
    if not desc:
        report.error("خالی است و باید پر شود.", row_num, "description_for_embedding")
    elif len(desc) < MIN_DESCRIPTION_CHARS:
        report.warn(
            "خیلی کوتاه است. توصیف دقیق‌تر، پیشنهادهای بهتری تولید می‌کند.",
            row_num,
            "description_for_embedding",
        )


# --- file-level checks ------------------------------------------------------


def validate(path: Path) -> Report:
    report = Report()

    try:
        # utf-8-sig strips the BOM Excel writes; without it the first header
        # cell would be "\ufeffid" and every row would look broken.
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            fieldnames = reader.fieldnames or []
            rows = list(reader)
    except UnicodeDecodeError:
        report.error(
            "فایل با کدگذاری UTF-8 ذخیره نشده است. در اکسل هنگام ذخیره، گزینهٔ "
            "«CSV UTF-8» را انتخاب کنید."
        )
        return report
    except FileNotFoundError:
        report.error(f"فایل پیدا نشد: {path}")
        return report

    present = [c.strip() for c in fieldnames]
    missing = [c for c in REQUIRED_COLUMNS if c not in present]
    if missing:
        for col in missing:
            # column= is deliberately omitted: Finding.render() would prefix the
            # label again and the line would read "ستون «قیمت»: ستون «قیمت» …".
            report.error(f"ستون «{PERSIAN_LABEL.get(col, col)}» ({col}) در فایل وجود ندارد.")
        # Without the columns, per-row checks would produce noise.
        return report

    unexpected = [c for c in present if c and c not in REQUIRED_COLUMNS]
    for col in unexpected:
        report.warn(f"ستون ناشناختهٔ «{col}» نادیده گرفته می‌شود.")

    seen_ids: dict[str, int] = {}
    for index, row in enumerate(rows):
        row_num = index + 2  # header is spreadsheet row 1
        if not any((v or "").strip() for v in row.values()):
            continue  # blank trailing rows are an Excel artefact, not an error
        report.rows_checked += 1
        check_row(row_num, row, report, seen_ids)

    if report.rows_checked == 0:
        report.error("فایل هیچ محصولی ندارد.")
    elif report.rows_checked < MIN_PRODUCTS:
        report.warn(
            f"تعداد محصولات {to_persian_digits(report.rows_checked)} است. برای اینکه "
            f"پیشنهادها معنادار باشند دست‌کم {to_persian_digits(MIN_PRODUCTS)} محصول "
            "توصیه می‌شود."
        )

    images = [
        (r.get("image_url") or "").strip() for r in rows if (r.get("image_url") or "").strip()
    ]
    if images and len(set(images)) < len(images):
        duplicates = len(images) - len(set(images))
        report.warn(
            f"{to_persian_digits(duplicates)} محصول تصویر تکراری دارند. "
            "تصویر اختصاصی برای هر محصول نتیجهٔ بهتری می‌دهد."
        )

    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="بررسی فایل کاتالوگ محصولات (CSV) پیش از تحویل به تیم فنی."
    )
    parser.add_argument("csv_path", type=Path, help="مسیر فایل CSV")
    parser.add_argument("--json", type=Path, default=None, help="ذخیرهٔ گزارش به صورت JSON")
    args = parser.parse_args(argv)

    report = validate(args.csv_path)

    print(f"بررسی فایل: {args.csv_path}")
    print(f"تعداد سطرهای بررسی‌شده: {to_persian_digits(report.rows_checked)}")
    print("-" * 60)

    if report.errors:
        print(f"\n[خطا] {to_persian_digits(len(report.errors))} مورد — باید اصلاح شود:\n")
        for finding in report.errors:
            print(f"  ✕ {finding.render()}")

    if report.warnings:
        print(f"\n[هشدار] {to_persian_digits(len(report.warnings))} مورد — اختیاری:\n")
        for finding in report.warnings:
            print(f"  ! {finding.render()}")

    print("-" * 60)
    if report.errors:
        print("نتیجه: فایل آمادهٔ تحویل نیست. موارد بالا را اصلاح و دوباره اجرا کنید.")
    elif report.warnings:
        print("نتیجه: فایل قابل قبول است. هشدارها اجباری نیستند.")
    else:
        print("نتیجه: فایل بدون اشکال است. ✓")

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(
            json.dumps(
                {
                    "file": str(args.csv_path),
                    "rows_checked": report.rows_checked,
                    "error_count": len(report.errors),
                    "warning_count": len(report.warnings),
                    "findings": [
                        {
                            "severity": f.severity,
                            "row": f.row,
                            "column": f.column,
                            "message": f.message,
                        }
                        for f in report.findings
                    ],
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    return 1 if report.errors else 0


if __name__ == "__main__":
    sys.exit(main())

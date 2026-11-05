"""
Genera los marcadores ArUco para imprimir y pegar en la placa.

Uso:
    python pc/tools/generate_aruco_sheet.py
    python pc/tools/generate_aruco_sheet.py --output docs/marcadores_aruco

Configuración:
    pc/config.json -> plate.marker_dictionary, plate.marker_size_cm y marker_ids.

Salida:
    aruco_0.png ... aruco_3.png   (marcador individual con margen blanco)
    hoja_marcadores_A4.png
    hoja_marcadores_A4.pdf        (imprimir al 100%, A4)
"""

from __future__ import annotations

import argparse
from pathlib import Path

import cv2
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
PC_DIR = ROOT / "pc"
CONFIG_PATH = PC_DIR / "config.json"


def load_plate_config():
    import json

    with CONFIG_PATH.open("r", encoding="utf-8") as file:
        config = json.load(file)
    return config["plate"]


def get_font(size_px: int):
    candidates = [
        "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/segoeui.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for candidate in candidates:
        if Path(candidate).is_file():
            try:
                return ImageFont.truetype(candidate, size_px)
            except OSError:
                pass
    return ImageFont.load_default()


def marker_image(dictionary, marker_id: int, side_px: int) -> Image.Image:
    gray = cv2.aruco.generateImageMarker(dictionary, marker_id, side_px)
    return Image.fromarray(gray, mode="L").convert("RGB")


def generate_marker_files(plate: dict, output_dir: Path, dpi: int) -> tuple[int, int]:
    ids = [int(value) for value in plate["marker_ids"]]
    dictionary_id = getattr(cv2.aruco, plate["marker_dictionary"])
    dictionary = cv2.aruco.getPredefinedDictionary(dictionary_id)

    side_px = int(round(plate["marker_size_cm"] / 2.54 * dpi))
    quiet_px = int(round(1.0 / 2.54 * dpi))  # 1 cm de margen blanco
    total = side_px + 2 * quiet_px

    for marker_id in ids:
        canvas = Image.new("RGB", (total, total), "white")
        marker = marker_image(dictionary, marker_id, side_px)
        canvas.paste(marker, (quiet_px, quiet_px))
        canvas.save(output_dir / f"aruco_{marker_id}.png", dpi=(dpi, dpi))

    return side_px, quiet_px


def draw_centered_text(draw, box, text, font, fill="black"):
    left, top, right, bottom = box
    bbox = draw.textbbox((0, 0), text, font=font)
    width = bbox[2] - bbox[0]
    height = bbox[3] - bbox[1]
    x = left + (right - left - width) / 2
    y = top + (bottom - top - height) / 2 - bbox[1]
    draw.text((x, y), text, font=font, fill=fill)


def generate_sheet(plate: dict, output_dir: Path, dpi: int) -> None:
    dictionary = cv2.aruco.getPredefinedDictionary(
        getattr(cv2.aruco, plate["marker_dictionary"])
    )

    mm_to_px = dpi / 25.4
    page_w = int(round(210 * mm_to_px))
    page_h = int(round(297 * mm_to_px))
    marker_mm = float(plate["marker_size_cm"]) * 10.0
    marker_px = int(round(marker_mm * mm_to_px))
    quiet_mm = 10.0
    box_mm = marker_mm + 2 * quiet_mm
    box_px = int(round(box_mm * mm_to_px))
    quiet_px = int(round(quiet_mm * mm_to_px))

    def font_pt(points: float):
        return get_font(int(round(points * dpi / 72.0)))

    def mm(value: float) -> int:
        return int(round(value * mm_to_px))

    page = Image.new("RGB", (page_w, page_h), "white")
    draw = ImageDraw.Draw(page)
    title_font = font_pt(18)
    text_font = font_pt(10)
    label_font = font_pt(12)
    small_font = font_pt(8)

    margin_x = mm(20)
    draw.text(
        (margin_x, mm(16)),
        "MARCADORES ARUCO - PLATAFORMA DE PELOTA",
        font=title_font,
        fill="black",
    )
    lines = [
        "Imprimí esta hoja en A4 al 100% (sin ajustar a la página).",
        f"Cada cuadrado negro debe medir {marker_mm:.1f} x {marker_mm:.1f} mm. "
        "Recortá por la línea gris dejando 1 cm de margen blanco.",
        "Orden visto desde la cámara: ID 0 arriba-izq, ID 1 arriba-der, "
        "ID 2 abajo-der, ID 3 abajo-izq.",
    ]
    for index, line in enumerate(lines):
        draw.text(
            (margin_x, mm(28 + index * 6)),
            line,
            font=text_font,
            fill="black",
        )

    # Dos columnas de 60 mm y dos filas. Los marcadores de 4 cm quedan
    # centrados, con 1 cm de margen blanco alrededor.
    x_positions_mm = [35.0, 115.0]
    y_positions_mm = [58.0, 162.0]
    positions = [
        ("ID 0 - arriba izquierda", 0, x_positions_mm[0], y_positions_mm[0]),
        ("ID 1 - arriba derecha", 1, x_positions_mm[1], y_positions_mm[0]),
        ("ID 2 - abajo derecha", 2, x_positions_mm[1], y_positions_mm[1]),
        ("ID 3 - abajo izquierda", 3, x_positions_mm[0], y_positions_mm[1]),
    ]

    for label, marker_id, x_mm, y_mm in positions:
        left = mm(x_mm)
        top = mm(y_mm)
        right = left + box_px
        bottom = top + box_px
        draw.rectangle(
            [left, top, right, bottom],
            outline=(190, 190, 190),
            width=max(1, mm(0.3)),
        )
        cut = mm(4)
        for cx, cy, dx, dy in (
            (left, top, 1, 1),
            (right, top, -1, 1),
            (left, bottom, 1, -1),
            (right, bottom, -1, -1),
        ):
            draw.line(
                [(cx, cy), (cx + dx * cut, cy)],
                fill=(120, 120, 120),
                width=max(1, mm(0.25)),
            )
            draw.line(
                [(cx, cy), (cx, cy + dy * cut)],
                fill=(120, 120, 120),
                width=max(1, mm(0.25)),
            )

        marker = marker_image(dictionary, marker_id, marker_px)
        page.paste(marker, (left + quiet_px, top + quiet_px))
        draw.text(
            (left, bottom + mm(3)),
            label,
            font=label_font,
            fill="black",
        )
        draw.text(
            (left, bottom + mm(9)),
            "Recortar por el borde gris.",
            font=small_font,
            fill=(60, 60, 60),
        )

    draw.text(
        (margin_x, page_h - mm(18)),
        "Tip: usá papel mate. Si el marcador queda brillante, la cámara puede "
        "no detectarlo.",
        font=small_font,
        fill=(50, 50, 50),
    )

    sheet_png = output_dir / "hoja_marcadores_A4.png"
    sheet_pdf = output_dir / "hoja_marcadores_A4.pdf"
    page.save(sheet_png, dpi=(dpi, dpi))
    page.save(sheet_pdf, "PDF", resolution=float(dpi))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Generar hoja de marcadores ArUco")
    parser.add_argument("--output", default=str(ROOT / "docs" / "marcadores_aruco"))
    parser.add_argument("--dpi", type=int, default=600)
    args = parser.parse_args(argv)
    if args.dpi < 200:
        print("Usá un DPI de al menos 200 para que el tamaño sea exacto.")
        return 2

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    plate = load_plate_config()
    generate_marker_files(plate, output_dir, args.dpi)
    generate_sheet(plate, output_dir, args.dpi)

    readme = f"""MARCADORES ARUCO PARA LA PLACA
================================

Archivo de impresión: hoja_marcadores_A4.pdf
Imprimí en A4 al 100%, sin "ajustar a la página".

Marcadores: IDs 0, 1, 2 y 3, diccionario {plate['marker_dictionary']}.
Cada cuadrado negro mide {plate['marker_size_cm']:.1f} x {plate['marker_size_cm']:.1f} cm.
Recortá dejando 1 cm de margen blanco alrededor.

Orden visto desde la cámara:
  ID 0: arriba-izquierda
  ID 1: arriba-derecha
  ID 2: abajo-derecha
  ID 3: abajo-izquierda

Centros en la placa de {plate['size_cm']:.1f} cm:
  config.json -> plate.marker_centers_cm
  Por defecto: (-10, +10), (+10, +10), (+10, -10), (-10, -10) cm.

Los archivos aruco_0.png ... aruco_3.png también están disponibles para
pegar en una hoja o imprimir por separado.
"""
    (output_dir / "LEEME_MARCADORES.txt").write_text(readme, encoding="utf-8")
    print(f"Generado en {output_dir}")
    print("  hoja_marcadores_A4.pdf")
    print("  hoja_marcadores_A4.png")
    print("  aruco_0.png ... aruco_3.png")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

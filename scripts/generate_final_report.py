from __future__ import annotations

from datetime import datetime
from pathlib import Path
import re
import shutil
import tempfile

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor
from PIL import Image, ImageDraw, ImageFont, ImageOps


ROOT = Path(r"C:\Users\Luis\Desktop\Proyecto2")
ATTACHMENTS = Path(
    r"C:\Users\Luis\AppData\Roaming\Code\agentSessionData"
    r"\0ecbac89-448f-4d4a-ba7e-639c077be199\attachments"
)
OUT_DIR = ROOT / "docs"
DOCX_PATH = OUT_DIR / "Reporte_Final_Taskboard.docx"
ASSET_DIR = Path(tempfile.gettempdir()) / "taskboard-final-report-assets"
CURRENT_RUBRIC_ID = "1c3d77e5-11d3-4c40-94b7-f82fc32f58fa"
CURRENT_COVER_ID = "00c46da7-0fcb-4439-b600-89ea5058d898"
NAVY = "15304B"
TEAL = "148A8A"
GREEN = "76B82A"
PALE = "EAF1F6"
GRAY = "5B6570"


def set_cell_shading(cell, fill: str) -> None:
    properties = cell._tc.get_or_add_tcPr()
    shading = OxmlElement("w:shd")
    shading.set(qn("w:fill"), fill)
    properties.append(shading)


def set_cell_text(cell, text: str, *, bold=False, color="222222", size=9) -> None:
    cell.text = ""
    cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
    paragraph = cell.paragraphs[0]
    paragraph.paragraph_format.space_after = Pt(2)
    paragraph.paragraph_format.space_before = Pt(2)
    run = paragraph.add_run(text)
    run.bold = bold
    run.font.name = "Arial"
    run.font.size = Pt(size)
    run.font.color.rgb = RGBColor.from_string(color)


def add_field(paragraph, instruction: str, placeholder: str = "1") -> None:
    run = paragraph.add_run()
    begin = OxmlElement("w:fldChar")
    begin.set(qn("w:fldCharType"), "begin")
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = f" {instruction} "
    separate = OxmlElement("w:fldChar")
    separate.set(qn("w:fldCharType"), "separate")
    text = OxmlElement("w:t")
    text.text = placeholder
    end = OxmlElement("w:fldChar")
    end.set(qn("w:fldCharType"), "end")
    run._r.extend([begin, instr, separate, text, end])


def add_hyperlink(paragraph, text: str, url: str) -> None:
    part = paragraph.part
    relationship_id = part.relate_to(
        url,
        "http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink",
        is_external=True,
    )
    hyperlink = OxmlElement("w:hyperlink")
    hyperlink.set(qn("r:id"), relationship_id)
    run = OxmlElement("w:r")
    properties = OxmlElement("w:rPr")
    color = OxmlElement("w:color")
    color.set(qn("w:val"), TEAL)
    properties.append(color)
    underline = OxmlElement("w:u")
    underline.set(qn("w:val"), "single")
    properties.append(underline)
    run.append(properties)
    value = OxmlElement("w:t")
    value.text = text
    run.append(value)
    hyperlink.append(run)
    paragraph._p.append(hyperlink)


def add_body(doc: Document, text: str, *, cite: str | None = None) -> None:
    paragraph = doc.add_paragraph(style="Normal")
    paragraph.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    paragraph.paragraph_format.widow_control = True
    paragraph.add_run(text)
    if cite:
        run = paragraph.add_run(f" {cite}")
        run.font.color.rgb = RGBColor.from_string(GRAY)


def add_bullet(doc: Document, text: str) -> None:
    paragraph = doc.add_paragraph(style="List Bullet")
    paragraph.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    paragraph.add_run(text)


def add_heading(doc: Document, text: str, level: int = 1):
    return doc.add_heading(text, level=level)


def add_caption(doc: Document, text: str) -> None:
    paragraph = doc.add_paragraph(style="Caption")
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    paragraph.paragraph_format.keep_with_next = False
    paragraph.paragraph_format.space_after = Pt(6)
    run = paragraph.add_run(text)
    run.font.name = "Arial"
    run.font.size = Pt(8)
    run.font.color.rgb = RGBColor.from_string(GRAY)


def get_font(size: int, bold=False):
    candidates = [
        r"C:\Windows\Fonts\arialbd.ttf" if bold else r"C:\Windows\Fonts\arial.ttf",
        r"C:\Windows\Fonts\calibrib.ttf" if bold else r"C:\Windows\Fonts\calibri.ttf",
    ]
    for candidate in candidates:
        if Path(candidate).exists():
            return ImageFont.truetype(candidate, size)
    return ImageFont.load_default()


def make_architecture_diagram(output: Path) -> None:
    width, height = 1600, 960
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    title_font = get_font(38, bold=True)
    box_title = get_font(25, bold=True)
    box_body = get_font(20)
    small = get_font(18)
    draw.text((70, 32), "Arquitectura de Taskboard: CI/CD y observabilidad", fill=f"#{NAVY}", font=title_font)

    def box(rect, title, body, fill, outline=TEAL):
        draw.rounded_rectangle(rect, radius=22, fill=f"#{fill}", outline=f"#{outline}", width=4)
        x1, y1, x2, y2 = rect
        draw.text((x1 + 20, y1 + 20), title, fill=f"#{NAVY}", font=box_title)
        draw.multiline_text((x1 + 20, y1 + 64), body, fill="#23313E", font=box_body, spacing=8)

    def arrow(start, end, label=None, label_pos=None, color=TEAL):
        draw.line([start, end], fill=f"#{color}", width=5)
        x1, y1 = start
        x2, y2 = end
        if abs(x2 - x1) >= abs(y2 - y1):
            direction = 1 if x2 >= x1 else -1
            tip = (x2, y2)
            p1 = (x2 - 15 * direction, y2 - 11)
            p2 = (x2 - 15 * direction, y2 + 11)
        else:
            direction = 1 if y2 >= y1 else -1
            tip = (x2, y2)
            p1 = (x2 - 11, y2 - 15 * direction)
            p2 = (x2 + 11, y2 - 15 * direction)
        draw.polygon([tip, p1, p2], fill=f"#{color}")
        if label and label_pos:
            draw.text(label_pos, label, fill=f"#{GRAY}", font=small)

    top_y1, top_y2 = 120, 310
    boxes = [
        (60, top_y1, 390, top_y2, "Repositorio", "Código y workflow\nGitHub: main"),
        (470, top_y1, 800, top_y2, "GitHub Actions", "Pytest + Playwright\nBuild solo tras aprobar"),
        (880, top_y1, 1190, top_y2, "GHCR", "Imagen Docker\nEtiqueta SHA inmutable"),
        (1270, top_y1, 1540, top_y2, "AWS EC2", "Ubuntu + Docker\nAcceso administrativo SSM"),
    ]
    for x1, y1, x2, y2, title, body in boxes:
        box((x1, y1, x2, y2), title, body, PALE)
    arrow((390, 215), (465, 215), "push", (400, 180))
    arrow((800, 215), (875, 215), "publicar", (800, 180))
    arrow((1190, 215), (1265, 215), "SSM pull", (1185, 180))

    box((95, 445, 390, 625), "Usuario", "Navegador\nHTTPS temporal de demo", "F2F7EA", GREEN)
    box((485, 445, 795, 625), "Taskboard", "FastAPI + interfaz web\nAutenticación y tareas", "EAF5F4")
    box((890, 445, 1190, 625), "Persistencia", "SQLite\nVolumen /var/lib/taskboard", "F2F7EA", GREEN)
    box((1280, 445, 1540, 625), "OpenObserve", "Logs, métricas,\ntrazas y eventos CI", "F5EFFA", "7654A5")
    arrow((390, 535), (480, 535), "Quick Tunnel", (380, 495))
    arrow((795, 535), (885, 535), "consultas", (800, 495))
    arrow((1190, 535), (1275, 535), "OTLP/HTTPS", (1180, 495))

    box((485, 720, 795, 880), "Instrumentación", "OpenTelemetry SDK\nFastAPI + SQLite", "EEF4FA")
    box((890, 720, 1190, 880), "Métricas EC2", "Hostmetrics Collector\nCPU, RAM, red, disco", "EEF4FA")
    arrow((640, 625), (640, 715), "telemetría app", (650, 655))
    arrow((1040, 625), (1040, 715), "scrape cada 60 s", (1050, 655))
    arrow((795, 800), (1275, 590), "OTLP", (1040, 735))
    arrow((1190, 800), (1275, 570), "OTLP", (1200, 690))
    draw.text((70, 915), "El Quick Tunnel de demostración es temporal y público; la instancia no requiere puertos entrantes para el despliegue por SSM.",
              fill=f"#{GRAY}", font=small)
    image.save(output, "PNG", optimize=True)


def redact_image(source: Path, destination: Path, regions) -> Path:
    with Image.open(source) as opened:
        image = ImageOps.exif_transpose(opened).convert("RGB")
    draw = ImageDraw.Draw(image)
    font = get_font(max(14, image.width // 90), bold=True)
    for left, top, right, bottom, label in regions:
        rect = (
            int(left * image.width),
            int(top * image.height),
            int(right * image.width),
            int(bottom * image.height),
        )
        draw.rectangle(rect, fill="#E5E9ED", outline=f"#{NAVY}", width=3)
        text_box = draw.textbbox((0, 0), label, font=font)
        text_w = text_box[2] - text_box[0]
        text_h = text_box[3] - text_box[1]
        x = rect[0] + max(8, (rect[2] - rect[0] - text_w) // 2)
        y = rect[1] + max(4, (rect[3] - rect[1] - text_h) // 2)
        draw.text((x, y), label, fill=f"#{NAVY}", font=font)
    image.save(destination, "PNG", optimize=True)
    return destination


def screenshot_stage(index: int) -> str:
    if index <= 3:
        return "especificación, criterios de aceptación y referencia de reporte"
    if index <= 20:
        return "preparación de repositorio, AWS e identidad OIDC"
    if index <= 39:
        return "configuración y validación inicial de OpenObserve"
    if index <= 62:
        return "configuración del workflow, variables y despliegue"
    if index <= 64:
        return "revisión documental de los requisitos"
    if index <= 69:
        return "contenedores, SSM y comprobación del servicio"
    return "aplicación, ingestión de telemetría y dashboards"


def build_report() -> tuple[Path, int]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ASSET_DIR.mkdir(parents=True, exist_ok=True)
    excluded = {CURRENT_RUBRIC_ID, CURRENT_COVER_ID}
    screenshots = [
        path
        for path in ATTACHMENTS.glob("*/*.png")
        if path.parent.name not in excluded
    ]
    screenshots.sort(key=lambda path: (path.stat().st_mtime, path.parent.name))
    if len(screenshots) < 89:
        raise RuntimeError(f"Se esperaban al menos 89 capturas del proyecto; encontré {len(screenshots)}.")
    # Keep the original reviewed/redacted evidence set; later attachments were not audited.
    screenshots = screenshots[:89]

    sensitive_regions = {
        "d164289e-3bf7-439a-851a-3422b7254ad5": [
            (0.38, 0.23, 0.99, 0.46, "Credenciales y endpoint ocultos")
        ],
        "2b3a86b9-ff93-455d-8ff8-f89a86990cb8": [
            (0.38, 0.26, 0.99, 0.67, "Credenciales y endpoint ocultos")
        ],
        "ca8cb834-dab3-4d93-95bf-95f1297a19b3": [
            (0.49, 0.25, 0.83, 0.32, "ARN oculto"),
            (0.89, 0.00, 0.99, 0.04, "ID oculto"),
        ],
        "0931fcee-d096-4c8b-941e-6f75421116ec": [
            (0.51, 0.60, 0.72, 0.70, "Valores AWS ocultos")
        ],
    }

    safe_images: list[Path] = []
    for index, screenshot in enumerate(screenshots, start=1):
        regions = sensitive_regions.get(screenshot.parent.name)
        if regions:
            safe_images.append(
                redact_image(
                    screenshot,
                    ASSET_DIR / f"evidence-{index:02d}-redacted.png",
                    regions,
                )
            )
        else:
            safe_images.append(screenshot)

    cover_source = ATTACHMENTS / CURRENT_COVER_ID / "Imagen pegada 2.png"
    if not cover_source.exists():
        cover_source = ATTACHMENTS / CURRENT_COVER_ID / "Imagen pegada.png"
    if not cover_source.exists():
        raise FileNotFoundError("No se encontró la portada institucional compartida.")
    with Image.open(cover_source) as cover:
        logo = ImageOps.exif_transpose(cover).convert("RGB").crop((305, 112, 440, 276))
        logo.save(ASSET_DIR / "uteq-logo.png", "PNG", optimize=True)
    logo_path = ASSET_DIR / "uteq-logo.png"
    diagram_path = ASSET_DIR / "arquitectura-taskboard.png"
    make_architecture_diagram(diagram_path)

    doc = Document()
    section = doc.sections[0]
    section.page_width = Inches(8.27)
    section.page_height = Inches(11.69)
    section.top_margin = Inches(0.72)
    section.bottom_margin = Inches(0.72)
    section.left_margin = Inches(0.82)
    section.right_margin = Inches(0.82)
    section.header_distance = Inches(0.32)
    section.footer_distance = Inches(0.35)
    section.different_first_page_header_footer = True

    styles = doc.styles
    normal = styles["Normal"]
    normal.font.name = "Arial"
    normal.font.size = Pt(10.5)
    normal.font.color.rgb = RGBColor.from_string("202832")
    normal.paragraph_format.space_after = Pt(7)
    normal.paragraph_format.line_spacing = 1.12
    normal.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    for name, size, color in [
        ("Heading 1", 16, NAVY),
        ("Heading 2", 12.5, TEAL),
        ("Heading 3", 11, NAVY),
    ]:
        style = styles[name]
        style.font.name = "Arial"
        style.font.size = Pt(size)
        style.font.bold = True
        style.font.color.rgb = RGBColor.from_string(color)
        style.paragraph_format.keep_with_next = True
        style.paragraph_format.space_before = Pt(12)
        style.paragraph_format.space_after = Pt(5)
    styles["Caption"].font.name = "Arial"
    styles["Caption"].font.size = Pt(8)
    styles["Caption"].font.italic = True
    styles["List Bullet"].font.name = "Arial"
    styles["List Bullet"].font.size = Pt(10.5)

    header = section.header.paragraphs[0]
    header.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    run = header.add_run("UTEQ  |  TASKBOARD  |  PROYECTO PARCIAL 2")
    run.font.name = "Arial"
    run.font.size = Pt(8)
    run.font.color.rgb = RGBColor.from_string(GRAY)
    footer = section.footer.paragraphs[0]
    footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
    footer.add_run("Reporte de proyecto  ·  Página ")
    add_field(footer, "PAGE")

    doc.core_properties.title = (
        "Taskboard: CI/CD, pruebas automatizadas y observabilidad en AWS"
    )
    doc.core_properties.subject = "Reporte final del Proyecto Parcial 2"
    doc.core_properties.author = "Luis Antonio Gómez Olascoaga"
    doc.core_properties.keywords = "Taskboard, Playwright, Pytest, CI/CD, AWS, OpenTelemetry"

    # Portada institucional recreada a partir del formato proporcionado.
    cover = doc.add_paragraph()
    cover.alignment = WD_ALIGN_PARAGRAPH.CENTER
    cover.paragraph_format.space_before = Pt(10)
    cover.add_run().add_picture(str(logo_path), width=Inches(1.45), height=Inches(1.75))
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(4)
    r = p.add_run("UNIVERSIDAD TECNOLÓGICA DE QUERÉTARO")
    r.bold = True
    r.font.name = "Georgia"
    r.font.size = Pt(19)
    r.font.color.rgb = RGBColor.from_string(NAVY)
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run("Gestión en el Desarrollo de Software")
    r.font.name = "Georgia"
    r.font.size = Pt(14)
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(14)
    p.paragraph_format.space_after = Pt(5)
    r = p.add_run(
        "PROYECTO PARCIAL 2\n"
        "Arquitectura de Entrega Continua (CI/CD),\n"
        "Pruebas Automatizadas y Observabilidad"
    )
    r.bold = True
    r.font.name = "Georgia"
    r.font.size = Pt(15)
    r.font.color.rgb = RGBColor.from_string(TEAL)
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run("Taskboard: gestión segura de tareas desplegada en AWS")
    r.font.name = "Georgia"
    r.font.size = Pt(13)
    r.italic = True

    doc.add_paragraph()
    cover_table = doc.add_table(rows=0, cols=2)
    cover_table.autofit = False
    cover_table.columns[0].width = Inches(1.55)
    cover_table.columns[1].width = Inches(4.95)
    cover_fields = [
        ("Matrícula", "2023371058"),
        ("Carrera", "Ingeniería en Desarrollo y Gestión de Software"),
        ("Materia", "Gestión en el Desarrollo de Software"),
        ("Alumno", "Luis Antonio Gómez Olascoaga"),
        ("Profesor", "M.C.C. Emmanuel Martínez Hernández"),
        ("Grupo", "IDGS14"),
        ("Título de la actividad", "Taskboard: CI/CD, pruebas automatizadas y observabilidad"),
        ("Repositorio", "github.com/Luisilloelpillo55/taskboard-ci-cd"),
        ("Tecnologías", "Python, FastAPI, SQLite, Pytest, Playwright, Docker, AWS, OpenTelemetry y OpenObserve"),
        ("Fecha", "26 de noviembre de 2026"),
    ]
    for label, value in cover_fields:
        cells = cover_table.add_row().cells
        set_cell_text(cells[0], label, bold=True, color=NAVY, size=9)
        set_cell_text(cells[1], value, size=9)
        set_cell_shading(cells[0], PALE)
    doc.add_paragraph()
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run("Repositorio del proyecto: ")
    r.bold = True
    add_hyperlink(p, "github.com/Luisilloelpillo55/taskboard-ci-cd",
                  "https://github.com/Luisilloelpillo55/taskboard-ci-cd")
    doc.add_page_break()

    index_title = doc.add_paragraph()
    index_title.paragraph_format.space_before = Pt(5)
    index_title.paragraph_format.space_after = Pt(10)
    title_run = index_title.add_run("Índice")
    title_run.bold = True
    title_run.font.name = "Arial"
    title_run.font.size = Pt(19)
    title_run.font.color.rgb = RGBColor.from_string(NAVY)
    toc = doc.add_paragraph()
    toc.paragraph_format.space_after = Pt(10)
    add_field(toc, 'TOC \\o "1-3" \\h \\z \\u', "El índice se actualizará al exportar el documento.")
    p = doc.add_paragraph(
        "El índice es automático y utiliza los títulos y subtítulos del documento."
    )
    p.alignment = WD_ALIGN_PARAGRAPH.LEFT
    p.runs[0].italic = True
    p.runs[0].font.size = Pt(8)
    p.runs[0].font.color.rgb = RGBColor.from_string(GRAY)
    doc.add_page_break()

    add_heading(doc, "1. Introducción", 1)
    introduction = [
        "La entrega continua integra cambios de software de manera frecuente y controlada, con validaciones automáticas que reducen errores entre el desarrollo y la operación. El Proyecto Parcial 2 propone implementar un flujo CI/CD condicionado por pruebas, desplegar una aplicación en AWS EC2 y supervisar tanto el servicio como la infraestructura desde una plataforma de observabilidad.",
        "Para cumplir ese propósito se desarrolló Taskboard, una aplicación web en español para que las personas registren una cuenta y administren sus propias tareas. La solución combina una interfaz web estática con una API FastAPI y una base SQLite persistente; la autenticación y la separación de datos se aplican en el servidor, no solamente en la presentación visual [1].",
        "La confiabilidad se comprueba en dos niveles. Pytest verifica rutas, validaciones, persistencia, límites y casos de error del backend; Playwright ejecuta escenarios de extremo a extremo en navegador Chromium, incluyendo registro, inicio de sesión, gestión de tareas y de cuenta, privacidad entre usuarios, diseño móvil y comunicación de errores [3], [4].",
        "El workflow de GitHub Actions ejecuta las suites antes de construir la imagen. Solo tras superar las pruebas se publica el contenedor en GitHub Container Registry y, cuando se cumplen las condiciones de configuración, la imagen identificada por el SHA del commit se despliega en EC2 mediante credenciales federadas OIDC y AWS Systems Manager [5], [6], [9].",
        "La telemetría de la aplicación utiliza OpenTelemetry para enviar registros, métricas y trazas por OTLP. Un Collector adicional obtiene métricas del host con intervalos de un minuto. OpenObserve recibe las señales de la aplicación, la instancia y los eventos JSON de CI/CD, y permite consultarlas y construir dashboards [10], [11], [12].",
        "La seguridad se considera parte del diseño: las contraseñas se almacenan mediante hashing resistente, las sesiones se representan por tokens aleatorios cuyo hash queda en SQLite, las cookies se protegen con atributos apropiados y el contenedor corre sin privilegios. El repositorio no almacena claves de AWS ni el encabezado secreto de OpenObserve [2], [6], [7].",
        "Este documento presenta el objetivo y la arquitectura, los resultados comprobados de las pruebas, el despliegue y la ingestión de telemetría, así como una matriz de cumplimiento basada en los requisitos entregados. También diferencia las capacidades configuradas de las que aún requieren una demostración específica.",
        "Las evidencias visuales recibidas durante el trabajo se incluyen en orden cronológico como anexos. Se conservaron las capturas del proyecto y se ocultaron en copias del documento los fragmentos de credenciales e identificadores sensibles; las credenciales utilizables no se adjuntan al informe por seguridad.",
    ]
    for text in introduction:
        add_body(doc, text)

    add_heading(doc, "2. Objetivos y alcance", 1)
    add_heading(doc, "2.1 Objetivo general", 2)
    add_body(
        doc,
        "Implementar un flujo automatizado de integración y despliegue continuo mediante GitHub Actions hacia una instancia AWS EC2, condicionado a la aprobación de pruebas automatizadas de frontend y backend, e integrar telemetría centralizada para supervisar la aplicación y los recursos del servidor en OpenObserve.",
    )
    add_heading(doc, "2.2 Objetivos específicos", 2)
    for text in [
        "Construir una aplicación web de tareas con autenticación, sesiones seguras y aislamiento de la información por cuenta.",
        "Automatizar pruebas de API/backend con Pytest y pruebas de navegador/API con Playwright, conservando reportes y medición de cobertura.",
        "Crear un pipeline que ejecute pruebas, publique una imagen Docker inmutable y despliegue por OIDC/SSM únicamente tras superar las validaciones.",
        "Emitir eventos JSON de pruebas y despliegues en OpenObserve con identificación del commit, rama, actor y ejecución.",
        "Instrumentar la aplicación y el host para observar logs, métricas, trazas, CPU, memoria, red, disco y uso de filesystem.",
        "Documentar las condiciones no verificables en el entorno, sin presentar mediciones simuladas ni revelar credenciales.",
    ]:
        add_bullet(doc, text)

    add_heading(doc, "2.3 Alcance funcional", 2)
    add_body(
        doc,
        "El servicio permite registrar e iniciar sesión, cerrar sesión, consultar la cuenta actual, actualizar el correo o la contraseña, eliminar la propia cuenta y realizar operaciones CRUD sobre tareas. Las tareas incluyen título, descripción, estado y fecha de creación; las consultas y modificaciones se limitan al usuario autenticado. No existe un rol de administrador para consultar cuentas ajenas."
    )
    add_body(
        doc,
        "La instalación de producción utiliza Docker Compose, un volumen persistente para SQLite, un usuario no root, un sistema de archivos de contenedor de solo lectura y un puerto enlazado a localhost. La administración remota se realiza con SSM; el grupo de seguridad no requiere exponer la aplicación por HTTP."
    )

    add_heading(doc, "3. Arquitectura e implementación", 1)
    add_heading(doc, "3.1 Arquitectura lógica", 2)
    add_body(
        doc,
        "La Figura 1 resume la relación entre el repositorio, el pipeline, el registro de contenedores, la instancia EC2, la aplicación, la persistencia y OpenObserve. Las líneas de telemetría salen hacia el servicio de observabilidad; la administración de la instancia se ejecuta mediante SSM y no requiere una conexión SSH entrante."
    )
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.add_run().add_picture(str(diagram_path), width=Inches(6.45))
    add_caption(doc, "Figura 1. Arquitectura lógica de Taskboard, su pipeline y la observabilidad.")
    add_heading(doc, "3.2 Aplicación y persistencia", 2)
    add_body(
        doc,
        "FastAPI sirve los recursos estáticos y expone rutas para salud, autenticación y tareas. Pydantic valida los datos; SQLite mantiene las tablas de usuarios, sesiones y tareas. Las consultas de tareas se filtran por el identificador de cuenta. Las actualizaciones de contraseña requieren verificar la contraseña vigente y revocan las otras sesiones; el borrado de cuenta elimina sus tareas y sesiones relacionadas."
    )
    add_body(
        doc,
        "La contraseña se valida con longitud mínima y se procesa mediante el algoritmo recomendado por la biblioteca de hashing configurada; la sesión se representa con un valor aleatorio en una cookie HttpOnly y SameSite=Lax, y la base almacena su digest SHA-256, no el token original. El parámetro COOKIE_SECURE se activa en el despliegue HTTPS. Estas medidas siguen la recomendación de no persistir contraseñas en texto claro y utilizar hashing lento y salado [2]."
    )
    add_heading(doc, "3.3 Pruebas automatizadas", 2)
    add_body(
        doc,
        "La suite Pytest cubre la API, reglas de negocio, persistencia, migraciones y telemetría mediante pruebas aisladas. La suite Playwright prueba el comportamiento de navegador, autenticación y operaciones de cuenta/tareas, además de casos de accesibilidad básica, responsive y errores de red/API. La configuración E2E inicia una instancia local en el puerto 8001 con una base de pruebas separada de la base de desarrollo [3], [4]."
    )
    add_body(
        doc,
        "El reporte HTML de Playwright y los reportes de Pytest/cobertura son artefactos del workflow con retención configurada de siete días. La cobertura de líneas observada en la ejecución local de este informe es 99%; no debe interpretarse como cobertura de ramas ni de la interfaz."
    )
    add_heading(doc, "3.4 Pipeline CI/CD y despliegue", 2)
    add_body(
        doc,
        "El workflow se ejecuta en cambios a main y pull requests, y también admite ejecución manual. El job de pruebas instala Python 3.12, Node.js 22 y Chromium, ejecuta Pytest, Playwright y una prueba aislada de carga de 1.000 solicitudes; conserva los reportes JUnit, HTML y de cobertura. En main, el job posterior construye y publica en GHCR etiquetas latest y sha-<commit>; el job de despliegue usa OIDC para obtener credenciales temporales de AWS, ejecuta el despliegue por SSM y verifica el servicio, el Collector de host y la ruta /api/health."
    )
    add_body(
        doc,
        "La imagen desplegada se identifica por el SHA probado, evitando depender de una etiqueta mutable. La configuración de Docker Compose limita el puerto a 127.0.0.1:8000, conserva SQLite en el volumen de datos y reduce privilegios del contenedor [7], [8], [9]. El uso de OIDC evita guardar claves AWS de larga duración en los secretos del repositorio [6]."
    )
    add_heading(doc, "3.5 Observabilidad", 2)
    add_body(
        doc,
        "El SDK de OpenTelemetry instrumenta FastAPI y SQLite y configura exportadores OTLP para trazas, métricas y logs. El hostmetrics Collector envía señales de CPU, disco, filesystem, carga, memoria, red y paging cada 60 segundos, con el recurso service.name=taskboard-ec2-host. Los nombres observados en el selector de OpenObserve emplean guiones bajos en las métricas, por ejemplo system_memory_utilization [10], [11]."
    )
    add_body(
        doc,
        "El dashboard creado en OpenObserve incluye solicitudes HTTP por segundo y utilización de CPU; el usuario confirmó también los paneles de utilización de RAM, tráfico de red, E/S de disco y espacio usado por filesystem. Los contadores de red y disco se convierten a bytes por segundo mediante rate(), mientras que la utilización de RAM es una gauge de fracción y el uso de filesystem una lectura en bytes. No se promedia system_memory_usage como si fuera memoria instantánea. Aunque la instrumentación HTTP aporta dimensiones de ruta y estado, no se verificaron paneles dedicados de latencia y tasa de errores por endpoint."
    )
    add_body(
        doc,
        "Los eventos de CI y despliegue se envían como registros JSON a ci_events cuando están configuradas las variables y el secreto de OpenObserve. El workflow reporta resultados individuales de Pytest y Playwright, clasificación de componente, causa de fallo y métricas de la prueba de carga; el backend también emite errores estructurados con ruta, estado y causa segura. Los eventos históricos de pruebas/despliegue fueron recibidos en OpenObserve; la ingestión de los nuevos tipos queda pendiente de confirmación en una ejecución posterior del workflow. La autenticación queda en el gestor de secretos y no se reproduce en el reporte."
    )

    add_heading(doc, "4. Resultados y análisis", 1)
    add_heading(doc, "4.1 Resultados de pruebas", 2)
    results_table = doc.add_table(rows=1, cols=3)
    results_table.style = "Table Grid"
    headers = ["Suite", "Resultado", "Alcance de la evidencia"]
    for cell, text in zip(results_table.rows[0].cells, headers):
        set_cell_text(cell, text, bold=True, color="FFFFFF", size=9)
        set_cell_shading(cell, NAVY)
    result_rows = [
        ("Pytest", "86 aprobadas; 0 fallidas", "API, reglas de negocio, base de datos, migraciones y telemetría."),
        ("Playwright", "27 aprobadas; 0 fallidas", "Flujos de navegador y API E2E; autenticación, CRUD, privacidad, responsive y errores."),
        ("Prueba API concurrente", "1.000/1.000; p95 276 ms", "20 clientes × 50; 165 solicitudes/s, máximo 2,9 s, 0 fallos HTTP. Entorno local aislado."),
        ("Cobertura app/", "99% de líneas", "386 instrucciones; 4 líneas sin cubrir en app/auth.py. No equivale a cobertura de ramas."),
        ("GitHub Actions #11", "Concluido con éxito", "Commit 118eb6e; pruebas, publicación, despliegue por SSM y health check."),
    ]
    for row in result_rows:
        cells = results_table.add_row().cells
        for cell, text in zip(cells, row):
            set_cell_text(cell, text, size=8.5)
    add_body(
        doc,
        "La ejecución local usada para elaborar este reporte terminó con 86 pruebas Pytest aprobadas y 27 pruebas Playwright aprobadas. Pytest mostró advertencias no bloqueantes de deprecación de Starlette; no hubo fallas. La prueba de carga aislada completó 1.000 solicitudes con 20 clientes concurrentes, sin fallos HTTP ni errores 5xx, con una tasa de 165,389 solicitudes/s. El p95 fue de 276,418 ms (umbral: 2.000 ms) y la latencia máxima observada fue de 2,912 s. Este resultado corresponde al entorno local de desarrollo y no demuestra el límite de capacidad de la instancia EC2. El pipeline CI/CD histórico número 11, asociado al commit 118eb6e, concluyó correctamente el 26 de noviembre de 2026."
    )
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.LEFT
    p.add_run("Ejecución CI/CD: ")
    add_hyperlink(p, "GitHub Actions run #11",
                  "https://github.com/Luisilloelpillo55/taskboard-ci-cd/actions/runs/45898952334")
    add_heading(doc, "4.2 Matriz de cumplimiento de requisitos", 2)
    matrix = doc.add_table(rows=1, cols=3)
    matrix.style = "Table Grid"
    for cell, text in zip(matrix.rows[0].cells, ["Requisito", "Estado", "Evidencia / observación"]):
        set_cell_text(cell, text, bold=True, color="FFFFFF", size=8.5)
        set_cell_shading(cell, NAVY)
    requirements = [
        ("RF-01 Pruebas integrales", "Parcial / demostrado",
         "86 Pytest + 27 Playwright pasan. No se incorporó una suite independiente de Jest; la UI se valida con Playwright."),
        ("RF-02 CI/CD condicionado", "Configurado y éxito verificado",
         "La publicación depende de tests verdes; el despliegue usa la imagen por SHA y se verificó en el run #11."),
        ("RF-03 Eventos CI/CD", "Configurado; nueva ingestión pendiente",
         "Se agregaron eventos individuales de backend/frontend, causa de fallo y carga API. La recepción de estos nuevos tipos debe confirmarse en el siguiente run; un fallo intencional de pipeline no se probó."),
        ("RF-04 Telemetría de aplicación", "Parcial / instrumentado",
         "OpenTelemetry exporta logs, métricas y trazas de FastAPI/SQLite. Los nuevos errores incluyen componente y causa; su ingestión tras el siguiente despliegue y paneles dedicados por endpoint aún deben verificarse."),
        ("RF-05 Métricas de infraestructura", "Parcial / visualizado",
         "CPU, RAM, red, disco y filesystem se configuraron y graficaron. EC2 no ofrece una temperatura utilizable."),
        ("RF-06 Dashboard y alertas", "Parcial",
         "El dashboard está creado; no se ha confirmado la configuración y prueba de reglas de alerta operativa."),
        ("Criterio: commit intencionalmente defectuoso", "No verificado",
         "El workflow contiene un gate de pruebas, pero no se ejecutó una prueba negativa intencional que pruebe el bloqueo y evento de fallo."),
    ]
    for row in requirements:
        cells = matrix.add_row().cells
        for cell, text in zip(cells, row):
            set_cell_text(cell, text, size=8)
        set_cell_shading(cells[1], "FCECC9" if "Parcial" in row[1] or "No verificado" in row[1] else "E3F2E5")
    add_body(
        doc,
        "La matriz diferencia entre código configurado, evidencia efectivamente observada y validaciones pendientes. En particular, el éxito de un despliegue no demuestra por sí solo el comportamiento ante una prueba fallida; tampoco se presenta como completado un sistema de alertas que aún no ha sido creado y comprobado."
    )

    add_heading(doc, "4.3 Evidencia del dashboard y recursos", 2)
    add_body(
        doc,
        "La configuración de hostmetrics permite supervisar CPU, memoria, red, disco y filesystem. La métrica system.memory.utilization se habilitó explícitamente porque es una gauge adecuada para visualizar la fracción de memoria utilizada por estado; system.memory.usage representa componentes de uso con semántica distinta. El panel de RAM se guardó tras refrescar el selector de OpenObserve. Las Figuras A-70 a A-89 documentan la revisión de señales, consultas y construcción del dashboard."
    )
    add_body(
        doc,
        "Para red y disco se usó la tasa por segundo de los contadores monotónicos y se agruparon series por dirección/dispositivo. Para filesystem se consultó el estado usado en bytes, sin aplicar rate(). El volumen EBS configurado es almacenamiento y no aumenta la memoria RAM de la instancia."
    )
    add_heading(doc, "4.4 Limitaciones operativas y seguridad", 2)
    add_body(
        doc,
        "La instancia EC2 no expone un sensor térmico válido para la temperatura del procesador. La única lectura revisada fue -273.15 °C, un valor centinela no interpretable como temperatura real; por ello se excluye del dashboard y de las conclusiones de rendimiento."
    )
    add_body(
        doc,
        "La aplicación se validó en EC2 mediante SSM y health check local. El acceso de demostración utiliza un Quick Tunnel de Cloudflare temporal; la URL vigente se incluye en la tabla final y puede cambiar o dejar de estar disponible al reiniciar o detener el túnel. Cualquier persona que conozca el enlace puede visitar la aplicación, por lo que no debe tratarse como un sitio privado ni como una dirección permanente."
    )
    add_body(
        doc,
        "La especificación solicita adjuntar credenciales del sistema, incluido OpenObserve; por seguridad, este informe no incluye contraseñas, tokens, encabezados de autorización, claves ni valores de secretos. Las capturas que mostraban partes de credenciales, ARN o identificadores de instancia se integran como copias con esas regiones ocultas. Si el docente necesita acceso, debe compartirse mediante un canal seguro y con permisos temporales."
    )
    add_body(
        doc,
        "Para completar todas las pruebas de aceptación deben agregarse y documentarse dos evidencias: (1) una ejecución controlada con fallo de prueba que deje el deploy bloqueado y registre el evento de fallo en OpenObserve, y (2) reglas operativas de alerta con una prueba de disparo/recuperación. Una alerta de temperatura no debe crearse con el valor inválido del sensor."
    )

    add_heading(doc, "5. Conclusiones", 1)
    conclusions = [
        "Taskboard integra una aplicación funcional de gestión de tareas con cuentas, sesiones y datos privados por usuario. El servidor aplica las restricciones de acceso, valida entradas y conserva la información en SQLite, mientras la interfaz ofrece los flujos principales de uso.",
        "Las suites de pruebas proporcionan cobertura complementaria: Pytest comprueba el comportamiento del backend y Playwright ejercita flujos de navegador y API. En la ejecución reportada aprobaron 86 pruebas Pytest y 27 pruebas Playwright; la cobertura de líneas de app/ fue 99%.",
        "La prueba acotada de concurrencia completó 1.000 solicitudes locales (20 clientes × 50), con 0 fallos HTTP, p95 de 276,418 ms y máximo de 2,912 s. El resultado valida la configuración probada, no garantiza el rendimiento bajo cargas distintas ni sustituye una prueba autorizada contra la instancia desplegada.",
        "El pipeline CI/CD conecta validación, construcción de contenedor, publicación en GHCR y despliegue remoto. El uso de OIDC y Systems Manager evita depender de claves AWS permanentes en GitHub y permite administrar la instancia sin abrir una conexión SSH entrante.",
        "La imagen identificada por commit facilita asociar el código probado con el artefacto desplegado. El run #11 terminó con éxito y la aplicación respondió al health check; ese resultado constituye evidencia del camino positivo de despliegue, no una prueba del camino de rechazo.",
        "OpenTelemetry y OpenObserve centralizan telemetría de aplicación y host. Los logs, las trazas y las métricas de HTTP/infraestructura permiten correlacionar el comportamiento del servicio con el estado del servidor y los eventos del pipeline.",
        "La visualización de RAM se corrigió al seleccionar una gauge de utilización, en vez de interpretar una suma de uso como memoria instantánea. De forma similar, los contadores de red y disco requieren una tasa temporal y las mediciones de filesystem deben conservar su unidad de bytes.",
        "La transparencia de los resultados es importante: no se reporta una temperatura que EC2 no proporciona de forma fiable ni se presenta el Quick Tunnel temporal como una URL permanente. Tampoco se distribuyen credenciales dentro del documento.",
        "El proyecto alcanza resultados funcionales importantes y cuenta con evidencia amplia, pero el cierre frente a la rúbrica todavía requiere demostrar el bloqueo ante una prueba fallida, crear y probar alertas operativas y confirmar si se solicita Jest además de Pytest y Playwright. Resolver esos puntos permitirá presentar una validación más completa sin sacrificar seguridad ni precisión.",
    ]
    for text in conclusions:
        add_body(doc, text)

    add_heading(doc, "6. Referencias", 1)
    references = [
        ("FastAPI. (s. f.). Documentación oficial de FastAPI.",
         "https://fastapi.tiangolo.com/"),
        ("OWASP Foundation. (s. f.). Password Storage Cheat Sheet.",
         "https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html"),
        ("Microsoft. (s. f.). Playwright Test: introducción y reportes HTML.",
         "https://playwright.dev/docs/intro"),
        ("pytest. (s. f.). Documentación oficial de pytest.",
         "https://docs.pytest.org/en/stable/"),
        ("GitHub. (s. f.). GitHub Actions documentation.",
         "https://docs.github.com/en/actions"),
        ("GitHub. (s. f.). Configuración de OpenID Connect en Amazon Web Services.",
         "https://docs.github.com/en/actions/how-tos/secure-your-work/security-harden-deployments/oidc-in-aws"),
        ("Docker. (s. f.). Docker Compose documentation.",
         "https://docs.docker.com/compose/"),
        ("Amazon Web Services. (s. f.). What is Amazon EC2?",
         "https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/concepts.html"),
        ("Amazon Web Services. (s. f.). AWS Systems Manager Run Command.",
         "https://docs.aws.amazon.com/systems-manager/latest/userguide/run-command.html"),
        ("OpenTelemetry. (s. f.). OpenTelemetry Python documentation.",
         "https://opentelemetry.io/docs/languages/python/"),
        ("OpenTelemetry Collector Contrib. (s. f.). Host Metrics receiver.",
         "https://github.com/open-telemetry/opentelemetry-collector-contrib/tree/main/receiver/hostmetricsreceiver"),
        ("OpenObserve. (s. f.). OpenObserve documentation.",
         "https://openobserve.ai/docs/"),
    ]
    for index, (citation, url) in enumerate(references, start=1):
        p = doc.add_paragraph(style="Normal")
        p.alignment = WD_ALIGN_PARAGRAPH.LEFT
        p.paragraph_format.left_indent = Inches(0.28)
        p.paragraph_format.first_line_indent = Inches(-0.28)
        p.paragraph_format.space_after = Pt(5)
        p.add_run(f"[{index}] {citation} ")
        add_hyperlink(p, url, url)
        p.add_run(" Consultado el 26 de noviembre de 2026.")

    add_heading(doc, "7. Anexos: evidencias visuales", 1)
    add_body(
        doc,
        "Las 89 capturas siguientes se presentan en el orden cronológico disponible de la sesión y se numeran como Figuras A-01 a A-89. El texto principal las referencia por rangos. Se excluyeron las dos imágenes utilizadas únicamente como rúbrica y plantilla de portada; estas sirvieron como guía del formato y los criterios. En las copias del informe se ocultaron regiones que contenían credenciales o identificadores operativos."
    )
    for index, image_path in enumerate(safe_images, start=1):
        if index > 1 and (index - 1) % 2 == 0:
            doc.add_page_break()
        paragraph = doc.add_paragraph()
        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        paragraph.paragraph_format.space_before = Pt(4)
        paragraph.paragraph_format.space_after = Pt(1)
        with Image.open(image_path) as opened:
            width_px, height_px = opened.size
        max_width, max_height = 6.35, 3.25
        scale = min(max_width / width_px, max_height / height_px)
        paragraph.add_run().add_picture(
            str(image_path),
            width=Inches(width_px * scale),
            height=Inches(height_px * scale),
        )
        add_caption(
            doc,
            f"Figura A-{index:02d}. Evidencia de {screenshot_stage(index)} "
            f"compartida durante el desarrollo del proyecto.",
        )

    add_heading(doc, "8. Acceso a la demostración y credenciales", 1)
    access_table = doc.add_table(rows=1, cols=2)
    access_table.style = "Table Grid"
    for cell, text in zip(access_table.rows[0].cells, ["Dato", "Acceso / nota"]):
        set_cell_text(cell, text, bold=True, color="FFFFFF", size=9)
        set_cell_shading(cell, NAVY)
    access_rows = [
        ("Sitio de demostración", "https://nhs-printer-certificates-resume.trycloudflare.com/"),
        ("Disponibilidad", "Quick Tunnel temporal y público; el enlace puede cambiar o dejar de funcionar."),
        ("Usuario de OpenObserve", "No incluido; utilizar la cuenta asignada por el propietario del espacio."),
        ("Contraseña y credenciales de OpenObserve", "No incluidas por seguridad. Gestionarlas por un canal privado y mantenerlas fuera del repositorio y de este informe."),
    ]
    for label, value in access_rows:
        cells = access_table.add_row().cells
        set_cell_text(cells[0], label, bold=True, size=8.5)
        if label == "Sitio de demostración":
            cells[1].text = ""
            cells[1].vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
            add_hyperlink(cells[1].paragraphs[0], value, value)
        else:
            set_cell_text(cells[1], value, size=8.5)

    doc.save(DOCX_PATH)
    return DOCX_PATH, len(screenshots)


if __name__ == "__main__":
    path, count = build_report()
    print(f"DOCX={path}")
    print(f"SCREENSHOTS={count}")

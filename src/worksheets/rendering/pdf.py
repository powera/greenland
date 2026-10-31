"""Paginated student sheets and separate answer keys using ReportLab."""

from io import BytesIO
import os
from pathlib import Path
from xml.sax.saxutils import escape

from PIL import Image as PillowImage, ImageDraw, ImageFont
import reportlab
from reportlab.pdfgen.canvas import Canvas
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate,
    Flowable,
    Image,
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from worksheets.models import Worksheet


def _emoji_image(glyph: str) -> Image:
    """Rasterize emoji locally, including joined sequences; never fetch remote images."""
    font_path = os.environ.get(
        "WORKSHEETS_EMOJI_FONT", "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf"
    )
    if not Path(font_path).is_file():
        raise ValueError(
            "Emoji PDFs need Noto Color Emoji; set WORKSHEETS_EMOJI_FONT to its font file."
        )
    try:
        font = ImageFont.truetype(font_path, 109)
        bounds = font.getbbox(glyph)
        canvas = PillowImage.new("RGBA", (bounds[2] - bounds[0] + 8, bounds[3] - bounds[1] + 8))
        ImageDraw.Draw(canvas).text(
            (4 - bounds[0], 4 - bounds[1]), glyph, font=font, embedded_color=True
        )
        buffer = BytesIO()
        canvas.save(buffer, format="PNG")
        buffer.seek(0)
        return Image(buffer, width=32 * canvas.width / canvas.height, height=32, hAlign="LEFT")
    except OSError as error:
        raise ValueError("Could not load the emoji font for PDF rendering.") from error


def render_pdf(worksheet: Worksheet, page_size: str = "letter", answers: bool = False) -> bytes:
    """Render escaped text, wrapping long definitions and keeping question blocks intact."""
    if page_size not in {"letter", "a4"}:
        raise ValueError("Unknown paper size.")
    if "WorksheetText" not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(
            TTFont("WorksheetText", str(Path(reportlab.__file__).parent / "fonts" / "Vera.ttf"))
        )
    styles = getSampleStyleSheet()
    for style_name in ("Normal", "Title", "Heading2"):
        styles[style_name].fontName = "WorksheetText"
    styles["Normal"].fontSize = 12
    styles["Normal"].leading = 18
    stream = BytesIO()
    document = SimpleDocTemplate(
        stream,
        pagesize=letter if page_size == "letter" else A4,
        rightMargin=45,
        leftMargin=45,
        topMargin=45,
        bottomMargin=45,
        title=worksheet.title + (" — Answer key" if answers else ""),
    )
    story: list[Flowable] = [
        Paragraph(escape(worksheet.title + (" — Answer key" if answers else "")), styles["Title"])
    ]
    if not answers:
        story.extend(
            [
                Paragraph("Name: ________________________  Date: ______________", styles["Normal"]),
                Spacer(1, 16),
                Paragraph(escape(worksheet.instructions), styles["Normal"]),
                Spacer(1, 16),
            ]
        )
    if worksheet.choices and not answers:
        rows = []
        for index, (question, clue) in enumerate(zip(worksheet.questions, worksheet.choices)):
            clue_content: list[Flowable] = [Paragraph(f"{chr(65 + index)}.", styles["Normal"])]
            clue_content.append(
                _emoji_image(clue)
                if worksheet.emoji_clues
                else Paragraph(escape(clue), styles["Normal"])
            )
            rows.append(
                [
                    Paragraph(
                        escape(f"{index + 1}. {question.prompt}    ______"), styles["Normal"]
                    ),
                    clue_content,
                ]
            )
        table = Table(rows, colWidths=[document.width * 0.45, document.width * 0.55])
        table.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 16),
                ]
            )
        )
        story.append(table)
    for number, question in enumerate(worksheet.questions, 1):
        if worksheet.choices and not answers:
            continue
        if answers:
            text = f"{number}. {question.answer}"
            story.append(Paragraph(escape(text), styles["Normal"]))
            continue
        block: list[Flowable] = [
            Paragraph(
                escape(f"{number}. {question.prompt}    __________________"), styles["Normal"]
            )
        ]
        if question.clue:
            block.append(
                _emoji_image(question.clue)
                if worksheet.emoji_clues
                else Paragraph(escape(question.clue), styles["Normal"])
            )
        block.append(Spacer(1, 18))
        story.append(KeepTogether(block))

    def footer(canvas: Canvas, doc: BaseDocTemplate) -> None:
        canvas.setFillColor(colors.grey)
        canvas.setFont("Helvetica", 9)
        canvas.drawRightString(document.pagesize[0] - 45, 25, f"Page {doc.page}")

    document.build(story, onFirstPage=footer, onLaterPages=footer)
    return stream.getvalue()

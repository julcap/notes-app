import re
import unicodedata
from html import escape
from io import BytesIO
from pathlib import Path

from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics, ttfonts
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

from .models import Note


ASSETS = Path(__file__).parent / 'assets'
FONT_FILES = (
    ('DejaVuSans', 'DejaVuSans.ttf'),
    ('NotoSansJP', 'NotoSansJP-VF.ttf'),
    ('NotoEmoji', 'NotoEmoji-VF.ttf'),
)
font_character_maps = []
for font_name, filename in FONT_FILES:
    font = TTFont(font_name, ASSETS / filename)
    pdfmetrics.registerFont(font)
    font_character_maps.append((font_name, font.face.charToGlyph))
FONT_CHARACTER_MAPS = tuple(font_character_maps)


def _make_to_unicode_cmap(font_name, subset):
    mappings = [
        f'<{index:02X}> <{chr(codepoint).encode("utf-16-be").hex().upper()}>'
        for index, codepoint in enumerate(subset)
    ]
    return '\n'.join([
        '/CIDInit /ProcSet findresource begin',
        '12 dict begin',
        'begincmap',
        '/CIDSystemInfo',
        f'<< /Registry ({font_name})',
        f'/Ordering ({font_name})',
        '/Supplement 0',
        '>> def',
        f'/CMapName /{font_name} def',
        '/CMapType 2 def',
        '1 begincodespacerange',
        f'<00> <{len(subset) - 1:02X}>',
        'endcodespacerange',
        f'{len(subset)} beginbfchar',
        *mappings,
        'endbfchar',
        'endcmap',
        'CMapName currentdict /CMap defineresource pop',
        'end',
        'end',
    ])


# ReportLab 5 emits invalid five-digit ToUnicode values for astral characters.
ttfonts.makeToUnicodeCMap = _make_to_unicode_cmap


def export_filename(title: str, extension: str) -> str:
    ascii_title = unicodedata.normalize('NFKD', title).encode('ascii', 'ignore').decode()
    safe_title = re.sub(r'[^A-Za-z0-9._-]+', '-', ascii_title).strip(' .-_')
    safe_title = safe_title[:100].rstrip(' .-_') or 'meeting-note'
    return f'{safe_title}.{extension}'


def markdown_export(note: Note) -> str:
    action_items = '\n'.join(
        f"- [{'x' if item.done else ' '}] {item.text} — "
        f"Owner: {item.owner_name or 'Unassigned'} — Due: {item.due_date or 'No due date'}"
        for item in note.action_items
    ) or 'No action items.'
    return (
        f'# {note.title}\n\n'
        f'**Date:** {note.meeting_date}\n\n'
        f"**Attendees:** {note.attendees or 'None'}\n\n"
        f'## Notes\n\n{note.content or "No notes."}\n\n'
        f'## Action items\n\n{action_items}\n'
    )


def pdf_export(note: Note) -> bytes:
    output = BytesIO()
    document = SimpleDocTemplate(
        output,
        pagesize=LETTER,
        rightMargin=0.7 * inch,
        leftMargin=0.7 * inch,
        topMargin=0.7 * inch,
        bottomMargin=0.7 * inch,
        title=note.title,
        author='Minutes',
    )
    body = ParagraphStyle('Body', fontName='DejaVuSans', fontSize=10, leading=14, spaceAfter=8)
    title = ParagraphStyle(
        'Title',
        parent=body,
        fontSize=20,
        leading=24,
        alignment=TA_CENTER,
        spaceAfter=14,
    )
    heading = ParagraphStyle('Heading', parent=body, fontSize=14, leading=18, spaceBefore=10, spaceAfter=8)

    def paragraph_markup(value: str) -> str:
        runs = []
        run_font = None
        run_text = ''

        def flush():
            nonlocal run_text
            if run_text:
                runs.append(f'<font name="{run_font}">{escape(run_text)}</font>')
                run_text = ''

        for character in value:
            if character == '\n':
                flush()
                runs.append('<br/>')
                run_font = None
                continue
            font_name = next((name for name, cmap in FONT_CHARACTER_MAPS if ord(character) in cmap), None)
            rendered = character if font_name else f'[U+{ord(character):04X}]'
            font_name = font_name or 'DejaVuSans'
            if font_name != run_font:
                flush()
                run_font = font_name
            run_text += rendered
        flush()
        return ''.join(runs)

    def paragraph(value: str, style: ParagraphStyle = body) -> Paragraph:
        return Paragraph(paragraph_markup(value), style)

    story = [
        paragraph(note.title, title),
        paragraph(f'Date: {note.meeting_date}'),
        paragraph(f"Attendees: {note.attendees or 'None'}"),
        Spacer(1, 6),
        paragraph('Notes', heading),
        paragraph(note.content or 'No notes.'),
        paragraph('Action items', heading),
    ]
    if note.action_items:
        for item in note.action_items:
            story.append(paragraph(
                f"Status: {'Completed' if item.done else 'Open'} | {item.text} | "
                f"Owner: {item.owner_name or 'Unassigned'} | Due: {item.due_date or 'No due date'}"
            ))
    else:
        story.append(paragraph('No action items.'))
    document.build(story)
    return output.getvalue()

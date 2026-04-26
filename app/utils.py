import logging
from io import BytesIO

import markdown
from weasyprint import HTML

log = logging.getLogger(__name__)


def _fmt(val, decimals: int = 1, suffix: str = "") -> str:
    """Format a value with the given number of decimals and suffix, or return 'N/A' if the value is None."""
    if val is None:
        return "N/A"
    return f"{float(val):.{decimals}f}{suffix}"


def generate_pdf_report(md_text: str) -> BytesIO:
    """
    Generate a PDF report from the given markdown text and return it as a BytesIO object.
    """
    log.info("Generating PDF report from markdown text of length %d", len(md_text))
    html = markdown.markdown(md_text)
    buffer = BytesIO()
    HTML(string=html).write_pdf(buffer)
    buffer.seek(0)
    return buffer

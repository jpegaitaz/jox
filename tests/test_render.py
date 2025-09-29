from pathlib import Path
from jox.cv.render import render_cv_pdf, render_cover_letter_pdf

def test_pdf(tmp_path):
    out1 = render_cv_pdf(tmp_path/"cv.pdf", "Engineer", "Hello\nWorld")
    out2 = render_cover_letter_pdf(tmp_path/"cl.pdf", "Engineer", "Dear Hiring,\n...")
    assert Path(out1).exists()
    assert Path(out2).exists()

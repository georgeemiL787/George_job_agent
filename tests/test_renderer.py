from agent.cv.renderer import latex_failure_summary


def test_latex_failure_summary_reads_first_error(tmp_path):
    tex_path = tmp_path / "bad.tex"
    tex_path.write_text("\\documentclass{article}", encoding="utf-8")
    (tmp_path / "bad.log").write_text(
        "noise\n! LaTeX Error: Unicode character U+202F not set up.\nl.10 bad line\n",
        encoding="utf-8",
    )

    assert "Unicode character U+202F" in latex_failure_summary(tex_path, tmp_path)


def test_latex_failure_summary_reads_package_error(tmp_path):
    tex_path = tmp_path / "bad.tex"
    tex_path.write_text("\\documentclass{article}", encoding="utf-8")
    (tmp_path / "bad.log").write_text(
        "noise\nPackage hyperref Error: Version mismatch!\nSee docs.\n",
        encoding="utf-8",
    )

    assert "Version mismatch" in latex_failure_summary(tex_path, tmp_path)

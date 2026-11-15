import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))
import make_release  # noqa: E402


def test_zipの名前に版が入る():
    v = make_release.app_version()
    assert re.fullmatch(r"[0-9]+(\.[0-9]+)+", v)
    assert make_release.zip_name() == f"{make_release.TOP}_v{v}.zip"       # 年月日ではない（同じ日に何度リリースしても、区別できる）

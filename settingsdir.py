"""文書フォルダーに連動する、テンプレート・定型文の設定。文書と同じ場所に置けるので、フォルダーごと別の PC へ持ち出せる。

置き場所: 文書のあるフォルダー（無ければ、親フォルダーへさかのぼって、最初に見つかったもの）の `.markdown-editor\\`
    snippets\\*.md   定型文（1ファイル＝1つ。名前はファイル名）
    templates\\*.md  テンプレート
    settings.json    {"snippets": {"inherit": false}, "templates": {"inherit": false}}

使う設定の優先順位（上が優先。同じ名前は、上のものだけを使う）:
    1. 文書フォルダーの設定   2. 自分用（%APPDATA%\\MarkdownEditor\\）   3. 組み込み（メモリの既定値）
`inherit` が false で、その種類のフォルダー（snippets\\ か templates\\）があるときは、**そのフォルダーのファイルだけ**を使う
（組み込み・自分用は出さない）。true、または指定が無ければ、下の層に、追加する。

先頭が `.` のフォルダーは、ファイル一覧に出ない（テンプレートが .md なので、文書の一覧に混ざらないため）。
このフォルダーだけは、編集できるよう、一覧に出す（mdeditor.scan_markdown の `INCLUDE_DOT_DIRS`）。
画面にも変換器にも依存しない。
"""
import json
import os
import re

SETTINGS_DIR = ".markdown-editor"
KINDS = ("snippets", "templates")
MAX_UP = 12                     # 親フォルダーへさかのぼる段数の上限
BAD_NAME = re.compile(r'[\\/:*?"<>|\x00-\x1f]')


def find_settings_dir(start):
    """start（ファイルでもフォルダーでも）から、親へさかのぼって、最初に見つかった設定フォルダー。無ければ None。"""
    if not start or not isinstance(start, str):
        return None
    d = os.path.abspath(start)
    if os.path.isfile(d):
        d = os.path.dirname(d)
    for _ in range(MAX_UP):
        cand = os.path.join(d, SETTINGS_DIR)
        if os.path.isdir(cand):
            return cand
        parent = os.path.dirname(d)
        if parent == d:
            break
        d = parent
    return None


def kind_dir(settings_dir, kind):
    """設定フォルダーの中の、その種類のフォルダー。無ければ None。"""
    if not settings_dir or kind not in KINDS:
        return None
    d = os.path.join(settings_dir, kind)
    return d if os.path.isdir(d) else None


def read_inherit(settings_dir, kind):
    """settings.json の、その種類の inherit。読めない・指定が無いときは True（下の層に追加する）。"""
    try:
        with open(os.path.join(settings_dir, "settings.json"), encoding="utf-8") as f:
            body = json.load(f)
        v = body.get(kind, {}).get("inherit")
        return v if isinstance(v, bool) else True
    except (OSError, ValueError, AttributeError, TypeError):
        return True


def list_md(folder, kind_label):
    """フォルダーの中の .md を、名前順に返す（サブフォルダーは見ない）。[{"id","name","kind"}]。"""
    try:
        names = [n for n in os.listdir(folder) if n.lower().endswith(".md") and os.path.isfile(os.path.join(folder, n))]
    except OSError:
        return []
    names.sort(key=lambda n: n.casefold())
    return [{"id": "file:" + os.path.join(folder, n), "name": os.path.splitext(n)[0], "kind": kind_label} for n in names]


def merge(project, user, builtin, project_present, inherit):
    """層を合わせる。project_present: 文書フォルダーの設定に、その種類のフォルダーがあるか。"""
    if project_present and not inherit:
        return list(project)                                    # そのフォルダーのファイルだけ
    seen, out = set(), []
    for layer in (project, user, builtin):
        for it in layer:
            key = it["name"].casefold()
            if key in seen:
                continue                                        # 同じ名前は、上の層のものだけ
            seen.add(key)
            out.append(it)
    return out


def safe_file_name(name):
    """項目の名前を、ファイル名にできる形にする（使えない文字は _）。空になったら「無題」。"""
    s = BAD_NAME.sub("_", str(name)).strip().rstrip(". ")
    return (s[:80] or "無題")


def export_set(settings_dir, kind, items):
    """items（[{"name","text"}]）を、設定フォルダーの kind\\ に、.md として書き出す。**既にあるファイルは、上書きしない**。
    settings.json の、その種類の inherit を false にする（そのフォルダーのファイルだけを使う）。{"written", "skipped"} を返す。"""
    target = os.path.join(settings_dir, kind)
    os.makedirs(target, exist_ok=True)
    written = skipped = 0
    for it in items:
        path = os.path.join(target, safe_file_name(it["name"]) + ".md")
        if os.path.exists(path):
            skipped += 1
            continue
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(it["text"])
        written += 1
    cfg_path = os.path.join(settings_dir, "settings.json")
    try:
        with open(cfg_path, encoding="utf-8") as f:
            cfg = json.load(f)
        if not isinstance(cfg, dict):
            cfg = {}
    except (OSError, ValueError):
        cfg = {}
    section = cfg.get(kind) if isinstance(cfg.get(kind), dict) else {}
    section["inherit"] = False
    cfg[kind] = section
    with open(cfg_path, "w", encoding="utf-8", newline="") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    return {"written": written, "skipped": skipped}

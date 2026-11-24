"""置換セット: よく使う置換（検索する文字列と、置換後の文字列）に名前を付けて保存し、順に実行する。

- 1 つのセットは、名前と、1 つ以上の手順から成る。手順は、検索・置換後・正規表現か・大文字小文字を区別するか。
  実行は、手順 1 → 手順 2 … の順に、前の手順の結果へ、次の手順を当てる。
- 標準のセット（BUILTIN）は、読み取り専用。コピーして、編集できる。利用者のセットは、設定の置き場の
  `replace_sets.json` に保存する。
- **文書のフォルダー用のセット**: 文書のあるフォルダー（無ければ、親へさかのぼって、最初に見つかったもの）の
  `.markdown-editor\\replace_sets.json` に置く（テンプレート・定型文と同じ置き場。フォルダーごと別の PC へ持ち出せる）。
  形式は、自分用と同じ。手で書いてもよい（id は、無ければ名前から作る）。settings.json の
  `{"replace_sets": {"inherit": false}}` で、そのフォルダーでは、標準と自分用のセットを出さない。
- 正規表現の確かめと、実際の置換は、画面側（find.js）が行う（検索・置換の画面と、同じ規則で動かすため）。
  ここでは、保存してよい形かどうか（型・長さ・件数）だけを確かめる。
- 画面にも変換器にも依存しない（試験できるように）。
"""
import hashlib
import json
import os
import re
import tempfile

MAX_SETS = 100
MAX_STEPS = 50
MAX_NAME = 60
MAX_TEXT = 2000
NAME_DEFAULT = "名前のない置換セット"
PROJECT_FILE = "replace_sets.json"
KIND = "replace_sets"                 # settings.json の項目名


def _step(find, replace, regex=False, case=False):
    return {"find": find, "replace": replace, "regex": bool(regex), "case": bool(case)}


# 標準のセット。正規表現は、JavaScript のもの（前読み・後ろ読みが使える）
BUILTIN = [
    {"id": "b-img", "name": "画像を <img> に変換（![代替](URL) → <img>）", "builtin": True, "steps": [
        _step(r'!\[([^\]]*)\]\(([^)\s]+)\s+"([^"]*)"\)', '<img src="$2" alt="$1" title="$3">', True),
        _step(r'!\[([^\]]*)\]\(([^)\s]+)\)', '<img src="$2" alt="$1">', True),
    ]},
    {"id": "b-link", "name": "リンクを <a> に変換（[文字](URL) → <a>）", "builtin": True, "steps": [
        _step(r'(?<!!)\[([^\]]+)\]\(([^)\s]+)\s+"([^"]*)"\)', '<a href="$2" title="$3">$1</a>', True),
        _step(r'(?<!!)\[([^\]]+)\]\(([^)\s]+)\)', '<a href="$2">$1</a>', True),
    ]},
    {"id": "b-bold", "name": "**太字** と *斜体* を <strong> と <em> に変換", "builtin": True, "steps": [
        _step(r'\*\*([^*\n]+)\*\*', '<strong>$1</strong>', True),
        _step(r'(?<![*\w])\*([^*\n]+)\*(?![*\w])', '<em>$1</em>', True),
    ]},
    {"id": "b-trail", "name": "行末の空白を削除", "builtin": True, "steps": [
        _step(r'[ \t　]+$', '', True),
    ]},
    {"id": "b-bullet", "name": "箇条書きの記号を - にそろえる（* や + → -）", "builtin": True, "steps": [
        _step(r'^(\s*)[*+] ', '$1- ', True),
    ]},
]


def _text(v, limit):
    return v if isinstance(v, str) and len(v) <= limit else None


def _make_id(name, scope, used):
    """id が無いセット（手で書いたファイル）の id を、名前から作る。同じ名前でも、重ならないようにする。"""
    base = ("p-" if scope == "project" else "u-") + hashlib.sha1(name.encode("utf-8")).hexdigest()[:10]
    sid, k = base, 2
    while used is not None and sid in used:
        sid, k = "%s%d" % (base, k), k + 1
    return sid


def clean_set(value, used_ids=None, scope="user"):
    """利用者のセット（自分用・文書フォルダー用）として保存してよい形に直す。使えないものは None。
    id が無ければ、名前から作る。標準の id（b-）や、形の正しくない id は、使えない。"""
    if not isinstance(value, dict):
        return None
    sid = value.get("id")
    if sid is not None and not (isinstance(sid, str) and re.fullmatch(r"[up]-[A-Za-z0-9]{1,38}", sid)):
        return None
    if sid is not None and used_ids is not None and sid in used_ids:
        return None
    name = _text(value.get("name"), MAX_NAME)
    name = (name or "").strip() or NAME_DEFAULT
    if sid is None:
        sid = _make_id(name, scope, used_ids)
    steps = []
    raw = value.get("steps")
    if not isinstance(raw, list):
        return None
    for s in raw[:MAX_STEPS]:
        if not isinstance(s, dict):
            continue
        f, r = _text(s.get("find"), MAX_TEXT), _text(s.get("replace"), MAX_TEXT)
        if f is None or r is None:
            continue
        steps.append(_step(f, r, s.get("regex") is True, s.get("case") is True))
    return {"id": sid, "name": name, "builtin": False, "scope": scope, "steps": steps}


def clean_sets(value, scope="user"):
    out, used = [], set()
    if isinstance(value, list):
        for v in value[:MAX_SETS]:
            c = clean_set(v, used, scope)
            if c:
                out.append(c)
                used.add(c["id"])
    return out


def load(path, scope="user"):
    """保存してあるセット（自分用・文書フォルダー用）。無い・壊れているときは、空。"""
    try:
        with open(path, encoding="utf-8") as f:
            return clean_sets(json.load(f).get("sets"), scope)
    except (OSError, ValueError, AttributeError):
        return []


def project_path(settings_dir):
    return os.path.join(settings_dir, PROJECT_FILE)


def load_project(settings_dir):
    return load(project_path(settings_dir), "project") if settings_dir else []


def save(path, sets, scope="user"):
    """セットを保存する（一時ファイルへ書いてから置き換える）。保存した内容（整えたもの）を返す。"""
    cleaned = clean_sets(sets, scope)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".replace_sets_", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump({"version": 1, "sets": cleaned}, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except OSError:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise
    return cleaned

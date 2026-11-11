"""Markdown の検査（lint）。「書いたつもり」と「プレビューに出るもの」が食い違う書き方を見つける。

- 画面に依存しない。`lint(text, md, doc_path, disabled)` が、問題の一覧を返す。
- 変換器（markdown-it）で文書を読み、プレビューと同じ解釈のうえで調べる。コードブロックの中の `#` や
  `**` を誤って指摘しない。
- 規則の番号（MD001 など）は markdownlint に合わせた。X で始まる番号は、このアプリ固有の検査。
- 直さない。どこが、なぜ問題かを示すだけ（直し方を決めるのは書いた人）。
- 数式（KaTeX）と図（Mermaid）の書き間違いは、描画してみないと分からないので、画面側（ui.html）が集める。
- 文書の中の指示で、行ごとに止められる: `<!-- lint-disable MD009 -->` … `<!-- lint-enable MD009 -->`、
  `<!-- lint-disable-next-line MD009 -->`、`<!-- lint-disable-line MD009 -->`（規則を省くと、すべて）。
  `markdownlint-` で始まる書き方も同じに読む。
"""
import json
import os
import re
from urllib.parse import unquote, urlsplit
from urllib.request import url2pathname

import mdext
import sanitize
from toc import ID_ATTR

MAX_ISSUES = 500
MAX_CHARS = 2000000
MAX_FILE_CHECKS = 300             # ファイルの有無を調べる数の上限（ネットワーク上の文書でも遅くならないように）

WARNING, INFO = "warning", "info"

# (番号, 名前, 既定で検査するか, 説明)
RULES = [
    ("MD001", "見出しの段が飛んでいる", True, "# の次に ### を使うなど、見出しの段を飛ばしています。目次や構造が崩れます。"),
    ("MD009", "行末の空白", True, "行の終わりに余分な空白があります（ちょうど2つで、次の行へ続くときは改行として使えるので指摘しません）。"),
    ("MD010", "タブ文字", False, "行の中にタブ文字があります。"),
    ("MD012", "空行が続いている", True, "空行が2行以上続いています。"),
    ("MD018", "# のあとに空白がない", True, "#見出し のように、# の直後に空白がないため、見出しになりません。"),
    ("MD022", "見出しの前後に空行がない", True, "見出しの前後に空行がありません。表示が崩れる処理系があります。"),
    ("MD024", "同じ見出しが重なっている", True, "同じ文言の見出しが複数あります。目次のリンク先が -1 -2 と分かれます。"),
    ("MD025", "第1段の見出しが複数ある", True, "文書の題名にあたる # の見出しが複数あります。"),
    ("MD026", "見出しの末尾の句読点", False, "見出しの終わりに句読点や記号があります。"),
    ("MD040", "コードブロックの言語がない", False, "コードブロックに言語の指定がなく、色分けされません。"),
    ("MD042", "リンク先が空", True, "[文字]() のように、リンク先が空です。"),
    ("MD045", "画像の代替文字がない", False, "![](画像) のように、代替文字（alt）が空です。"),
    ("MD051", "文書内リンクの飛び先がない", True, "[文字](#見出し) の飛び先の見出しや id が、文書の中にありません。"),
    ("MD052", "参照リンクの定義がない", True, "[文字][名前] の [名前]: URL の定義がありません。"),
    ("X001", "リンク先のファイルがない", True, "相対パスや絶対パスのリンク先のファイルが見つかりません。"),
    ("X002", "画像のファイルがない", True, "画像のファイルが見つからないため、プレビューに表示されません。"),
    ("X003", "表示されない HTML", True, "このアプリは安全のため一部の HTML の要素・属性を取り除くので、書いても表示されません。"),
    ("X004", "強調の記号が残っている", True, "**太字** や ~~取り消し線~~ の記号が、効かずに文字のまま表示されます。"),
    ("X005", "コードブロックが閉じていない", True, "``` の閉じが足りず、以降がすべてコードになります。"),
    ("X006", "数式の $$ が対になっていない", True, "$$ の閉じが足りないか、数式として読めない書き方です。"),
    ("X007", "表の書き方", True, "表として認識されない、またはセルが多くて切り捨てられる表です。"),
    ("X008", "グラフの JSON の誤り", True, "```vega-lite の中身が JSON として読めません。"),
    ("X009", "数式の誤り", True, "KaTeX が数式を組めません（プレビューを描いた結果から集めます）。"),
    ("X010", "図の誤り", True, "Mermaid が図を描けません（プレビューを描いた結果から集めます）。"),
    ("X011", "脚注の書き方", True, "本文の [^1] に対応する [^1]: の定義がない、または、定義があるのに本文から使われていません。"),
    ("X012", "注釈ブロックの書き方", True, "Qiita の :::note の種類が info・warn・alert 以外、または、閉じの ::: がありません。"),
    ("X013", "アラートの種類", True, "GitHub のアラートは [!NOTE] [!TIP] [!IMPORTANT] [!WARNING] [!CAUTION] の5種類です。"),
]
RULE_IDS = [r[0] for r in RULES]
DEFAULT_OFF = [r[0] for r in RULES if not r[2]]

DIRECTIVE = re.compile(r"<!--\s*(?:markdownlint|lint)-(disable-next-line|disable-line|disable|enable)"
                       r"((?:\s+[A-Za-z]+[0-9]+)*)\s*-->", re.I)
HEADING_NO_SPACE = re.compile(r"^ {0,3}#{1,6}[^\s#0-9]")
DELIMITER_ROW = re.compile(r"^\s*\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)*\|?\s*$")
TAG = re.compile(r"<\s*(/?)\s*([A-Za-z][A-Za-z0-9-]*)((?:\s+[^<>]*?)?)\s*/?>")
ATTR = re.compile(r"""([A-Za-z_:][-A-Za-z0-9_:.]*)(?:\s*=\s*("[^"]*"|'[^']*'|[^\s"'>]+))?""")
CLOSING_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})\s*$")
EXTERNAL = re.compile(r"^(?:[A-Za-z][A-Za-z0-9+.-]+:)", re.I)
PUNCT_END = tuple(".,;:!。、，；：！")


def _edit(start, end, text):
    """文書の範囲（行・桁は 0 から）を、text に置き換える編集。"""
    return {"from": [start[0], start[1]], "to": [end[0], end[1]], "text": text}


def _fix(label, *edits):
    return {"label": label, "edits": list(edits)}


def apply_edits(text, edits):
    """編集の一覧を、文書に当てて返す。画面（CodeMirror）と同じに、後ろの編集から当て、
    すでに当てた編集と重なるものは飛ばす。当てた数も返す: (新しい文書, 当てた数)。"""
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    offsets, pos = [], 0
    for ln in lines:
        offsets.append(pos)
        pos += len(ln) + 1
    body = "\n".join(lines)

    def at(p):
        return offsets[p[0]] + p[1]

    todo = sorted(edits, key=lambda e: (at(e["from"]), at(e["to"])), reverse=True)
    applied, floor = 0, len(body) + 1
    for e in todo:
        a, b = at(e["from"]), at(e["to"])
        if b > floor or a > b:                 # すでに当てた編集（より後ろ）と重なる
            continue
        body = body[:a] + e["text"] + body[b:]
        floor = a
        applied += 1
    return body, applied


def collect_edits(issues):
    return [e for i in issues for e in (i.get("fix") or {}).get("edits", [])]


def _normalize_label(label):
    return re.sub(r"\s+", " ", label.strip()).upper()


def _directives(lines, code_lines):
    """行ごとに、止めている規則の集合（None は全部）を返す。"""
    disabled = {}           # 規則 → 止めている。"*" は全部
    result = []
    next_line = {}          # 行 → 次の行だけ止める規則
    for i, line in enumerate(lines):
        here = set()
        if i not in code_lines and "<!--" in line:
            for m in DIRECTIVE.finditer(line):
                kind = m.group(1).lower()
                rules = {r.upper() for r in m.group(2).split()} or {"*"}
                if kind == "disable":
                    for r in rules:
                        disabled[r] = True
                elif kind == "enable":
                    if "*" in rules:
                        disabled.clear()
                    else:
                        for r in rules:
                            disabled.pop(r, None)
                elif kind == "disable-line":
                    here |= rules
                else:
                    next_line.setdefault(i + 1, set()).update(rules)
        result.append(set(disabled) | here | next_line.get(i, set()))
    return result


def _walk_inline(tok, base_line):
    """インラインの部品を、(部品, その行) で返す。改行のたびに行を進める。"""
    line = base_line
    for child in tok.children or []:
        yield child, line
        if child.type in ("softbreak", "hardbreak"):
            line += 1


def _split_cells(row):
    """表の1行のセル数。`\\|` は区切りにしない。コードスパンを含む行は数えない（None）。"""
    if "`" in row:
        return None
    s = row.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|") and not s.endswith("\\|"):
        s = s[:-1]
    return len(re.split(r"(?<!\\)\|", s))


def _local_path(href, base):
    """リンク・画像のパスを、調べるファイルの場所にする。調べられない書き方は None。"""
    raw = href.strip()
    if not raw or raw.startswith("#") or raw.startswith("//") or raw.startswith("\\\\"):
        return None
    if re.match(r"(?i)^file:", raw):
        parts = urlsplit(raw)
        if parts.netloc not in ("", "localhost"):
            return None
        path = url2pathname(unquote(parts.path))
        if os.name == "nt" and re.match(r"^[\\/][A-Za-z]:", path):
            path = path[1:]
    else:
        if EXTERNAL.match(raw) and not re.match(r"^[A-Za-z]:[\\/]", raw):
            return None                                   # http: mailto: などは調べない
        path = unquote(raw.split("#")[0].split("?")[0])
        if not path:
            return None
        if os.name == "nt" and path[:1] in ("/", "\\") and base:
            path = os.path.splitdrive(base)[0] + path
        elif not os.path.isabs(path):
            if not base:
                return None
            path = os.path.join(base, path)
    return os.path.normpath(path)


def lint(text, md, doc_path=None, disabled=()):
    """問題の一覧を返す: [{"line": 0 から数えた行, "rule", "severity", "message"}]（行の順）。"""
    if not text or len(text) > MAX_CHARS:
        return []
    off = {d.upper() for d in disabled}
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    if len(lines) > 1 and lines[-1] == "":
        lines.pop()                    # 末尾の改行のあとの空要素は、行ではない（「a\n\n」の空行1つを、続く空行としない）
    env = {"base": os.path.dirname(doc_path) if doc_path else ""}
    tokens = md.parse("\n".join(lines), env)
    base = os.path.dirname(doc_path) if doc_path else ""

    code_lines, raw_lines = set(), set()      # コードの行 / HTML の行
    for t in tokens:
        if not t.map:
            continue
        if t.type in ("fence", "code_block"):
            code_lines.update(range(t.map[0], t.map[1]))
        elif t.type == "html_block" or "math" in t.type:
            raw_lines.update(range(t.map[0], t.map[1]))
    skip = code_lines | raw_lines
    muted = _directives(lines, code_lines)

    issues = []

    def add(line, rule, severity, message, fix=None):
        if rule in off:
            return
        line = max(0, min(line, len(lines) - 1))
        if "*" in muted[line] or rule in muted[line]:
            return
        issue = {"line": line, "rule": rule, "severity": severity, "message": message}
        if fix:
            issue["fix"] = fix
        issues.append(issue)

    # --- 行ごとの検査 ---
    blank_run = 0
    for i, line in enumerate(lines):
        if i in code_lines:
            blank_run = 0
            continue
        if not line.strip():
            blank_run += 1
            if blank_run == 2:
                j = i
                while j < len(lines) and not lines[j].strip() and j not in code_lines:
                    j += 1                                         # 続く空行の終わり（i から j の手前まで、余分）
                if j < len(lines):
                    edit = _edit((i, 0), (j, 0), "")
                else:                                              # 文書の終わりまで続くとき
                    edit = _edit((i - 1, len(lines[i - 1])), (len(lines) - 1, len(lines[-1])), "")
                add(i, "MD012", WARNING, "空行が続いています（1行にまとめます）", _fix("余分な空行を取り除く", edit))
            continue
        blank_run = 0
        if i in raw_lines:
            continue
        stripped = line.rstrip(" \t")
        trail = line[len(stripped):]
        if trail:
            nxt = lines[i + 1] if i + 1 < len(lines) else ""
            if not (trail == "  " and nxt.strip()):
                add(i, "MD009", INFO, "行末に余分な空白があります",
                    _fix("行末の空白を取り除く", _edit((i, len(stripped)), (i, len(line)), "")))
        if "\t" in line:
            add(i, "MD010", INFO, "タブ文字があります（半角空白にそろえます）")
        if HEADING_NO_SPACE.match(line) and (i == 0 or not lines[i - 1].strip()):
            m = re.match(r"^ {0,3}#{1,6}", line)
            add(i, "MD018", WARNING, "# の直後に空白がないため、見出しになりません",
                _fix("# の後ろに空白を入れる", _edit((i, m.end()), (i, m.end()), " ")))

    # --- 見出し ---
    last_level, seen, h1 = 0, {}, 0
    eff_last = 0                       # 段の飛びを直したあとの、直前の見出しの段（直す先を決めるため）
    ids, html_ids = set(), set()
    for idx, t in enumerate(tokens):
        if t.type == "heading_open" and t.map:
            level = int(t.tag[1])
            ident = t.attrs.get("id") if hasattr(t, "attrs") else None
            if ident:
                ids.add(ident)
            label = ""
            if idx + 1 < len(tokens) and tokens[idx + 1].type == "inline":
                label = "".join(c.content for c in tokens[idx + 1].children or []
                                if c.type in ("text", "code_inline")).strip()
            fix001, new_level = None, level
            if last_level and level > last_level + 1:
                new_level = eff_last + 1
                m = re.match(r"^( {0,3})(#{1,6})(?=[ \t]|$)", lines[t.map[0]])
                if m and t.markup.startswith("#") and new_level < level:        # 設定欄（===・---）の見出しは、直さない
                    fix001 = _fix("見出しの段を %s にする" % ("#" * new_level),
                                  _edit((t.map[0], m.end(1)), (t.map[0], m.end(2)), "#" * new_level))
                add(t.map[0], "MD001", WARNING,
                    "見出しの段が飛んでいます（%s の次に %s）" % ("#" * last_level, "#" * level), fix001)
            last_level = level
            eff_last = new_level if fix001 else level
            if t.level == 0:
                before = t.map[0] - 1
                if before >= 0 and lines[before].strip():
                    add(t.map[0], "MD022", WARNING, "見出しの前に空行がありません",
                        _fix("見出しの前に空行を入れる", _edit((t.map[0], 0), (t.map[0], 0), "\n")))
                after = t.map[1]
                if after < len(lines) and lines[after].strip():
                    add(t.map[0], "MD022", WARNING, "見出しの後に空行がありません",
                        _fix("見出しの後に空行を入れる", _edit((after, 0), (after, 0), "\n")))
            if label:
                if label in seen:
                    add(t.map[0], "MD024", INFO,
                        "「%s」と同じ見出しが %d 行目にもあります" % (label, seen[label] + 1))
                else:
                    seen[label] = t.map[0]
                if label.endswith(PUNCT_END):
                    add(t.map[0], "MD026", INFO, "見出しの末尾に句読点があります")
            if level == 1:
                h1 += 1
                if h1 == 2:
                    add(t.map[0], "MD025", INFO, "第1段（#）の見出しが複数あります")
        elif t.type in ("html_block", "inline") and t.content and "id" in t.content.lower():
            for m in re.finditer(r"<[^>]*>", t.content):
                for im in ID_ATTR.finditer(m.group(0)):
                    html_ids.add(im.group(2))
                nm = re.search(r"""\bname\s*=\s*(["'])(.*?)\1""", m.group(0), re.I)
                if nm and m.group(0).lower().startswith("<a"):
                    html_ids.add(nm.group(2))

    # --- 本文の部品（リンク・画像・文字・HTML） ---
    refs = env.get("references", {})
    checks = 0
    for t in tokens:
        if t.type == "fence" and t.map:
            lang = t.info.strip().split(" ")[0].lower()
            if not lang:
                add(t.map[0], "MD040", INFO, "コードブロックに言語の指定がありません")
            if t.level == 0:
                last = lines[t.map[1] - 1] if t.map[1] - 1 > t.map[0] else ""
                m = CLOSING_FENCE.match(last)
                closed = bool(m) and m.group(1)[0] == t.markup[0] and len(m.group(1)) >= len(t.markup)
                if not closed:
                    add(t.map[0], "X005", WARNING,
                        "コードブロック（%s）が閉じられていません。以降がすべてコードになります" % t.markup)
            if lang in ("vega-lite", "vegalite", "vega"):
                try:
                    json.loads(t.content)
                except ValueError as e:
                    ln = getattr(e, "lineno", 1) or 1
                    add(t.map[0] + ln, "X008", WARNING, "グラフの JSON を読めません: " + str(e).split(": line")[0])
        elif t.type == "html_block" and t.map:
            _check_html(t.content, t.map[0], add)
        elif t.type == "table_open" and t.map and t.level == 0:
            head = _split_cells(lines[t.map[0]])
            for ln in range(t.map[0] + 2, min(t.map[1], len(lines))):
                n = _split_cells(lines[ln])
                if head and n and n > head:
                    add(ln, "X007", WARNING,
                        "セルが見出し行（%d列）より多いため、はみ出した分は表示されません" % head)
        elif t.type == "paragraph_open" and t.map and t.map[1] - t.map[0] >= 2:
            first, second = lines[t.map[0]], lines[t.map[0] + 1]
            if "|" in first and "|" in second and DELIMITER_ROW.match(second):
                add(t.map[0], "X007", WARNING,
                    "表として認識されません（見出し行と区切り行の列数が合っているか確認してください）")
        elif t.type == "inline" and t.map:
            for child, ln in _walk_inline(t, t.map[0]):
                ctype = child.type
                if ctype == "link_open":
                    href = child.attrGet("href") or ""
                    if href in ("", "#"):
                        add(ln, "MD042", WARNING, "リンク先が空です")
                    elif href.startswith("#") and len(href) > 1:
                        frag = unquote(href[1:])
                        if frag not in ids and frag not in html_ids and href[1:] not in ids \
                                and href[1:] not in html_ids:
                            add(ln, "MD051", WARNING, "飛び先「%s」の見出しや id が文書にありません" % frag)
                    elif doc_path and checks < MAX_FILE_CHECKS:
                        path = _local_path(href, base)
                        if path:
                            checks += 1
                            if not os.path.exists(path):
                                add(ln, "X001", WARNING, "リンク先のファイルが見つかりません: " + href)
                elif ctype == "image":
                    src = child.attrGet("src") or ""
                    if not "".join(c.content for c in child.children or []).strip() and not child.content.strip():
                        add(ln, "MD045", INFO, "画像の代替文字（alt）が空です")
                    if doc_path and src and not src.startswith("data:") and checks < MAX_FILE_CHECKS:
                        path = _local_path(src, base)
                        if path:
                            checks += 1
                            if not os.path.exists(path):
                                add(ln, "X002", WARNING, "画像のファイルが見つかりません: " + src)
                elif ctype == "text":
                    c = child.content
                    if "**" in c or "~~" in c:
                        add(ln, "X004", WARNING,
                            "強調の記号が効かず、文字のまま表示されます（%s の前後の文字や空白を確認）"
                            % ("**" if "**" in c else "~~"))
                    if "$$" in c:
                        add(ln, "X006", WARNING, "数式の $$ が対になっていません（閉じが無いか、途中に空行があります）")
                    for m in re.finditer(r"\[([^\]]+)\]\[([^\]]*)\]", c):
                        label = m.group(2) or m.group(1)
                        if _normalize_label(label) not in refs:
                            add(ln, "MD052", WARNING, "参照「%s」の定義（[%s]: URL）がありません" % (label, label))
                elif ctype == "html_inline":
                    _check_html(child.content, ln, add)
    # 未対応の段落（$$ の閉じ忘れ）は、数式のブロックにならず段落として残る。上の text の検査で拾う

    _check_extensions(lines, tokens, skip, add)

    issues.sort(key=lambda x: (x["line"], x["rule"]))
    seen_keys, out = set(), []
    for it in issues:
        key = (it["line"], it["rule"], it["message"])
        if key not in seen_keys:
            seen_keys.add(key)
            out.append(it)
        if len(out) >= MAX_ISSUES:
            break
    return out


FOOTNOTE_REF = re.compile(r"\[\^([^\]\s]+)\]")
FOOTNOTE_DEF = re.compile(r"^ {0,3}\[\^([^\]\s]+)\]:")
COLON_OPEN = re.compile(r"^ {0,3}:{3,}[ \t]*([^\s:]\S*)(.*)$")
COLON_CLOSE = re.compile(r"^ {0,3}:{3,}[ \t]*$")
ALERT_MARK = re.compile(r"^ {0,3}>[ \t]*\[!([A-Za-z]+)\][ \t]*$")
INLINE_CODE = re.compile(r"`[^`\n]*`")


def _check_extensions(lines, tokens, skip, add):
    """脚注・Qiita の注釈ブロック・GitHub のアラートの書き間違い（mdext.py の書き方）。"""
    defined = {}                                       # 定義（[^x]: 説明）。使われない定義は、変換器が捨てるので、文字から拾う
    used = {}
    stack = []                                         # 開いている ::: のブロック (名前, 行)
    for i, line in enumerate(lines):
        if i in skip:
            continue
        m = COLON_CLOSE.match(line)
        if m:
            if stack:
                stack.pop()
            continue
        m = COLON_OPEN.match(line)
        if m:
            name, rest = m.group(1), m.group(2)
            if name == "note":
                if mdext.note_kind("note" + rest) is None:
                    add(i, "X012", WARNING, "注釈ブロックの種類は info・warn・alert のどれかです（「%s」は、注釈になりません）" % rest.strip())
                    continue
            stack.append((name, i))
            continue
        m = ALERT_MARK.match(line)
        if m and m.group(1).upper() not in mdext.ALERTS:
            add(i, "X013", WARNING, "[!%s] は、GitHub のアラートの種類ではありません（NOTE・TIP・IMPORTANT・WARNING・CAUTION）" % m.group(1))
        plain = INLINE_CODE.sub("", line)
        dm = FOOTNOTE_DEF.match(plain)
        if dm:
            defined.setdefault(dm.group(1), i)
        for fm in FOOTNOTE_REF.finditer(plain):
            if dm and fm.start() == dm.start(1) - 2:
                continue                               # 定義の行の先頭の [^x]: は、参照ではない
            used.setdefault(fm.group(1), i)
    for label, i in used.items():
        if label not in defined:
            add(i, "X011", WARNING, "脚注 [^%s] の定義（[^%s]: 説明）がありません" % (label, label))
    for label, i in defined.items():
        if label not in used:
            add(i, "X011", INFO, "脚注 [^%s] は、本文から使われていません" % label)
    for name, i in stack:
        if name == "note":
            add(i, "X012", WARNING, "注釈ブロック（:::note）が閉じられていません。以降がすべて注釈になります（閉じは :::）")


def _check_html(content, line, add):
    """HTML の断片のうち、プレビューで取り除かれる要素・属性を指摘する。"""
    reported = set()
    for m in TAG.finditer(content):
        closing, tag, attrs = m.group(1), m.group(2).lower(), m.group(3) or ""
        ln = line + content[:m.start()].count("\n")
        if closing:
            continue
        if tag in sanitize.DROP_WITH_CONTENT:
            if tag not in reported:
                reported.add(tag)
                add(ln, "X003", WARNING, "<%s> は安全のため中身ごと取り除かれ、表示されません" % tag)
            continue
        if tag not in sanitize.TAGS:
            if tag not in reported:
                reported.add(tag)
                add(ln, "X003", WARNING, "<%s> は使えない要素なので、タグが取り除かれます" % tag)
            continue
        allowed = sanitize.COMMON | sanitize.ATTRS.get(tag, set()) | {"style"}
        for am in ATTR.finditer(attrs):
            name = am.group(1).lower()
            value = (am.group(2) or "").strip("\"'")
            key = (tag, name)
            if key in reported:
                continue
            if name not in allowed:
                reported.add(key)
                add(ln, "X003", WARNING, "<%s> の %s 属性は取り除かれます" % (tag, name))
            elif name == "style" and sanitize.safe_style(value, tag) is None:
                reported.add(key)
                add(ln, "X003", INFO, "style 属性は、改ページと表の文字寄せ以外は取り除かれます")
            elif name == "href" and sanitize.safe_url(value, sanitize.LINK_SCHEMES) is None:
                reported.add(key)
                add(ln, "X003", WARNING, "このリンク先の書き方は許可されておらず、取り除かれます")
            elif name == "src" and sanitize.safe_url(value, sanitize.IMG_SCHEMES, allow_data_image=True) is None:
                reported.add(key)
                add(ln, "X003", WARNING, "この画像の指定は許可されておらず、取り除かれます")

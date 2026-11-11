"""Qiita・GitHub などで広く使われている Markdown の拡張。ビューアとエディタで同じ内容を使う。

- 脚注: 本文の `[^1]` と、`[^1]: 説明` の行（PHP Markdown Extra で広まり、Qiita・GitHub・Obsidian・Pandoc などが対応）。
  文末に脚注の一覧を出し、本文との間を行き来するリンクを付ける。標準（CommonMark・GFM の仕様）には無い。
- Qiita の注釈ブロック: `:::note info`（`warn`・`alert`）〜 `:::`。種類を書かなければ info。
  Qiita の表示に合わせて、見出しは付けず、色と左の線だけで区別する。
- GitHub のアラート: 引用の最初の行に `[!NOTE]`（`[!TIP]`・`[!IMPORTANT]`・`[!WARNING]`・`[!CAUTION]`）を書く。
  引用の書き方に乗っているので、対応していないアプリでは、ただの引用に見える。GitHub と同じく、英語の見出しを付ける。
- コードブロックの情報行: ```ruby:app.rb は、言語 ruby とファイル名 app.rb（Qiita・Zenn の書き方）。
  ```diff_ruby は、差分（Qiita の書き方）。この 2 つは highlight.py が読み、ファイル名の表示は `filename_html` が作る。

文字は1字も捨てない（脚注の定義・注釈の中身は、そのまま表示される）。HTML は、変換器が組み立てるものだけで、
利用者が書いた HTML は、従来どおり sanitize.py を通る。
"""
import re
from html import escape

NOTE_KINDS = {"": "info", "info": "info", "warn": "warn", "alert": "alert"}     # :::note のあとの語 → 種類
ALERTS = {                                                                        # [!NOTE] → (種類, 見出し)
    "NOTE": ("note", "Note"),
    "TIP": ("tip", "Tip"),
    "IMPORTANT": ("important", "Important"),
    "WARNING": ("warning", "Warning"),
    "CAUTION": ("caution", "Caution"),
}
_ALERT_HEAD = re.compile(r"^\[!(NOTE|TIP|IMPORTANT|WARNING|CAUTION)\][ \t]*(?:\n|$)", re.I)


def note_kind(params):
    """`:::note info` の、`:::` のあと（"note info"）から、種類を返す。注釈ブロックでなければ None。"""
    words = (params or "").split()
    if not words or words[0] != "note" or len(words) > 2:
        return None
    return NOTE_KINDS.get(words[1].lower() if len(words) == 2 else "")


def _validate_note(params, *args):
    return note_kind(params) is not None


def _render_note(self, tokens, idx, options, env):
    tok = tokens[idx]
    if tok.nesting == 1:
        tok.attrJoin("class", "md-note md-note-" + (note_kind(tok.info) or "info"))
    return self.renderToken(tokens, idx, options, env)


def _footnote_caption(self, tokens, idx, options, env):
    """本文の中の番号。標準では [1] と括弧が付く。GitHub と同じく、数字だけにする（上付きにする）。"""
    n = str(tokens[idx].meta["id"] + 1)
    if tokens[idx].meta["subId"] > 0:
        n += ":" + str(tokens[idx].meta["subId"])
    return n


def _alerts(state):
    """引用の最初の行が [!NOTE] などなら、アラートにする（印を取り除き、見出しを足す）。"""
    from markdown_it.token import Token

    toks = state.tokens
    i = 0
    while i < len(toks) - 2:
        t = toks[i]
        if t.type == "blockquote_open" and toks[i + 1].type == "paragraph_open" and toks[i + 2].type == "inline":
            inline = toks[i + 2]
            m = _ALERT_HEAD.match(inline.content)
            kids = inline.children or []
            if m and kids and kids[0].type == "text" and kids[0].content.strip().upper() == "[!" + m.group(1).upper() + "]":
                kind, title = ALERTS[m.group(1).upper()]
                rest = kids[1:]
                if rest and rest[0].type == "softbreak":
                    rest = rest[1:]
                inline.children = rest
                inline.content = inline.content[m.end():]
                t.attrJoin("class", "md-alert md-alert-" + kind)
                p_open = Token("paragraph_open", "p", 1)
                p_open.attrSet("class", "md-alert-title")
                body = Token("inline", "", 0)
                body.content = title
                text = Token("text", "", 0)
                text.content = title
                body.children = [text]
                p_close = Token("paragraph_close", "p", -1)
                head = [p_open, body, p_close]
                if rest:
                    toks[i + 1:i + 1] = head                 # 見出しを、本文の段落の前に入れる
                    i += 3
                else:
                    toks[i + 1:i + 4] = head                 # 印だけの段落は、見出しに置き換える
        i += 1


def apply(md):
    """変換器 md に、脚注・Qiita の注釈ブロック・GitHub のアラートを足す。"""
    from mdit_py_plugins.container import container_plugin
    from mdit_py_plugins.footnote import footnote_plugin

    md.use(footnote_plugin)
    md.add_render_rule("footnote_caption", _footnote_caption)
    md.use(container_plugin, name="note", validate=_validate_note, render=_render_note)
    md.core.ruler.push("github_alerts", _alerts)


# ---- コードブロックの情報行（```ruby:app.rb、```diff_ruby）
def split_info(info):
    """情報行を (言語, ファイル名, 差分か) に分ける。```ruby:app.rb → ('ruby', 'app.rb', False)、```diff_ruby → ('diff', '', True)。

    ファイル名は、最初の語の `:` のあと。`{.python}` や ```python title="a.py" のような書き方には触れない。
    """
    words = (info or "").strip().split(None, 1)
    if not words:
        return "", "", False
    first = words[0]
    name = ""
    if ":" in first and not first.startswith(("{", ".")):
        first, _, name = first.partition(":")
        if not first or not name:                    # `:` だけ・片方が空の書き方は、そのまま（言語として読まない）
            first, name = words[0], ""
    lang = first.strip("{}").lstrip(".").lower()
    diff = False
    if lang.startswith("diff_") and len(lang) > 5:
        lang, diff = "diff", True
    return lang, name, diff


def filename_html(info):
    """ファイル名がある情報行なら、コードブロックの上に出す見出しの HTML。なければ空。"""
    name = split_info(info)[1]
    return f'<div class="code-filename">{escape(name, quote=False)}</div>\n' if name else ""

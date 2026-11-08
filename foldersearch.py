"""フォルダー全体の検索（本文の検索）。フォルダーの中の Markdown ファイルを、まとめて探し、一致した行を返す。ビューアとエディタで、同じ内容。

- 文字列（既定）か、正規表現で探す。大文字小文字を区別するかは、選べる。**1行ずつ**探す（行をまたぐ一致は、探さない）。
- 1行に何か所一致しても、結果は、その行の最初の一致の1件。ファイルごとの件数は、一致した行の数。
- 結果は、一致の前後（context 文字）を切り出した文字列と、その中の一致の範囲、元の行の中の位置（行・桁・長さ）。
- 巨大なファイル・巨大な行・長い時間で、固まらないよう、上限がある（超えたら、そこまでの結果を返し、truncated で知らせる）。
- ファイルの一覧と、読み込みの関数は、呼ぶ側から渡す（ビューアとエディタで、文字コードの扱いが違うため）。画面に依存しない。
"""
import os
import re
import time

MAX_HITS = 500              # 返す一致の上限（行の数）
PER_FILE = 100              # 1ファイルで返す一致の上限
MAX_BYTES = 2_000_000       # これより大きなファイルは、探さない
MAX_LINE = 2000             # 1行のうち、探す長さの上限（正規表現が、長い行で、固まらないように）
SECONDS = 10                # 探す時間の上限（秒）
CONTEXT = 40                # 一致の前後に残す文字数


def _compile(query, case, regex):
    flags = 0 if case else re.IGNORECASE
    try:
        return re.compile(query if regex else re.escape(query), flags), None
    except re.error as e:
        return None, "正規表現が正しくありません: %s" % e


def _snippet(line, start, end):
    a, b = max(0, start - CONTEXT), min(len(line), end + CONTEXT)
    lead = "…" if a > 0 else ""
    text = lead + line[a:b] + ("…" if b < len(line) else "")
    return text, len(lead) + (start - a), len(lead) + (end - a)


def search(folder, files, query, case=False, regex=False, read=None, overrides=None, cancelled=None,
           max_hits=MAX_HITS, per_file=PER_FILE, max_bytes=MAX_BYTES, seconds=SECONDS):
    """files: フォルダーからの相対パス（/ 区切り）の並び。read(パス) → 本文（読めなければ None）。
    overrides: {正規化した絶対パス: 本文}（保存していない編集中の内容を、ディスクの内容の代わりに使う）。
    返す: {"results": [{"rel", "count", "hits": [{"line", "col", "len", "text", "s", "e"}]}], "total", "files", "scanned",
           "skipped", "truncated", "reason", "error"}。line は 0 から数える。"""
    out = {"results": [], "total": 0, "files": 0, "scanned": 0, "skipped": 0, "truncated": False, "reason": "", "error": None}
    if not query:
        return out
    pattern, error = _compile(query, case, regex)
    if error:
        out["error"] = error
        return out
    overrides = overrides or {}
    deadline = time.monotonic() + seconds

    def stop(reason):
        out["truncated"], out["reason"] = True, reason

    for rel in files:
        if cancelled and cancelled():
            stop("検索を取りやめました")
            return out
        if time.monotonic() > deadline:
            stop("時間の上限（%d 秒）に達したので、途中までの結果です" % seconds)
            return out
        path = os.path.join(folder, *rel.split("/"))
        key = os.path.normcase(os.path.abspath(path))
        if key in overrides:
            text = overrides[key]
        else:
            try:
                if os.path.getsize(path) > max_bytes:
                    out["skipped"] += 1
                    continue
                text = read(path)
            except OSError:
                out["skipped"] += 1
                continue
        if text is None:
            out["skipped"] += 1
            continue
        out["scanned"] += 1
        hits, count = [], 0
        for number, line in enumerate(text.split("\n")):
            if number % 4000 == 3999 and time.monotonic() > deadline:
                stop("時間の上限（%d 秒）に達したので、途中までの結果です" % seconds)
                break
            if line.endswith("\r"):
                line = line[:-1]
            for m in pattern.finditer(line[:MAX_LINE]):
                if m.end() == m.start():
                    continue                                     # 空の一致（`a*` など）は、数えない
                count += 1
                if len(hits) < per_file:
                    snippet, s, e = _snippet(line, m.start(), m.end())
                    hits.append({"line": number, "col": m.start(), "len": m.end() - m.start(), "text": snippet, "s": s, "e": e})
                break                                            # 1行につき、1件
        if count:
            out["results"].append({"rel": rel, "count": count, "hits": hits})
            out["files"] += 1
            out["total"] += count
            if out["total"] >= max_hits:
                stop("一致が %d 件に達したので、途中までの結果です" % max_hits)
                return out
        if out["truncated"]:
            return out
    return out

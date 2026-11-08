"""画面テストで、OS のダイアログ（フォルダー選択・ファイル選択・保存先の選択）を、実際には出さない。

実際に出ると、テストが終わるまで画面に残り、利用者が使っている他のアプリのキー入力を奪う
（2026-11-08、利用者の指摘。ビューアは、引数なしで起動するとフォルダー選択を開く）。
import するだけで、`dialogs.pick_*` が「選ばなかった（None）」を返す関数に差し替わる。

画面テストの先頭（`import mdviewer` / `import mdeditor` の次の行）で、`import gui_nodialog` する。
"""
import dialogs

for _name in dir(dialogs):
    if _name.startswith("pick_"):
        setattr(dialogs, _name, lambda *a, **k: None)

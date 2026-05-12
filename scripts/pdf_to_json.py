#!/usr/bin/env python3
"""
pdf_to_json.py — 保育士試験 PDF → JSON 変換スクリプト
======================================================

■ 使い方
  1. PDFファイルを ../pdfs/ フォルダに入れる
     ファイル名の形式: <年度>_<科目>.pdf
     例: R05前期_教育原理.pdf  /  R06後期_保育原理.pdf

  2. 依存パッケージをインストール
     pip install pdfplumber

  3. スクリプトを実行
     cd scripts
     python3 pdf_to_json.py

  4. ../data/ フォルダに JSON ファイルが出力されます
     また ../data/index.json が自動更新されます

■ PDFの対応フォーマット
  以下のいずれかの形式の問題に対応しています。

  [形式A] 問題番号 + 問題文 + 選択肢①〜⑤
    問題1
    次の文について…
    ① 選択肢A
    ② 選択肢B
    …

  [形式B] 「問」から始まる形式
    問1 次の記述として正しいものはどれか。
    A テキスト
    B テキスト
    …

  ※ 正解・解説はPDFに含まれていない場合、空欄になります。
     出力されたJSONを手動で編集して正解(answer)と解説(explanation)を追加してください。
"""

import json
import os
import re
import sys
from pathlib import Path

try:
    import pdfplumber
except ImportError:
    print("pdfplumber が見つかりません。以下を実行してください:")
    print("  pip install pdfplumber")
    sys.exit(1)

# ── Paths ─────────────────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).parent
ROOT_DIR   = SCRIPT_DIR.parent
PDF_DIR    = ROOT_DIR / "pdfs"
DATA_DIR   = ROOT_DIR / "data"
INDEX_FILE = DATA_DIR / "index.json"

# ── Helpers ───────────────────────────────────────────────────────────────
CIRCLE_NUMS = {'①':0,'②':1,'③':2,'④':3,'⑤':4,'⑥':5}
ALPHA_OPTS  = {'A':0,'B':1,'C':2,'D':3,'E':4,'F':5}

def extract_text_from_pdf(pdf_path: Path) -> str:
    """PDFから全テキストを抽出する"""
    text = ""
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            t = page.extract_text()
            if t:
                text += t + "\n"
    return text

def parse_questions_style_a(text: str) -> list[dict]:
    """
    形式A: 丸数字（①②③…）の選択肢
    「問題N」または「問N」または数字だけの行から始まる問題
    """
    questions = []
    # 問題を区切るパターン
    blocks = re.split(r'\n(?=問題\s*\d+|問\s*\d+)', text)

    for block in blocks:
        lines = [l.strip() for l in block.strip().splitlines() if l.strip()]
        if not lines:
            continue

        # 最初の行から問題番号を除去して問題文を取得
        q_text = re.sub(r'^(?:問題|問)\s*\d+\s*', '', lines[0]).strip()
        # 後続行が選択肢でない場合、問題文に追加
        options = {}
        extra_q = []
        for line in lines[1:]:
            m = re.match(r'^([①②③④⑤⑥])\s+(.*)', line)
            if m:
                options[CIRCLE_NUMS[m.group(1)]] = m.group(2).strip()
            else:
                if not options:
                    extra_q.append(line)

        if extra_q:
            q_text = q_text + ' ' + ' '.join(extra_q)

        if not q_text or len(options) < 2:
            continue

        opts_list = [options.get(i, '') for i in range(len(options))]

        questions.append({
            "id":          len(questions) + 1,
            "question":    q_text,
            "options":     opts_list,
            "answer":      0,        # ← 要手動修正
            "explanation": ""        # ← 要手動追記
        })

    return questions

def parse_questions_style_b(text: str) -> list[dict]:
    """
    形式B: アルファベット（A B C D E）の選択肢
    """
    questions = []
    # 問題を区切るパターン
    blocks = re.split(r'\n(?=問\s*\d+)', text)

    for block in blocks:
        lines = [l.strip() for l in block.strip().splitlines() if l.strip()]
        if not lines:
            continue

        q_text = re.sub(r'^問\s*\d+\s*', '', lines[0]).strip()
        options = {}
        extra_q = []
        for line in lines[1:]:
            m = re.match(r'^([ABCDEF])\s+(.*)', line)
            if m and m.group(1) in ALPHA_OPTS:
                options[ALPHA_OPTS[m.group(1)]] = m.group(2).strip()
            else:
                if not options:
                    extra_q.append(line)

        if extra_q:
            q_text = q_text + ' ' + ' '.join(extra_q)

        if not q_text or len(options) < 2:
            continue

        opts_list = [options.get(i, '') for i in range(len(options))]

        questions.append({
            "id":          len(questions) + 1,
            "question":    q_text,
            "options":     opts_list,
            "answer":      0,        # ← 要手動修正
            "explanation": ""        # ← 要手動追記
        })

    return questions

def parse_filename(filename: str) -> tuple[str, str]:
    """
    ファイル名から年度と科目を抽出する
    例: "R05前期_教育原理.pdf" → ("R05前期", "教育原理")
         "令和5年後期_保育原理.pdf" → ("令和5年後期", "保育原理")
         "教育原理.pdf" → ("不明", "教育原理")
    """
    stem = Path(filename).stem
    if '_' in stem:
        parts = stem.split('_', 1)
        return parts[0].strip(), parts[1].strip()
    else:
        return "不明", stem.strip()

def load_index() -> dict:
    if INDEX_FILE.exists():
        with open(INDEX_FILE, encoding='utf-8') as f:
            return json.load(f)
    return {"datasets": []}

def save_index(index_data: dict):
    DATA_DIR.mkdir(exist_ok=True)
    with open(INDEX_FILE, 'w', encoding='utf-8') as f:
        json.dump(index_data, f, ensure_ascii=False, indent=2)

def process_pdf(pdf_path: Path) -> int:
    """PDFを処理してJSONを出力。追加した問題数を返す。"""
    year, subject = parse_filename(pdf_path.name)
    print(f"\n処理中: {pdf_path.name}")
    print(f"  年度: {year}　科目: {subject}")

    text = extract_text_from_pdf(pdf_path)

    # 丸数字が多ければ形式A、アルファベットが多ければ形式B
    count_circle = sum(text.count(c) for c in CIRCLE_NUMS)
    count_alpha  = sum(len(re.findall(rf'\n{c}\s', text)) for c in 'ABCDE')

    if count_circle >= count_alpha:
        questions = parse_questions_style_a(text)
        style = "A（丸数字）"
    else:
        questions = parse_questions_style_b(text)
        style = "B（アルファベット）"

    print(f"  解析形式: {style}　検出問題数: {len(questions)}")

    if not questions:
        print("  ⚠️  問題が検出できませんでした。PDFの形式を確認してください。")
        return 0

    # JSON出力
    out_data = {
        "meta": {
            "year":    year,
            "subject": subject,
            "source":  f"保育士試験 {year} {subject}",
            "notes":   "answer(正解番号 0始まり)とexplanation(解説)は手動で追記してください"
        },
        "questions": questions
    }

    safe_name = f"{subject}_{year}.json"
    out_path  = DATA_DIR / safe_name
    DATA_DIR.mkdir(exist_ok=True)
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(out_data, f, ensure_ascii=False, indent=2)
    print(f"  ✅ 出力: data/{safe_name}")

    # index.json を更新
    index = load_index()
    entry_id = f"{subject}_{year}"
    # 同じ id が既にあれば更新、なければ追加
    existing = next((d for d in index["datasets"] if d["id"] == entry_id), None)
    new_entry = {
        "id":            entry_id,
        "year":          year,
        "subject":       subject,
        "file":          f"data/{safe_name}",
        "questionCount": len(questions)
    }
    if existing:
        index["datasets"][index["datasets"].index(existing)] = new_entry
    else:
        index["datasets"].append(new_entry)
    save_index(index)

    return len(questions)

# ── Main ──────────────────────────────────────────────────────────────────
def main():
    PDF_DIR.mkdir(exist_ok=True)

    pdfs = sorted(PDF_DIR.glob("*.pdf"))
    if not pdfs:
        print(f"PDFファイルが見つかりません: {PDF_DIR}")
        print("pdfs/ フォルダにPDFを置いてから再実行してください。")
        print("ファイル名の形式: <年度>_<科目>.pdf")
        print("例: R05前期_教育原理.pdf")
        return

    total = 0
    for pdf in pdfs:
        total += process_pdf(pdf)

    print(f"\n{'='*50}")
    print(f"完了！　合計 {total} 問を JSON に変換しました。")
    print()
    print("⚠️  重要: 各JSONファイルの answer（正解の選択肢番号、0始まり）と")
    print("   explanation（解説文）を手動で修正・追記してください。")
    print()
    print("JSONファイルの場所: data/")
    print("index.jsonも自動更新されました。")

if __name__ == "__main__":
    main()

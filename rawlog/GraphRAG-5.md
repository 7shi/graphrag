# GraphRAGにおける名詞句抽出（extractor_type）と spaCy の動作仕様まとめ

本ドキュメントは、GraphRAG の NLP ベースのグラフ構築（FastGraphRAG）における `extractor_type` の設定、spaCy の使用箇所、日本語サポート状況、エラー時の挙動、および LLM ベース方式との精度比較に関する議論をまとめたものです。

---

## 1. インデックス作成方式の指定方法と spaCy の有効化
GraphRAG で spaCy などの NLP モジュールを使用するためには、まずインデックス作成方式（`method`）を **`fast` (FastGraphRAG)** に指定する必要があります。

> [!IMPORTANT]
> **このインデックス作成方式を明示的に指定しない場合、デフォルト値である `standard`（LLMベース）が適用され、`extractor_type` などの設定はすべて無視されて spaCy は一切使用されません。**

### インデックス作成方式の指定方法
インデックス作成方式（`method`）は設定ファイル（`settings.yaml`）ではなく、実行時にコマンドライン（CLI）または API を介して直接指定します。

#### A. コマンドライン（CLI）での指定
`graphrag index` コマンド実行時に `--method`（あるいは `-m`）オプションを渡します。
* **標準方式 (Standard) - デフォルト (spaCy は使用されません)**
  ```bash
  graphrag index --root ./project --method standard
  ```
  *(省略した場合は自動的に standard になります)*
* **高速方式 (Fast) - NLPベース (spaCy を使用します)**
  ```bash
  graphrag index --root ./project --method fast
  ```

#### B. Python API での指定
[graphrag.api.index.build_index](file:///home/7shi/repos/graphrag/packages/graphrag/graphrag/api/index.py#L30-L37) を呼び出す際、`method` 引数を渡します。
```python
await build_index(config=config, method="fast") # または IndexingMethod.Fast
```

### 指定可能な値
* `standard`: 標準の LLM ベースでの完全なグラフ構築と要約（デフォルト）。
* `fast`: spaCy などのローカル NLP を用いた高速グラフ構築と、LLM による要約。
* `standard-update`: `standard` 方式による既存インデックスの差分更新。
* `fast-update`: `fast` 方式による既存インデックスの差分更新。

---

## 2. `extractor_type` とは何か？
`extractor_type` は、NLP ベースのグラフ構築（`extract_graph_nlp` ワークフロー）において、入力テキストから名詞句（Noun Phrase）を抽出する抽出器（Extractor）の種類を指定するパラメーターです。設定ファイル `settings.yaml` の `extract_graph_nlp.text_analyzer` ブロックで指定します。

### 指定できるパラメーターとその意味
[NounPhraseExtractorType](file:///home/7shi/repos/graphrag/packages/graphrag/graphrag/config/enums.py#L57-L66) に定義されている以下の3つのいずれかを指定できます。

1. **`regex_english`** (デフォルト)
   * **クラス**: [RegexENNounPhraseExtractor](file:///home/7shi/repos/graphrag/packages/graphrag/graphrag/index/operations/build_noun_graph/np_extractors/regex_extractor.py)
   * **動作**: NLTK と TextBlob の機能を利用した、英語専用の正規表現ベースの抽出器。
   * **特徴**: 非常に高速ですが、**英語限定**であり、構文解析を行う方式に比べて抽出精度は劣る場合があります。
2. **`syntactic_parser`**
   * **クラス**: [SyntacticNounPhraseExtractor](file:///home/7shi/repos/graphrag/packages/graphrag/graphrag/index/operations/build_noun_graph/np_extractors/syntactic_parsing_extractor.py)
   * **動作**: spaCy の構文解析（Dependency Parsing）と固有表現認識（NER）を用いた抽出器。
   * **特徴**: テキストの文法構造を解析するため**抽出精度が高く、多言語（日本語含む）に対応可能**ですが、処理速度は遅くなります。
3. **`cfg`**
   * **クラス**: [CFGNounPhraseExtractor](file:///home/7shi/repos/graphrag/packages/graphrag/graphrag/index/operations/build_noun_graph/np_extractors/cfg_extractor.py)
   * **動作**: spaCy を用いた簡易的な品詞（POS）タグの判定と、事前に定義した文脈自由文法（Context-Free Grammar）の遷移ルールを組み合わせた抽出器。
   * **特徴**: 構文解析（Parser）を行わないため `syntactic_parser` より高速ですが、言語ごとに適切な文法ルール（`noun_phrase_grammars`）を個別に設計する必要があります。

---

## 3. spaCy はコードのどこで使用されているか？
spaCy は、FastGraphRAG の名詞句抽出処理において、主に以下の3つのファイルで使用されています。

* **モデルのロードと自動ダウンロード**
  * [base.py](file:///home/7shi/repos/graphrag/packages/graphrag/graphrag/index/operations/build_noun_graph/np_extractors/base.py#L47-L61)
  * `spacy.load` を用いて言語モデルをロードします。モデルが未インストールの場合は、`spacy.cli.download` を用いて自動的にダウンロードを行います。
* **構文解析に基づく抽出**
  * [syntactic_parsing_extractor.py](file:///home/7shi/repos/graphrag/packages/graphrag/graphrag/index/operations/build_noun_graph/np_extractors/syntactic_parsing_extractor.py)
  * `spacy.tokens.span.Span` や `spacy.util.filter_spans` を使用し、文脈からの固有表現（`doc.ents`）や名詞チャンク（`doc.noun_chunks`）をマージ・選別します。
* **文法ルール（CFG）に基づく抽出**
  * [cfg_extractor.py](file:///home/7shi/repos/graphrag/packages/graphrag/graphrag/index/operations/build_noun_graph/np_extractors/cfg_extractor.py)
  * 処理高速化のために parser を無効化したモデルをロードし、各トークンの品詞情報 `token.pos_` を参照して、文法ルールに沿ったマージを行います。

---

## 4. 言語サポートと日本語の扱い

### デフォルトの設定は「英語専用」
[defaults.py](file:///home/7shi/repos/graphrag/packages/graphrag/graphrag/config/defaults.py#L156-L181) における初期値は、以下のように英語を対象として定義されています。
* **モデル名**: `en_core_web_md` (英語モデル)
* **除外名詞**: `EN_STOP_WORDS` (英語用ストップワード)
* **CFG文法**: `"ADJ,NOUN"` (形容詞+名詞) など、英語の語順を前提とした品詞結合ルール

### 日本語を扱う方法
日本語で FastGraphRAG を動かすためには、以下の設定調整が必要です。

1. **日本語モデルのインストール**
   ```bash
   python -m spacy download ja_core_news_md
   ```
2. **`settings.yaml` の変更**
   `extractor_type` を `syntactic_parser` に変更し、日本語用のモデル名を指定します。
   ```yaml
   extract_graph_nlp:
     text_analyzer:
       extractor_type: syntactic_parser
       model_name: ja_core_news_md
       exclude_nouns: ["これ", "それ", "あれ", "もの", "こと"] # 日本語用ストップワードの指定を推奨
   ```

---

## 5. 各種設定の挙動と注意点

### `model_name` を省略した場合
* 設定上のデフォルト値である **`"en_core_web_md"`（英語モデル）** が適用されます。
* 実行環境にモデルがない場合は、自動ダウンロードが走ります。
* 日本語ドキュメントに対して実行した場合、英語用のルールで無理やり解析しようとするため、日本語の名詞句を切り出すことができず、**最終的に抽出結果が 0 件となりエラー終了します。**

### `prompt-tune` との関係性
* `prompt-tune`（プロンプト自動調整機能）のコードベースには、**spaCy に対する依存関係は一切ありません。**
* `prompt-tune` は、入力ドキュメントのドメインや言語の判定に LLM 自体を使用するのに対し、spaCy はローカルでの非 LLM ベースの高速インデックス作成（FastGraphRAG）で使用されるため、両者は完全に独立しています。

---

## 6. エラー発生時の挙動（フォールバックの有無）
FastGraphRAG（`extract_graph_nlp`）の実行時に、spaCy が利用できない（モジュール未検出、モデルのロード失敗など）場合や、解析した結果の抽出ノード数が 0 件だった場合、**LLM への自動フォールバックは発生しません。**

* [extract_graph_nlp.py](file:///home/7shi/repos/graphrag/packages/graphrag/graphrag/index/workflows/extract_graph_nlp.py#L77-L82) で実装されている通り、例外（`ValueError`）が送出され、インデックス作成プロセス自体がその時点で**異常終了（クラッシュ）**します。

---

## 7. インデックス作成方式による精度・コスト比較
LLM を使用する `standard` 方式と、spaCy を使用する `fast` 方式には、以下のような明確なトレードオフがあります。

| 比較項目 | `standard` (LLMベース) | `fast` (NLP/spaCyベース) |
| :--- | :--- | :--- |
| **抽出の精度** | **非常に高い**<br>文脈を理解して無駄な名詞を省き、表記揺れをマージする。 | **低〜中（粗い）**<br>機械的な抽出のため、文脈に関係のないノイズ名詞が多く混ざる。 |
| **説明文（description）** | **詳細**<br>ノードやエッジに対し、LLM が文脈に沿った説明文を生成する。 | **空白または簡易的** |
| **APIコスト（費用）** | **高い**<br>大量の LLM API 呼び出しを行うため、トークン消費量が多い。 | **極めて低い**<br>ローカル CPU で処理し、コミュニティ要約時のみ LLM を使用する。 |
| **処理速度** | **遅い** | **非常に高速** |
| **向いている用途** | 本番環境、高い検索・要約精度が求められる場合。 | 初期検証、データ構造 of 可視化テスト、低予算での検証。 |

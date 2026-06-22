# main ↔ feature/llm-rawlog 差分の要約

`git diff main HEAD` のうち、`rawlog/`（ドキュメント・分析ツール）・`ENTITY_RELATIONSHIP.md`・
`uv.lock` を除いた **13 ファイル（+385 / −201）** をファイル単位でレビューした要約。
変更は **(A) rawlog 機能の追加** と **(B) グラフ抽出の構造化出力（JSON）移行** の 2 系統。
詳細な設計判断は [`ENTITY_RELATIONSHIP.md`](ENTITY_RELATIONSHIP.md) を参照。

## 経緯（なぜこの 2 系統が 1 ブランチに入っているか）

この 2 系統は別々の目的ではなく、**A が本来の目的、B はその過程で判明した問題への派生対応**という
時系列でつながっている。

1. **本来の目的は A（rawlog）**。[`README.md`](README.md) の解説記事（GraphRAG-A/B.md）を書くための
   **調査用フック**として、LLM とのやり取りを XML に記録する rawlog 機能を入れた。当初の計画では
   **ここで止める**つもりだった（ドキュメント化が完了すれば役目を終える）。
2. ところが rawlog で実際のやり取りを観察した結果、**ローカルの Gemma 4 がタプル区切り
   （`<|>` / `##`）の出力フォーマットを安定して守れない**ことが判明した。書式崩れでレコードが
   silently drop され、特に relationship の生存率が著しく低かった（非 tune で約 10%）。
3. この書式由来の脱落を根絶するため、**グラフ抽出を構造化出力（JSON / `response_format`）へ移行**する
   修正（B）を追加した。当初の予定にはなかったが、rawlog の調査が直接の動機になっている。

つまり **A が無ければ B の問題には気付けず、B は A の発見に対する手当て**である。両者は
「調査 → 発見 → 対処」という一連の流れとして同一ブランチ（`feature/llm-rawlog`）に同居している。

## A. rawlog 機能（LLM 生ログの XML 出力）

### `packages/graphrag-llm/graphrag_llm/completion/rawlog_helper.py`（新規 +123）

- LLM へ渡した messages と応答を `messages`/`message` 要素の CDATA に入れた XML として書き出す。
- 出力先は環境変数 `GRAPHRAG_RAWLOG_DIR`（既定 `rawlogs`）。`NNNNN.xml`（5 桁連番）で採番。
- `threading.Lock` ＋グローバルカウンタで採番・書き込みを直列化し、並行実行の競合を防ぐ。
- `_wrap_response` / `_wrap_response_async`: 非ストリームは即記録、ストリームはチャンクを
   yield しつつ蓄積し、消費完了後に結合して記録する（同期・非同期の両ラッパを用意）。
- CDATA 内の `]]>` を `]] >` に退避するエスケープ、テキストの前後改行整形を行う。
- 全体を `try/except: pass` で囲み、**ログ失敗が本処理をクラッシュさせない**設計。

### `packages/graphrag-llm/graphrag_llm/completion/lite_llm_completion.py`（+9 −2）

- `rawlog_helper` の 2 ラッパを import。
- 同期 `completion` / 非同期 `completion_async` の戻り値を、それぞれ `_wrap_response` /
  `_wrap_response_async` で包んでから返すよう 2 箇所を差し替え（記録フックの注入のみ）。

### `packages/graphrag/graphrag/cli/main.py`（+1）

- typer アプリに `pretty_exceptions_enable=False` を追加。例外の整形を抑止し、生のトレース
  バックを出す（rawlog 解析時のデバッグ性向上）。

## B. グラフ抽出の構造化出力（JSON）移行

### `packages/graphrag/graphrag/index/operations/extract_graph/graph_extractor.py`（+155 −…）

本系統の中核。タプル区切りパースを廃し、Pydantic スキーマによる構造化出力へ全面移行。

- 旧定数 `TUPLE_DELIMITER`(`<|>`) / `RECORD_DELIMITER`(`##`) / `COMPLETION_DELIMITER` と
  `import re` を削除。
- `EntityModel` / `RelationshipModel` / `GraphExtractionResult`（Pydantic）を追加。
  `strength` は `default=1.0`（旧パーサのフォールバック重みを踏襲、スコア欠落でも検証が通る）。
- `_process_document`:
  - プロンプト埋め込みを `str.format` → **`str.replace`** に変更（`{entity_types}`/`{input_text}`
    のみ置換）。JSON 例の波括弧が `format` の placeholder と衝突する問題を回避。
  - `completion_async(..., response_format=GraphExtractionResult)` を呼び、
    `response.formatted_response` を読む。**gleaning も構造化呼び出し**にし、各ラウンドの
    `entities`/`relationships` を `extend` で統合。継続判定（`LOOP_PROMPT`）は素のまま。
- `_process_result`: 文字列パースを廃止し、構造化結果から直接 DataFrame を構築。
  `clean_str`＋大文字化に加え、`(title, type)` / `(source, target)` での重複排除を追加。

### `packages/graphrag/graphrag/prompts/index/extract_graph.py`（+91 −…）

- index エンジンが実際に使う `GRAPH_EXTRACTION_PROMPT` を JSON 出力指示へ書き換え。
- フィールド名を `entity_name`→`name`、`relationship`→`description`、
  `relationship_strength`→`strength` 等に整理し、`<|>`/`##`/`<|COMPLETE|>` の指示を削除。
- 3 つの few-shot 例（Central Institution / TechGlobal / Aurelia）を
  `{"entities":[...],"relationships":[...]}` の単一 JSON オブジェクトへ書き換え。
- 例中の JSON は**単一波括弧**（`str.replace` 前提なのでエスケープ不要）。
- `CONTINUE_PROMPT` を「同じ JSON 形式で追加せよ」と JSON 文面へ更新。

### prompt-tune 側（生成プロンプトを構造化出力スキーマに合わせる）

- `api/prompt_tune.py`（+2 −2）: `generate_entity_relationship_examples` と
  `create_extract_graph_prompt` の `json_mode` を **`False`→`True`** に変更
  （index が構造化出力で抽出するため、tune 生成プロンプトも JSON スキーマに揃える）。
- `prompt_tune/prompt/entity_relationship.py`（+94 −…）:
  typed 版 `ENTITY_RELATIONSHIPS_GENERATION_PROMPT` の JSON 例を単一オブジェクト形へ更新し、
  **untyped 版の JSON プロンプト `UNTYPED_..._JSON_PROMPT` を新規追加**。
- `prompt_tune/template/extract_graph.py`（+51 −…）:
  同様に typed テンプレートを更新し、**`UNTYPED_GRAPH_EXTRACTION_JSON_PROMPT` を新規追加**。
- `prompt_tune/generator/entity_relationship.py`（+9）/
  `prompt_tune/generator/extract_graph_prompt.py`（+7）:
  `json_mode` が真かつ untyped のとき、新設の JSON プロンプトを選ぶ分岐を追加。
- フィールド名は本体プロンプトと一致（`relationship`/`relationship_strength`→`description`/`strength`）。

### `tests/.../graph_intelligence/test_gi_entity_extraction.py`（+20 −…）

- モック応答 `SIMPLE_EXTRACTION_RESPONSE` をタプル形式から
  `{"entities":[...],"relationships":[...]}` の JSON へ変換（新パーサに合わせる）。

## C. その他（ビルド・依存・除外設定）

### `pyproject.toml`（+17 −…）

- ルートに `dependencies = ["graphrag", "llm7shi"]` を追加。
  `[tool.uv.sources]` に `graphrag = { workspace = true }` と
  `llm7shi = { git = "https://github.com/7shi/llm7shi.git" }` を追加。
- poe タスク `rawlog_fields` / `rawlog_log` / `rawlog_show`（`rawlog/` の解析ツール）を追加。
- dev 依存の pytest 系を `~=`（互換リリース固定）→ `>=`（下限のみ）へ緩和。

### `.gitignore`（+5 −1）

- 末尾 EOL を補正し、`# rawlog outputs` として `graphrag_quickstart/` を無視に追加。

## レビュー所見

- **整合性**: 本体プロンプト・prompt-tune・テスト・パーサが同一 JSON スキーマ
  （`entities`/`relationships`、`name/type/description`、`source/target/description/strength`）で
  一致しており、`ENTITY_RELATIONSHIP.md` の記述とも整合。
- **後方互換**: 旧タプル系テンプレート（`GRAPH_EXTRACTION_PROMPT` 等の非 JSON 版）は
  prompt-tune モジュールに残置され、既定フローからは未使用。公開 API は不変。
- **堅牢性**: rawlog は例外握り潰し＋ロックで本処理に副作用を与えない。`strength` の
  デフォルトと重複排除で、スコア欠落・重複レコードによる脱落／二重計上を抑止。
- **留意**: rawlog は `try/except: pass` のため**書き込み失敗が無言で握り潰される**（設計上
  許容だが、デバッグ時は注意）。`pretty_exceptions_enable=False` は CLI のエラー表示を変える。

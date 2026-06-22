# tagore — 構造化出力による抽出の動作確認

`rawlog/` の調査で **ローカル Gemma 4 がタプル区切り（`<|>`）の出力フォーマットを守れず**、
relationship が silently drop されることが判明した。その手当てとしてグラフ抽出を**構造化出力
（JSON）へ移行**し（[`ENTITY_RELATIONSHIP.md`](ENTITY_RELATIONSHIP.md) / [`DIFF.md`](DIFF.md)）、
実テキストでの動作を end-to-end に検証した。本ドキュメントはその**最終結果**を要約する。

題材・質問・模範解答はリポジトリ [7shi/bou-thakuranir_haat](https://github.com/7shi/bou-thakuranir_haat) で公開されている。

- **テキスト**: Rabindranath Tagore『Bou-Thakuranir Haat』英訳（全 37 章、text_units 66）—
  [`all/en-gemini.md`](https://github.com/7shi/bou-thakuranir_haat/blob/main/all/en-gemini.md)
- **質問・模範解答**: 50 問（`single`/`cross` ≈ Local/Global 対応）—
  [`questions-en.jsonl`](https://github.com/7shi/bou-thakuranir_haat/blob/main/questions-en.jsonl)

## 条件
- **抽出**: prompt-tune（`--discover-entity-types`）＋**構造化出力**。LLM は Ollama `gemma4:26b`
  （`reasoning_effort: none`）、埋め込み `embeddinggemma`、`concurrent_requests: 1`（逐次実行）。
- 全 50 問を Local / Global で回答収集し、引用タグを章へ展開して模範解答と突き合わせた。

## index 結果

| 指標 | 値 |
| --- | --- |
| entities | 244 |
| relationships | 237 |
| communities / reports | 22 / 22 |
| entity description 空率 | **0%** |
| relationship description 空率 | **0%** |
| エラー / タイムアウト | **0 / 0** |

- **構造化出力が書式由来の脱落をデコーダ側で根絶**した。`response_format`（grammar-constrained
  decoding）により `<|>` 崩れも strength 欄の貼り付けも起こり得ず、タプル時代に silently drop して
  いた relationship が落ちずに残る（relationships 237・communities 22 と密なグラフが得られた）。
- **description 空率 0%**（entity・relationship とも）。構造化出力に加え、プロンプト埋め込みを
  `str.format`→`str.replace` にした（JSON の波括弧と placeholder の衝突回避）ことで保証される。
- index・query を通じてエラー／タイムアウト 0 件で end-to-end 完走。
- prompt-tune が discover した entity type は 8 種（PERSON / LOCATION / ROLE / OBJECT / RELIGION /
  SOCIAL CLASS / TITLE / MILITARY RANK）。

## query 結果

- Local 50 / Global 50 をすべて取得（空出力・WARN なし）。`local.jsonl`(50) / `global.jsonl`(50) を生成。
- 章番号への展開は **Local が 50/50 で空 0**、Global は 40/50 が空。Local は `[Data: Sources]`
  （text_unit）を豊富に引用して章へ展開でき、Global の引用はすべて `[Data: Reports]`
  （コミュニティ単位）で Sources を含まないため章展開が空になる（仕様どおりの分岐）。

| 指標 | Local | Global |
| --- | --- | --- |
| 引用タグを含む回答 | 50 / 50 | 10 / 50 |
| 実質的に内容を述べた回答 | 34 / 50 | 9 / 50 |

## QA レベルの動作確認（代表 5 問）

各問の rawlog で「正解の一節がコンテキストに入っていたか（＝検索／構造の成否）」と「入っていた
とき正しく扱えたか（＝LLM の成否）」を確認した。

| 問 | type / 正解章 | 結果 | 要因 |
| --- | --- | --- | --- |
| Q2 | single / 4 | 成功 | 構造○ LLM○ |
| Q3 | single / 8 | **棄権** | 核心 `diamond`/`thick` が未取り込み（検索リコール限界） |
| Q5 | single / 21 | 成功 | グラフ密化で正解がコンテキストに到達 |
| Q7 | single / 7 | 成功（断定） | 構造○、過剰ヘッジも解消 |
| Q29 | cross / 16,17 | 成功（毒殺を記述） | グラフ密化で因果が到達 |

- 密になった relationship／community が正解チャンクをコンテキストへ運び（Q5・Q29）、コンテキストが
  整うことで LLM の過剰ヘッジも減った（Q7）。**抽出層（グラフ）の忠実度を上げると下流 QA が改善する**
  ことを実証した。
- 唯一の取りこぼし Q3 は、数量・修飾（8 本の太い金の腕輪＋ダイヤ）が型に載らず生チャンクにしか
  残らないため、最下層の検索で拾えなかった。これは抽出層の忠実度では解けない検索リコールの限界。

## まとめ

構造化出力への移行は、**Gemma の書式追従限界に由来する relationship の silent drop を根絶**し、
workaround なしで密なグラフ（rel 237・desc 空 0%・error 0）を得た。その上で QA を底上げし、
**抽出層の忠実度向上が下流 QA に効く**ことを示した。一方で、残る失敗（Q3）は GraphRAG 本来の
検索リコール限界に、Global の弱さは要約方式の天井に由来し、これらは抽出層では解けない。
アーキテクチャ上の含意は [`GRAPHRAG.md`](GRAPHRAG.md) にまとめてある。

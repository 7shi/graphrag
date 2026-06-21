# GraphRAG ハッキングガイド（内部構造とログ解析）

このドキュメントでは、GraphRAG で LLM とのやり取りを記録するための改造手法から、蓄積されたログの分析、そして実際のソースコードとログを突き合わせたプロセス解析まで、GraphRAGの内部動作を深く理解するための開発者向け情報をまとめています。

---

## 1. LLM ログ記録・分析機能の導入

LLM呼び出し（同期 `completion`・非同期 `completion_async`）をフックし、送受信データを自動でXMLファイルに保存する改造の概要と分析ツールについてです。

### 1.1 `lite_llm_completion.py` の改造概要
GraphRAG本体側のコード変更による影響を最小化するため、ログ出力の実処理（文字列整形やファイル書き込み）はすべて別ファイルの `rawlog_helper.py` にカプセル化しました。
これにより、`lite_llm_completion.py` の差分は以下の通り、インポートと return 文のラップだけの極小に抑えられています。

```python:packages/graphrag-llm/graphrag_llm/completion/lite_llm_completion.py
# lite_llm_completion.py への追加フック
from graphrag_llm.completion.rawlog_helper import (
    _wrap_response,
    _wrap_response_async,
)

# 同期呼び出しの return ラップ
return _wrap_response(response, messages, is_streaming)

# 非同期呼び出しの return ラップ
return await _wrap_response_async(response, messages, is_streaming)
```

### 1.2 `rawlogs` の仕様
XMLログはカレントディレクトリの `rawlogs/` 配下に保存されます（環境変数 `GRAPHRAG_RAWLOG_DIR` で変更可）。
スレッドセーフ（排他制御）とメモリ内カウンターによる高速書き込みを実装しており、大量の非同期リクエストでもファイル競合を起こしません。
ログはLLMへのリクエスト履歴（`messages`）をそのままチャット形式で保存し、LLMからの返答も `role="assistant"` として同一階層にマージして記録します。

### 1.3 分析補助ツール
蓄積されたログを効率的に処理・分析するための Python スクリプトです。

* **`analyze_log.py` (LLMを使用)**: XMLファイルに保存された会話コンテキストを復元してローカルLLMに渡し、内容を要約・解説させるスクリプトです（JSONL形式で随時出力・レジューム対応）。
* **`analyze_fields.py` (LLM不要の高速処理)**: レスポンスがJSONであるかをパースし、JSONであればトップレベルのキー（フィールド）を抽出して、同一構造を持つファイルを自動的にグループ化します。

### 1.4 長すぎるエラーメッセージの抑制
ローカルモデル検証時に発生するエラーログ（スタックトレース）が長大になる問題は、CLIフレームワークの `typer` の機能によるものです。
`main.py` にて `app = typer.Typer(..., pretty_exceptions_enable=False)` を追加することで、標準的な短いエラー表示に戻すことができます。

---

## 2. 実行プロセスとソースコード・ログの対応解析

GraphRAG の各実行プロセスにおいて、実際のソースコード（対象コミットID: `6d02c235`）のどこでプロンプトが組み立てられ、LLMがどのような形式でレスポンスを出力しているか（XMLログ解析結果）をセットで解説します。

### 2.1 `1-prompt-tune` (自動プロンプトチューニング)
インデックス作成やクエリ処理用のシステムプロンプトを、テキストデータに合わせて動的に最適化するフェーズです。

#### 00001.xml（ドメイン特定）
引数のテキスト（`docs`）を連結し、`domain.py` 内の `GENERATE_DOMAIN_PROMPT` の `{input_text}` に埋め込んで LLM を呼び出します。
```python:packages/graphrag/graphrag/prompt_tune/generator/domain.py:generate_domain
domain_prompt = GENERATE_DOMAIN_PROMPT.format(input_text=docs_str)
response = await model.completion_async(messages=domain_prompt)
```
入力された小説の抜粋テキストから「文学作品」であると判断しています。
```text:結果
Literature
```

#### 00002.xml（専門家ペルソナの定義）
特定したドメインをタスクに構築し、`GENERATE_PERSONA_PROMPT` の `{sample_task}` に埋め込み、AIの「ペルソナ」を生成させます（`generate_persona` in `persona.py`）。
```text:結果
You are an expert Bibliometric Analyst and Network Scientist. You are skilled at mapping citation networks... in the Literature domain.
```

#### 00003.xml（評価基準の定義）
`domain`、`persona`、`input_text` を `GENERATE_REPORT_RATING_PROMPT` にフォーマットして送信します（`generate_community_report_rating` in `community_report_rating.py`）。
専門家の視点から、テキストデータの重要性を判断するための評価基準（0〜10のスコア）を生成しています。

#### 00004.xml（エンティティ種別の抽出） ※JSON出力
`ENTITY_TYPE_GENERATION_JSON_PROMPT` をユーザープロンプトとし、Pydantic モデルの `EntityTypesResponse` を `response_format` として指定します。
```python:packages/graphrag/graphrag/prompt_tune/generator/entity_types.py:generate_entity_types
response = await model.completion_async(messages=messages, response_format=EntityTypesResponse)
```
物語内の実体のカテゴリ（`entity_types`）を JSON 配列で出力します。
```json:結果
{"entity_types": ["person", "spirit", "location", "food", "object", "family_member", "time", "feeling"]}
```

#### 00005.xml 〜 00009.xml（エンティティ・関係性のFew-Shot抽出）
最大5つのバッチに分割し、`ENTITY_RELATIONSHIPS_GENERATION_PROMPT` を用いて `asyncio.gather` で並列に呼び出します。
```python:packages/graphrag/graphrag/prompt_tune/generator/entity_relationship.py:generate_entity_relationship_examples
history_groups = [history[i:i+batch_size] for i in range(0, len(history), batch_size)]
results = await asyncio.gather(*[...])
```
登場人物、アイテムなどの結びつきを独自のデリミタ `<|>` や `##` を使って抽出する Few-Shot のサンプル（日本語）が生成されます。

#### 00010.xml（最終役割プロンプトの生成）
`domain`、`persona`、`docs` を `GENERATE_COMMUNITY_REPORTER_ROLE_PROMPT` に埋め込み、コミュニティ要約レポートを担当する「コミュニティ・リポーター」の役割を定義させます（`generate_community_reporter_role` in `community_reporter_role.py`）。
```text:結果
You are a Literary Structural Analyst, with expertise in analyzing the themes...
```


### 2.2 `2-index` (インデックス作成 / ナレッジグラフ構築)
テキストからエンティティと関係性を抽出し、重複を統合した後にグラフ構造を検出してコミュニティ要約レポートを作成します。

#### 00002.xml 〜 00081.xml（エンティティ・関係性の抽出）
テキストユニットと `entity_types` を送信します。1回目の抽出後、`_max_gleanings` 回を上限に `CONTINUE_PROMPT` を追加して抽出漏れを防ぐループを回します。
```python:packages/graphrag/graphrag/index/operations/extract_graph/graph_extractor.py:GraphExtractor._process_document
for i in range(self._max_gleanings):
    messages_builder.add_user_message(CONTINUE_PROMPT)
    ...
```
小説本文から、登場人物、場所、出来事の結びつきを検出し抽出します。

#### 00082.xml 〜 00223.xml（エンティティの要約・マージと矛盾解消）
異なるチャンクから抽出された同一エンティティの説明リストを取得し、トークン上限を計算しながら LLM に統合させます（`_summarize_descriptions_with_llm` in `description_summary_extractor.py`）。
断片的な記述を名寄せし、1つの整理された紹介文へと統合します。

#### 00224.xml（構造化コミュニティレポートの生成） ※JSON出力
「コミュニティ」内のエンティティ情報をプロンプトに埋め込み、Pydantic モデル `CommunityReportResponse` を指定して厳密な JSON で出力させます（`CommunityReportsExtractor.__call__` in `community_reports_extractor.py`）。
```json:結果
{
    "title": "エベネザー・スクルージの精神的変容と超自然的ネットワーク",
    "summary": "本コミュニティは、主人公エベネザー・スクルージを中心とした...",
    "findings": [ ... ],
    "rating": 9.5
}
```


### 2.3 `3-global` (Global Searchによる全体質問)
ドキュメント全体を跨ぐマクロな問いに対する質問応答プロセスです（Map-Reduce）。

#### 00001.xml & 00002.xml（要点抽出 Mapステップ） ※JSON出力
コミュニティレポートのサブセットを `map_system_prompt` に埋め込み、返却された JSON から要点と重要度スコアを抽出します（`_map_response_single_batch` in `global_search/search.py`）。
```json:結果
{
    "points": [
        {"description": "主人公エベネザー・スクルージの精神的変容...", "score": 100}
    ]
}
```

#### 00003.xml（回答集約 Reduceステップ）
得られた要点リストを重要度スコアの降順にソートして結合し、`reduce_system_prompt` に埋め込んで最終回答を生成させます（`_reduce_response` in `global_search/search.py`）。
重複排除と論理整合性の調整が行われ、最終的な Markdown 形式のテーマ分析報告書が出力されます。


### 2.4 `4-local` (Local Searchによる個別質問)
特定のエンティティや直接関係する情報を抽出して答えるミクロな問いへの応答です。

#### 00001.xml（ローカルコンテキストからの直接回答）
`LocalContextBuilder` でクエリキーワードに類似するエンティティ、リレーション、コベリエイト、生テキストをコンテキストウィンドウ内に収まるよう収集し、システムプロンプトに埋め込んで一発で回答を生成させます（`LocalSearch.search` in `local_search/search.py`）。
スクルージの性格や周辺人物との関係性が整理され、根拠ID付きの丁寧な解説テキストとして出力されます。


### 2.5 まとめ
XMLログのパースとソースコードを対応させることで、GraphRAGの高度な動作ロジック（チャンキング、抽出・マージ、コミュニティ要約、Map-Reduceやローカル検索のコンテキスト構築）がどのように実装されているかが明確に理解できます。
ログを監視・分析することは、LLMを使ったナレッジグラフ構築の品質をデバッグし、プロンプトを洗練させる上で非常に強力な手段となります。

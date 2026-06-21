# GraphRAG LLM ログ記録・分析機能 活用ガイド

このドキュメントでは、GraphRAG で LLM との生のリクエスト・レスポンスのやり取りを `rawlogs` ディレクトリへ記録するように行った [lite_llm_completion.py](../packages/graphrag-llm/graphrag_llm/completion/lite_llm_completion.py) の改造概要、ログの仕様、および蓄積されたログの分析・整理を自動化する各種補助スクリプトの解説についてまとめています。

---

## 1. [lite_llm_completion.py](../packages/graphrag-llm/graphrag_llm/completion/lite_llm_completion.py) の改造概要

LLM呼び出し（同期 `completion`・非同期 `completion_async`）をフックし、送受信データを自動でXMLファイルに保存する改造を行いました。

### 最小限の変更差分
GraphRAG本体側のコード変更による影響を最小化するため、ログ出力の実処理（文字列整形やファイル書き込み）はすべて別ファイルの [rawlog_helper.py](../packages/graphrag-llm/graphrag_llm/completion/rawlog_helper.py) にカプセル化しました。
これにより、[lite_llm_completion.py](../packages/graphrag-llm/graphrag_llm/completion/lite_llm_completion.py) の差分は以下の通り、インポートと return 文のラップだけの極小（合計15行程度）に抑えられています。

```python
# lite_llm_completion.py への追加フック例
from graphrag_llm.completion.rawlog_helper import (
    _wrap_response,
    _wrap_response_async,
)

# 同期呼び出しの return ラップ
return _wrap_response(response, messages, is_streaming)

# 非同期呼び出しの return ラップ
return await _wrap_response_async(response, messages, is_streaming)
```

---

## 2. `rawlogs` の仕様

### 2.1 ログディレクトリの出力先
デフォルトでは、カレントディレクトリに `rawlogs/` が生成されます。
環境変数 `GRAPHRAG_RAWLOG_DIR` を指定することで、任意のディレクトリ（例：`graphrag_quickstart/rawlogs/1-prompt-tune`）に動的にログ出力先を切り替えることができます。

### 2.2 スレッドセーフ・高速な連番保存
GraphRAGは非同期（`asyncio`）やマルチスレッドで大量のLLMリクエストを並行処理します。
これに対応するため、ログ書き込み処理には以下の設計が組み込まれています。
* **排他制御（`threading.Lock`）**: ファイル名の競合と書き込み衝突を完全に防止します。
* **メモリ内カウンター（`O(1)`）**: 毎回ディレクトリ全体をスキャン（`glob`）することなく、スレッドロック内で未使用の連番ファイル名（`00001.xml`、`00002.xml` ...）を高速に探索して書き込みを行います。

### 2.3 XMLログ構造
LLMへのリクエストメッセージ履歴（`messages`）をそのままのチャット形式で保存します。LLMからの返答も `role="assistant"` として同一階層にマージして記録します。

```xml
<?xml version="1.0" encoding="utf-8"?>
<messages>
<message role="system"><![CDATA[
(システムプロンプト)
]]></message>
<message role="user"><![CDATA[
(クエリ内容)
]]></message>
<message role="assistant"><![CDATA[
(レスポンス内容)
]]></message>
</messages>
```

---

## 3. 分析補助ツール

蓄積された大量のログファイルを1つずつ、あるいはディレクトリ単位で効率的に処理・分析するための Python スクリプトを作成しました。

### 3.1 [analyze_log.py](analyze_log.py) (LLMを使用)
XMLファイルに保存された `messages` の会話コンテキスト（`system`, `user`, `assistant` などの履歴）をそのまま忠実に復元してローカルLLMに渡し、その末尾に「要約・確認」の確認ターンを付け足して何を行っているか解説させるスクリプトです。

* **機能:**
  * メッセージ履歴を正確に再現してLLMへ入力するため、LLMの理解精度が向上します。
  * 実行結果（解説文）を JSONL 形式のファイル（`1-prompt-tune.jsonl` など）に随時追記します。
  * レジューム機能を備えており、すでに分析済みのファイルは自動でスキップして処理を再開します。
* **実行コマンド例:**
  ```bash
  uv run poe analyze_log graphrag_quickstart/rawlogs/1-prompt-tune
  ```

### 3.2 [analyze_fields.py](analyze_fields.py) (LLM不要の高速処理)
LLMを呼び出さず、ローカルの Python ロジックのみでXML内のレスポンス（最後の `<message>`）がJSONであるかをパースし、JSONであればそのトップレベルのキー（フィールド）を抽出して分析するスクリプトです。

* **機能:**
  * 抽出したフィールド一覧（例: `["title", "summary", "findings", "rating"]`）を出力先 JSONL に書き込みます。
  * 同一のフィールド構造を持つファイルを自動的にグループ化し、出力先 `*-groups.txt` に書き出します。
  * **グループ結果の要約（ブレース展開表記）**: ファイル名の出力が長くなるのを防ぐため、連番のファイル一覧は `{00001..00223}.xml` のように自動でマージしてコンパクトに出力します。
* **実行コマンド例:**
  ```bash
  uv run poe analyze_fields graphrag_quickstart/rawlogs/2-index
  ```
* **グループ化テキストの出力例（`2-index-groups.txt`）:**
  ```text
  ============================================================
  === フィールドグループ化結果 ===
  対象ディレクトリ: graphrag_quickstart/rawlogs/2-index
  ============================================================

  Group 1: [ "title", "summary", "findings", "rating", "rating_explanation" ] (23 files)
    - {00224..00246}.xml

  Group 2 (Non-JSON / Text / Errors): (223 files)
    - {00001..00223}.xml
  ```

---

## 4. エラーメッセージが長すぎる・複雑すぎる場合の対策

ローカル環境のOllamaなどで動作検証を行っている際、接続タイムアウトなどのエラーが発生すると、表示されるエラーログ（スタックトレース）が極めて長大になり、原因特定が難しくなることがあります。

これは、GraphRAGがCLIフレームワークとして採用している `typer` が、デフォルトで例外発生時にローカル変数などを含む非常に詳細な色付きスタックトレースを表示する機能（Pretty Exceptions）を有効にしているためです。

これを無効化し、Python標準のシンプルなスタックトレース表示に戻すには、エントリポイントとなるファイルを以下のように修正します。

* **修正ファイル**: [main.py](../packages/graphrag/graphrag/cli/main.py)
```python
# typer.Typerの初期化時に pretty_exceptions_enable=False を追加
app = typer.Typer(
    help="GraphRAG: A graph-based retrieval-augmented generation (RAG) system.",
    no_args_is_help=True,
    pretty_exceptions_enable=False,  # これを追加
)
```

この対策を施すことで、ローカル環境でエラーが発生した際にも画面が詳細なデバッグログで埋め尽くされることなく、瞬時に原因が把握できる標準的なエラー表示になります。


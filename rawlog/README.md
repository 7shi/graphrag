# rawlog — GraphRAG のローカル LLM 検証・ログ解析

このディレクトリには、GraphRAG をローカルの **Ollama** で動かして検証した際の解説記事と、LLM とのやり取り（rawlogs）を記録・分析するための補助スクリプトがまとまっています。

題材には小説『クリスマス・キャロル』（Charles Dickens）を、解析・要約用のローカル LLM として `gemma4:26b` を用いています。

## ドキュメント

GraphRAG の使い方・内部動作を、2 つの視点からまとめた記事があります。最初に読むなら **A → B** の順がおすすめです。

| ドキュメント | 視点 | 内容 |
| --- | --- | --- |
| [GraphRAG-A.md](GraphRAG-A.md) | **ユーザー視点** | セットアップ → 解析 → 質問という利用の流れに沿った実践記事。各ステップで「裏側で何が起きているか」を補足し、Global / Local Search の実際の出力例も掲載。 |
| [GraphRAG-B.md](GraphRAG-B.md) | **開発者視点** | ソースコードと LLM 処理から動作概要を説明する技術ドキュメント。LLM ログ記録機能の改造、ログ解析、ソースコードとログの対応関係まで踏み込む。 |
| [DIFF.md](DIFF.md) | **変更差分** | 本フォーク（`feature/llm-rawlog`）が本家 GraphRAG に加えた変更を `main` との差分でファイル単位に要約。rawlog 機能の追加と、その調査で判明した Gemma 4 の書式逸脱を受けたグラフ抽出の構造化出力（JSON）移行の経緯を記録。 |
| [ENTITY_RELATIONSHIP.md](ENTITY_RELATIONSHIP.md) | **設計ノート** | entity / relationship 抽出をタプル区切りから構造化出力（JSON）へ移行した理由と実装の詳細。デリミタ問題・Pydantic スキーマ・gleaning・prompt-tune への波及・検証手順までを記録。 |
| [TAGORE.md](TAGORE.md) | **実験まとめ** | 構造化出力による抽出の動作確認の最終結果。Tagore 小説・50 問で index 規模・description 空率・QA 品質を測り、書式由来の脱落が構造化出力で根絶されたことを実証。 |
| [GRAPHRAG.md](GRAPHRAG.md) | **アーキテクチャ考察** | 抽出層（グラフ）の忠実度を上げると GraphRAG の何が変わり何が残るか。3 層構造・消えた限界／残った限界・ボトルネックの下流移動・残る手当てを整理。 |

### 元資料（作業ログ）

A・B は、以下の作業段階のドキュメントを統合・再構成したものです。経緯を追いたい場合の参考に残しています。

| ファイル | 内容 |
| --- | --- |
| [GraphRAG-1.md](GraphRAG-1.md) | GraphRAG 活用ガイド（Ollama / ローカル LLM 構築手順）。**A の元資料**。 |
| [GraphRAG-2.md](GraphRAG-2.md) | LLM ログ記録・分析機能の活用ガイド（`lite_llm_completion.py` の改造概要）。 |
| [GraphRAG-3.md](GraphRAG-3.md) | 実行ログ（rawlogs）詳細分析レポート。 |
| [GraphRAG-4.md](GraphRAG-4.md) | 実行プロセスとソースコードの対応関係レポート。 |

> GraphRAG-2/3/4 は **B に統合済み**です。

## 補助スクリプト

蓄積された rawlogs（XML ログ）を処理・分析するためのスクリプトです。いずれもリポジトリルートから `poe` タスク経由で実行できます。

| スクリプト | 用途 | LLM |
| --- | --- | --- |
| [analyze_log.py](analyze_log.py) | XML に保存された会話コンテキストを復元してローカル LLM に渡し、内容を要約・解説させる（JSONL 出力・レジューム対応）。 | 使用 |
| [analyze_fields.py](analyze_fields.py) | レスポンスが JSON かをパースし、トップレベルのキー構造でファイルを自動グループ化する（高速）。 | 不要 |
| [show_response.py](show_response.py) | 指定した XML ログから `assistant` のレスポンス部分だけを取り出して表示する。 | 不要 |

### 実行例

```bash
# ディレクトリ単位で解析（poe タスク）
uv run poe analyze_log    graphrag_quickstart/rawlogs/1-prompt-tune
uv run poe analyze_fields graphrag_quickstart/rawlogs/2-index

# 個別の XML からレスポンスだけを表示
uv run poe show_response  graphrag_quickstart/rawlogs/3-global/00003.xml
```

> rawlogs の記録方法や XML の仕様、`GRAPHRAG_RAWLOG_DIR` によるフェーズ別出力の切り替えなどは [GraphRAG-B.md](GraphRAG-B.md) を参照してください。

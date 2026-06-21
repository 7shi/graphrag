# GraphRAG 活用ガイド（Ollama/ローカルLLM構築手順）

[GraphRAG](https://github.com/microsoft/graphrag) をローカル環境の Ollama で動作検証します。公式の [Get Started](https://github.com/microsoft/graphrag/blob/main/docs/get_started.md) に沿って、対象テキストとして小説『クリスマス・キャロル』を使用します。

## GraphRAG とは

GraphRAG (Graph Retrieval-Augmented Generation) は、LLM（大規模言語モデル）の力を利用して、非構造化テキストから意味のある構造化データを抽出し、ナレッジグラフ（知識グラフ）を構築して質問応答を行うAIベースのデータパイプラインおよび検索技術です。

従来のキーワード検索やベクトルベースのRAG（Retrieval-Augmented Generation）では回答が難しかった、以下のような検索や分析を得意としています。
* **ドキュメント全体（または小説全体）を跨ぐような質問**（例：「この物語の主要なテーマは何ですか？」）
* **大量の情報間のつながりの追跡・要約**（例：「登場人物Aと登場人物Bの関係はどのように変化しましたか？」）

このドキュメントは、GraphRAGを利用して小説などの長文テキストを分析する際の特徴、サポートされているLLM、動作環境のセットアップ、外部ホストで動作する Ollama (OLLAMA_HOST) の設定、並列処理の最適化（タイムアウト対策）、データの出力形式、およびクエリ（質問）の実行方法についてまとめた解説ドキュメントです。

---

## 1. 小説全文の分析について

GraphRAGは、書籍や小説全体の長文テキストを分析する用途に非常に適しています。

* **ナレッジグラフの構築**: 物語の登場人物、場所、重要なアイテムなどを抽出し、それらの間の「関係性」をグラフとして整理します。
* **大局的なテーマの分析 (Global Search)**: 小説全体を横断したテーマの分析や要約が可能です。
* **登場人物の分析 (Local Search)**: 特定の人物に焦点を当て、その人物と他者との関係性などを詳細に追跡できます。

---

## 2. サポートされているLLM

GraphRAGは内部で [LiteLLM](https://docs.litellm.ai/) を使用してモデルの呼び出しを行っているため、100種類以上のモデルに対応しています。

### 推奨モデル (OpenAI)
GraphRAGが最も徹底的にテストされているのは、OpenAIの **GPT-4シリーズ**（`gpt-4o`, `gpt-4o-mini`, `o1` など）です。

### LiteLLM経由でのサポート (Gemini, Claude, Ollama 等)
`settings.yaml` で `model_provider` と `model` を指定することで、Gemini や Anthropic Claude、ローカルで起動した Ollama などの外部LLMを利用できます。

> [!IMPORTANT]
> **構造化出力 (JSON) の要件**
> 選択するLLMは、**JSONスキーマに準拠した構造化出力 (Structured Outputs / JSON Mode)** をサポートしている必要があります。

---

## 3. 動作環境のセットアップ（独立したプロジェクトの作成）

独立した検証用のプロジェクトスペース（例: `graphrag-test/quickstart`）を作成し、パッケージを個別にインストールして初期化を行う手順です。

```bash
# 1. ワークスペースを作成して依存パッケージを仮想環境に同期・インストール
uv init graphrag-test
cd graphrag-test
uv add graphrag

# 2. 新しい作業用ディレクトリを作成して移動
mkdir quickstart
cd quickstart

# 3. 初期化を実行
uv run graphrag init
```

対話プロンプトが表示されますが、デフォルトのままEnterで進め、後から設定ファイルを編集します。

---

## 4. Ollama との連携設定および最適化 (`settings.yaml`)

初期化後に生成される `quickstart/settings.yaml` を編集し、LLMおよび埋め込みモデルに Ollama を指定します。

Ollama上のローカルモデル（例：31B/26Bクラスなどの推論モデル）を使用する場合、以下の2つの問題に対処する必要があります。
1. **タイムアウトエラー**: デフォルトで25並列リクエストが飛ぶため、Ollamaサーバーが過負荷になりコネクションが切断される。
2. **推論の遅延**: 推論モデル特有の長い「思考プロセス（Reasoning）」が働き、データ抽出に莫大な時間がかかる。

これらを解決するために、同時リクエスト数を `1` に制限し、かつ `reasoning_effort: "none"` を使って思考プロセスを無効化（Ollamaの `think: false` にマッピング）します。

また、環境変数 `OLLAMA_HOST` にIPアドレスのみ（例: `192.168.0.8`）が設定されている場合は、ポート `11434` および `http://` スキームを補正した形式で接続先を指定します。

**設定例 (`settings.yaml`)**:
```yaml
# 対策1：Ollamaへの同時リクエスト数を1に制限（トップレベルに追記）
concurrent_requests: 1

completion_models:
  default_completion_model:
    model_provider: ollama
    model: gemma4:26b-a4b-it-qat  # 使用するLLMのモデル名
    auth_method: api_key
    api_key: ${GRAPHRAG_API_KEY}  # 生成された.envファイルに設定するか、不要ならダミー文字を入力
    api_base: http://${OLLAMA_HOST}:11434  # 環境変数をURL形式に補正
    retry:
      type: exponential_backoff
    # 対策2：思考プロセスを無効化して実行時間を大幅に短縮
    call_args:
      reasoning_effort: "none"

embedding_models:
  default_embedding_model:
    model_provider: ollama
    model: embeddinggemma         # 使用する埋め込みモデル名
    auth_method: api_key
    api_key: ${GRAPHRAG_API_KEY}
    api_base: http://${OLLAMA_HOST}:11434
    retry:
      type: exponential_backoff
```

---

## 5. テストデータの準備

動作確認用として、公式クイックスタート [get_started.md](https://github.com/microsoft/graphrag/blob/main/docs/get_started.md) の記述を参考に、チャールズ・ディケンズの小説『クリスマス・キャロル』のテキストデータをダウンロードして `input/` ディレクトリ配下に配置します。

```bash
# 入力ディレクトリを作成してデータを配置
mkdir -p input
curl https://www.gutenberg.org/cache/epub/24022/pg24022.txt -o input/book.txt
```

---

## 6. 日本語への対応（自動プロンプトチューニング） ※必要に応じて実施

日本語のテキストを扱う場合、デフォルトの設定ファイルのままだとシステムプロンプトが英語であるため、出力される説明文やレポートが英語になってしまうことがあります。

完全に日本語で処理・出力させるためには、インデックスを作成する前に**自動プロンプトチューニング（Prompt Tuning）**を実行することを推奨します。

> [!NOTE]
> **実行のタイミングについて**
> 自動プロンプトチューニングは、前ステップで**解析対象の入力テキストデータ（`input/book.txt` など）を配置した状態**で実行します。

### 日本語化の手順

1. **日本語プロンプトの自動生成**:
   設定ファイル（`settings.yaml`）と入力テキストを読み込ませ、日本語用にカスタマイズされたプロンプトを自動生成します。
   ```bash
   uv run graphrag prompt-tune --root . --language "Japanese"
   ```
   * ※ 実行すると、プロジェクトのルート配下に `prompts/` ディレクトリが作成され、日本語に最適化されたプロンプトファイル（`extract_graph.txt` など）が生成されます。

2. **`settings.yaml` の更新**:
   生成された日本語プロンプトファイルを参照するように、`settings.yaml` 内の該当するプロンプトパスを修正します。
   
   ```yaml
   extract_graph:
     prompt: "prompts/extract_graph.txt"
   summarize_descriptions:
     prompt: "prompts/summarize_descriptions.txt"
   community_reports:
     prompt: "prompts/community_report.txt"
   ```

---

## 7. インデックスの作成（解析の実行）

設定とデータ（および必要に応じたプロンプトチューニング）が完了したら、インデックスを作成します。

```bash
# 解析の実行
uv run graphrag index
```
* ※ 解析した結果は `output/` ディレクトリ配下に各種 Parquet ファイルおよびベクターデータベース（LanceDB）として保存されます。

**インデックス作成の所要時間**: 約20分30秒 (EVO-X2 / Ryzen AI MAX+ 395)
（prompt-tuneで日本語化した場合: 約37分）

---

## 8. 解析データへの質問（クエリの実行）

インデックス作成完了後、構築したデータに対して質問を投げることができます。質問テキストを引数として渡します。

### A. Global Search（マクロな質問）
物語全体のテーマ、共通する葛藤、要約などを調べたい場合に適しています。コミュニティの要約レポートを走査して回答を生成します。

```bash
uv run graphrag query --method global "What are the top themes in this story?"
```

日本語も受け付けます。

```bash
uv run graphrag query --method global "この物語の主要なテーマは何ですか？"
```

**出力例**:

> # 物語の主要なテーマと精神的変容の分析
> 
> この物語における中心的なテーマは、主人公エベネザー・スクルージの精神的な変容と、それに伴う道徳的な再生のプロセスです。以下にその詳細な構造を解説します。
> 
> ### 精神的な変容と道徳的再生
> 物語の中核をなすのは、強欲で孤立していた状態から、慈愛に満ちた社会の一員へとスクルージが再生していく過程です [Data: Reports (2, 5, 14, 19, 22)]。彼は亡きビジネスパートナーや3人の精神（GHOST）との相互作用を通じ、恐怖から慈愛へと至る感情的な弧を描きます。この変容は、自身の人生や他者の運命に直面することで価値観を再構築させるものであり、社会的な孤立から社会への劇的な再統合へと至ります [Data: Reports (2, 5, 14, 17, 22)]。
> 
> ### 時間軸と運命の役割
> 変容を促す重要な枠組みとして、「時間」と「記憶」が挙げられます。過去の記憶（YOUNG SCROOGEや失われた人間関係）は現在の自分を規定する要素となり、時間の連続性が精神的変容を促します [Data: Reports (2, 9, 19)]。
> 
> また、過去・現在・未来という時間軸を通じた個人の運命と責任も描かれています。「来たるべきクリスマスの幽霊」は死の象徴である墓石を指し示すことで、避けられない終焉と道徳的な覚醒を促す役割を担います [Data: Reports (16)]。
> 
> ### 社会的つながりと物質的価値の対比
> 物語は、相反する二つの価値観の対比によって構成されています。
> 
> * **社会的孤立と繋がり**: スクルージの初期状態における社会的断絶や過去の孤独な子供時代（SOLITARY CHILD）といった負の状態から、ボブ・クラチット家のような愛と絆に基づいた社会的なつながりへ、また慈善的精神を持つ人間味のある交流へと変化していく様子が描かれています [Data: Reports (0, 2, 5, 7, 8, 13, +more)]。
> * **物質的執着と精神的価値**: 富への執着（GOLDEN IDOL）と、家族の絆や献身的な行為といった情緒的な価値観との対照が、物語の道徳的側面を浮き彫りにしています [Data: Reports (2, 5, 14)]。さらに、現金箱、鍵、帳簿などの経済的な執着が、死後の罪業の象徴である「鎖」へと変容するプロセスは、商業的な執着が精神的な束縛となる構造を示しています [Data: Reports (3)]。

**Global Search クエリの所要時間**: 約30秒 (EVO-X2 / Ryzen AI MAX+ 395)
（prompt-tuneで日本語化した場合: 約70秒）

---

### B. Local Search（ミクロな質問）
特定の登場人物、特定の出来事など、固有名詞に焦点を当てた詳細な情報を調べたい場合に適しています。

```bash
uv run graphrag query --method local "Who is Scrooge and what are his main relationships?"
uv run graphrag query --method local "スクルージはどのような人物で、誰とどのような関係がありますか？"
```

**出力例**:

> エベネザー・スクルージの人物像とその周囲の人々との複雑な人間関係について、提供された資料に基づきまとめます。
> 
> ### エベネザー・スクルージの人物像
> 
> エベネザー・スクルージは、物語の中心となる圧倒的な存在であり、極めて高い次数を持つハブとして機能しています [Data: Reports (0); Entities (0)]。彼の性格は以下のような特徴を持っています。
> 
> *   **強欲さと孤独:** 彼は「握りつぶすような、むしり取るような、掴み取ろうとする、執着心の強い強欲な罪人」として描かれ、非常に強欲で、硬い石のような冷酷な性質を持っています [Data: Sources (1)]。また、非常に孤独であり、「牡蠣のように自己完結し、世間から隔絶された」状態にありました [Data: Sources (1)]。
> *   **社会的・精神的な変容:** 物語を通じて、彼は「孤独と強欲」から「慈愛と社会貢献」へと劇的に変化を遂げます [Data: Reports (23, 31, 41, 57, +more)]。クリスマスという節目を経て、閉鎖的な個人主義から開かれた社会の一員へと、その精神性と人間性を再定義させていくプロセスが描かれています [Data: Reports (198, 41, 112, +more)]。
> 
> ### 周辺人物との関係性
> 
> スクルージの周囲には、過去の記憶、ビジネス上の繋がり、そして家族としての関係を持つ多くの人々が存在します。
> 
> #### ビジネスと過去の繋がり
> *   **ジェイコブ・マーリー:** かつてのビジネスパートナーであり、現在は亡き人物です [Data: Reports (1, 124)]。マーリーの死はスクルージの現状を揺るがすきっかけとなり、物語における因果関係の起動役（トリガー）として機能しています [Data: Reports (8, 11, 23)]。
> *   **フェズウィッグ:** かつてスクルージが丁稚奉公をしていた時の雇い主で、非常に陽気で慈悲深い人物です [Data: Entities (207); Relationships (54, 49)]。
> *   **ディック・ウィルキンス:** スクルージの元徒弟であり、かつての同僚でもあります [Data: Entities (14); Relationships (55, 51)]。
> 
> #### 家族関係
> *   **甥（フレッド）:** スクルージの甥であるフレッドは、叔父に親交を求めていますが、二人はクリスマスに対する考え方において対立しています [Data: Entities (10, 49, 62); Relationships (88, 1, 110)]。
> *   **妹（ファン）:** スクルージには「ファン」という名前の妹がおり、彼を「親愛なる兄」と呼んでいました [Data: Entities (12); Relationships (47, 48)]。
> *   **姪:** スクルージには聡明で社交的な姪がおり、彼女は叔父であるスクルージの冷淡な態度に対して憤りを感じることもあります [Data: Entities (385); Relationships (90, 89)]。
> 
> #### その他の社会的関係
> *   **ボブ・クラチットとタイニー・ティム:** 物語の終盤において、スクルージはボブへの昇給やタイニー・ティムへの支援を通じて、彼らに対して慈愛に満ちた社会的な繋がりを持つようになります [Data: Reports (41, 112, +more)]。
> *   **ベル（Belle）:** かつての恋人であり、スクルージは彼女の幸せそうな様子を見て、自身の過去や孤独を思索します [Data: Entities (11); Relationships (67)]。

**Local Search クエリの所要時間**: 約40秒 (EVO-X2 / Ryzen AI MAX+ 395)
（prompt-tuneで日本語化した場合: 約50秒）

---

## 9. データ出力形式（簡易見本とノード・エッジの具体例）

インデックス作成 (`index`) が完了すると、テキストデータは解析され、`output/` フォルダ配下に Parquet テーブルとして保存されます。ここでは、各テーブルの簡易的な Markdown 見本と、実際に生成されたデータから `BOB CRATCHIT` に関連する生の格納データ（JSON形式にダンプしたもの）、および原文との対比を解説します。

### A. 簡易データ構造見本（Markdownテーブル）

#### entities (エンティティテーブル)
物語から抽出された主要な登場人物や場所の一覧。

| title (名前) | type (分類) | description (物語全体を通した説明文) | frequency (出現回数) |
| :--- | :--- | :--- | :--- |
| **Ebenezer Scrooge** | `person` | 物語の主人公。強欲な老人。3人の精霊との出会いを経て改心する。 | 42 |

#### relationships (関係性テーブル)
エンティティ同士のつながり（グラフのエッジ）。

| source (主客) | target (対象) | description (関係性の説明) | weight (関係の強さ) |
| :--- | :--- | :--- | :--- |
| **Ebenezer Scrooge** | **Bob Cratchit** | ボブはスクルージの事務所の事務員。スクルージは彼を冷遇している。 | 5.0 |

#### community_reports (コミュニティレポート)
関係性の近い要素ごとにグループ（コミュニティ）を作り、そのグループごとにLLMが分析・作成した詳細な要約。

* **title**: "スクルージのビジネスと家庭環境"
* **findings (主要な発見)**: スクルージの強欲さ、親族（フレッド）との隔絶など。

---

### B. ノード（Entities / 実体）の生データ例
同じ名前のキャラクターが複数の異なるテキストチャンクに登場した場合、LLMがそれらの説明をすべて読み込み、物語全体を通して統合した一貫性のある要約文（`description`）を作成して格納します。

**`BOB CRATCHIT` (ノードレコード)**:
```json
{
  "id": "242e1a77-602b-4d3f-a698-7fcfd23a3c8b",
  "human_readable_id": 7,
  "title": "BOB CRATCHIT",
  "type": "PERSON",
  "description": "Bob Cratchit is the mild-mannered and cheerful underpaid clerk employed by Ebenezer Scrooge, working in Scrooge's office for a weekly salary of fifteen shillings. He resides with his family in a humble four-roomed house located in Camden Town. Bob is a devoted husband to Mrs. Cratchit and a loving father to Peter, Martha, Belinda, and Tiny Tim. \n\nThough he is grieving for the health of his son, Tiny Tim, Bob maintains a positive spirit, leading his family in a Christmas toast and returning home from church on Christmas Day. His modest dwelling is visited by both Scrooge and the Ghost. Ultimately, following a change in his employer's nature, Bob Cratchit receives a large turkey for Christmas, earns a salary increase, and finds that his family is assisted by Mr. Scrooge.",
  "text_unit_ids": [
    "527ef8d0f325a31f64285add4f6138106dc3db756f00d2c7db2688c9cbedfdf00788c1e7de2a1e6b6a6926662fc6c0a935a9d14bb967fa8802a56d8b5156c764",
    "b85209e070a7de249d237524295b008b4e5b8048bc99caba32ebb5cadb435309197859d3c21f6c9390f7d20d97b6ba1a9a64244e735e62d26980240e132d1b63",
    ... (他8件のIDがリストされています)
  ],
  "frequency": 10,
  "degree": 28
}
```

* **`title` / `type`**: 登場人物名 `"BOB CRATCHIT"` および分類属性 `"PERSON"`。
* **`description`**: この人物に言及している全ての箇所を統合した、LLM生成のプロフィール文。
* **`text_unit_ids`**: この人物が登場するテキストチャンク（テキストユニット）のIDリスト。
* **`frequency`**: 登場したテキストチャンクの総数（ここでは `10` 箇所）。
* **`degree`**: グラフにおける接続度（彼と直接関係性を持っている他のエンティティの数。ここでは `28` の実体と結ばれています）。

---

### C. エッジ（Relationships / 関係性）の生データ例
抽出されたエンティティ同士の「つながり」です。同じシーンで関わりが描かれるたびにエッジが形成され、その関係の深さ（登場回数や記述の強さ）が `weight`（重み）として合算されます。

**`BOB CRATCHIT ➡️ EBENEZER SCROOGE` (エッジレコード)**:
```json
{
  "id": "2f48f911-3bda-4fb6-8fa4-e511b03dc5cf",
  "human_readable_id": 0,
  "source": "BOB CRATCHIT",
  "target": "EBENEZER SCROOGE",
  "description": "Bob Cratchit is employed as a clerk to Ebenezer Scrooge",
  "weight": 7.0,
  "combined_degree": 54,
  "text_unit_ids": [
    "527ef8d0f325a31f64285add4f6138106dc3db756f00d2c7db2688c9cbedfdf00788c1e7de2a1e6b6a6926662fc6c0a935a9d14bb967fa8802a56d8b5156c764"
  ]
}
```

* **`source` / `target`**: 関係の起点（`BOB CRATCHIT`）と終点（`EBENEZER SCROOGE`）。
* **`description`**: 二者間の具体的な関係についての説明文。
* **`weight`**: 関係の強さ。このエッジの重みは `7.0` になっています（登場頻度やLLMによる強さ評価が反映されています）。
* **`text_unit_ids`**: この関係性が具体的に記述されていたテキストチャンクのID。ここに格納されたIDを辿ることで、上のボブ・クラチットのノードが持つテキストユニットとも正確に紐づきます。

---

### D. 原文（ダウンロード済みの小説）との対比解説

GraphRAGが生成したノードやエッジの説明文（`description`）が、実際にダウンロードした小説『クリスマス・キャロル』のどの記述から抽出されたか、原文と対比して解説します。

#### 例1：ボブ・クラチットの雇用状況と「週給15シリング」
* **GraphRAGが出力したノード・エッジの記述**:
  > "...working in Scrooge's office for a weekly salary of fifteen shillings..."
  > (スクルージのオフィスで週給15シリングの給与で働いている...)
* **対応する book.txt の原文 (L444-446)**:
  > *'There's another fellow,' muttered Scrooge, who overheard him: 'my clerk, with **fifteen shillings a week**, and a wife and family, talking about a merry Christmas. I'll retire to Bedlam.'*

#### 例2：ボブが働く劣悪な環境（火の小ささ）
* **GraphRAGが出力したノードの説明**:
  > "...mild-mannered and cheerful underpaid clerk employed by Ebenezer Scrooge..."
  > (エベネザー・スクルージに雇用されている、物静かで明るい薄給の事務員...)
* **対応する book.txt の原文 (L325-333)**:
  > *The door of Scrooge's counting-house was open, that he might keep his eye upon his clerk, who in a dismal little cell beyond, a sort of tank, was copying letters. Scrooge had a very small fire, but **the clerk's fire was so very much smaller that it looked like one coal**. But he couldn't replenish it, for Scrooge kept the coal-box in his own room...*

#### 例3：スクルージとの雇用関係
* **GraphRAGが出力したエッジ（BOB CRATCHIT ➡️ EBENEZER SCROOGE）の記述**:
  > "Bob Cratchit is employed as a clerk to Ebenezer Scrooge"
  > (ボブ・クラチットはエベネザー・スクルージの事務員として雇用されている。)
* **対応する book.txt の原文 (L325-327)**:
  > *The door of **Scrooge's** counting-house was open, that he might keep his eye upon **his clerk**, who in a dismal little cell beyond...*

---

### ナレッジグラフ構築のメカニズム

1. **分割 (Chunking)**: 
   入力された小説テキストを、LLMのコンテキスト制限に合わせて一定トークン（例: 1200トークン）ごとの「テキストユニット」に分割します。
2. **LLM によるエンティティ・関係性抽出**:
   分割された各ユニットに対してLLMを実行し、「この文章に登場する人物や組織（ノード）は何か」「それらの間にはどんな関係（エッジ）が描かれているか」を抽出します。
3. **名寄せと説明の統合 (Entity Resolution & Summarization)**:
   別々のユニットで抽出された同一エンティティ（例: 異なる章で言及される `Bob Cratchit`）を名寄せして1つのノードにマージします。さらに、抽出された複数の局所的な説明テキストをLLMが再度読み込み、物語全体を通した一貫性のある「説明文（description）」へ統合します。
4. **関係性の重み付け (Weight Calculation)**:
   登場人物同士が同じテキストユニットで何度も共起し、関係が描かれるほどエッジの `weight` 値が高くなります。これにより、「物語の中で誰と誰の結びつきが特に強いか」をグラフの構造（重み付きエッジ）として表現できるようになります。

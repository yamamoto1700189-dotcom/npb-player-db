# NPB Player DB v17 - Cloud PWA

PCでもスマートフォンでもURLを開くだけで使えるPWA版です。

## 特徴

- Node.js / npm / BAT / VBS / PowerShell 不要（利用時）
- HTTPSのURLで公開
- iPhone / Androidのホーム画面に追加可能
- NPB公式「全ての選手」ページを自動巡回
- 選手ページから年度別成績を取得
- 指標を自動計算して `site/data/database.json` を更新
- GitHub Actionsで毎日03:00 JSTに自動更新
- PWAは更新されたJSONをネットワーク優先で取得
- オフライン時は直前に取得したデータを利用可能
- カスタムPWAアイコン同梱

## 1回だけ必要な設定

1. GitHubで新しいRepositoryを作成
2. このフォルダの中身を `main` ブランチへアップロード
3. Repository Settings → Pages → Source を `GitHub Actions` に設定
4. Actionsが完了すると、RepositoryのPages URLでPWAが公開されます
5. iPhoneではSafariでURLを開き、「ホーム画面に追加」

## 自動更新

GitHub Actionsが毎日03:00 JSTに起動し、NPB公式サイトからデータを取得して再デプロイします。
GitHub Actions画面から `Update NPB database and deploy PWA` を手動実行することもできます。

## 注意

NPB公式サイトは掲載情報・画像・映像等の二次利用および無断転載を禁止しています。取得・公開・再配布する前に、NPBの利用条件を確認してください。

このプロジェクトのスクレイパーはNPB公式の個人年度別成績ページを情報源とします。アクセス頻度を抑え、エラー時はログに残します。

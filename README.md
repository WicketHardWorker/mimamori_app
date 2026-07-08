# 🏠 MiMaMoRi - 見守りアプリ

TP-Link Tapoデバイスを活用した、一人暮らしの親の見守りシステムです。
モーションセンサーとスマートプラグから活動データを収集し、異常があればLINEで通知します。

## 📋 機能一覧

| 機能 | 説明 |
|------|------|
| 📊 活動タイムライン | 時間帯ごとの動き検知・家電使用をグラフ表示 |
| ⏰ 朝の安否確認 | 設定時刻までに活動がなければLINE通知 |
| ⚠️ 長時間不活動アラート | 一定時間動きがなければLINE通知 |
| 📈 週間レポート | 生活リズムの変化を日次で一覧表示 |
| 🔌 家電使用状況 | スマートプラグのON/OFFを記録 |
| 📱 日次レポート | 毎日21時に前日の活動サマリーをLINEで送信 |

## 🔧 使用デバイス

| デバイス | 用途 |
|----------|------|
| **Tapo H100** | IoTハブ（T100との通信ブリッジ） |
| **Tapo T100** | モーションセンサー（動き検知） |
| **Tapo P100M** | スマートプラグ（電気ケトル使用検知） |

## 🏗️ システム構成

```
[T100 センサー] ─sub-GHz─→ [H100 ハブ] ─WiFi─┐
[P100M プラグ+電気ケトル] ─WiFi──────────────┤
                                              ↓
                                    [Raspberry Pi]
                                     ├─ FastAPI Web
                                     ├─ SQLite DB
                                     └─ LINE通知
```

## 🚀 セットアップ

### 1. インストール

```bash
cd ~/mimamori
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. 環境設定

```bash
cp .env.example .env
nano .env  # Tapoアカウント、デバイスIP、LINE設定を記入
```

### 3. 起動

```bash
python -m app.main
# → http://localhost:8000 でダッシュボード表示
```

### 4. 自動起動 (systemd)

```bash
sudo nano /etc/systemd/system/mimamori.service
```

```ini
[Unit]
Description=MiMaMoRi Monitoring Service
After=network-online.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/mimamori
Environment=PATH=/home/pi/mimamori/venv/bin:/usr/bin
ExecStart=/home/pi/mimamori/venv/bin/python -m app.main
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable mimamori
sudo systemctl start mimamori
```

## 🌐 外部アクセス（推奨: Tailscale）

```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
# → Tailscale IP でどこからでもアクセス可能
```

## 📂 プロジェクト構成

```
mimamori/
├── app/
│   ├── main.py              # FastAPI エントリポイント
│   ├── config.py            # 環境設定
│   ├── database.py          # DB接続
│   ├── models.py            # データモデル
│   ├── routers/
│   │   ├── dashboard.py     # Web画面
│   │   └── api.py           # REST API
│   ├── services/
│   │   ├── tapo_monitor.py  # デバイス監視
│   │   ├── alert_service.py # アラート判定
│   │   └── line_notify.py   # LINE通知
│   ├── scheduler/jobs.py    # 定期ジョブ
│   ├── templates/index.html # ダッシュボードUI
│   └── static/              # CSS + JS
├── .env.example
├── requirements.txt
├── preview.html             # UIプレビュー（サンプルデータ入り）
└── README.md
```

## ⚙️ API エンドポイント

| メソッド | パス | 説明 |
|----------|------|------|
| GET | `/` | ダッシュボード画面 |
| GET | `/api/summary` | サマリー情報 |
| GET | `/api/events` | イベント一覧 |
| GET | `/api/alerts` | アラート一覧 |
| POST | `/api/alerts/{id}/acknowledge` | アラート確認 |
| GET | `/api/devices` | デバイス状態 |
| GET | `/api/daily-summary` | 日次サマリー |
| GET | `/api/timeline` | 時間帯別活動データ |

## 📝 ライセンス

MIT License

"""LINE通知テスト"""
import asyncio
from dotenv import load_dotenv

load_dotenv()

async def test():
    from app.services.line_notify import line_service

    await line_service.initialize()

    if not line_service.is_initialized:
        print("❌ LINE通知サービスの初期化に失敗しました")
        return

    print("LINE通知サービス初期化OK、テスト送信中...")

    result = await line_service.send_text_message(
        "🏠 MiMaMoRi テスト通知\n\nこのメッセージが届いていれば、LINE通知は正常に動作しています！"
    )

    if result:
        print("✅ テスト通知を送信しました。LINEを確認してください。")
    else:
        print("❌ 送信に失敗しました。ログを確認してください。")

    await line_service.close()

asyncio.run(test())

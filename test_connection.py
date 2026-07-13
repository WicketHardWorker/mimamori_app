"""Tapoデバイス接続テスト"""
import asyncio
from dotenv import load_dotenv
import os

load_dotenv()

async def test():
    from tapo import ApiClient

    username = os.getenv("TAPO_USERNAME")
    password = os.getenv("TAPO_PASSWORD")
    h100_ip = os.getenv("TAPO_H100_IP")
    p100m_ip = os.getenv("TAPO_P100M_IP")

    print(f"接続テスト開始...")
    print(f"  H100 IP: {h100_ip}")
    print(f"  P100M IP: {p100m_ip}")
    print()

    client = ApiClient(username, password)

    # H100ハブ
    try:
        hub = await client.h100(h100_ip)
        hub_info = await hub.get_device_info()
        print(f"✅ H100ハブ接続成功: {hub_info.nickname}")

        children = await hub.get_child_device_list()
        print(f"   子デバイス数: {len(children)}")
        for child in children:
            nickname = getattr(child, "nickname", "不明")
            model = getattr(child, "model", "不明")
            print(f"   - {nickname} ({model})")
    except Exception as e:
        print(f"❌ H100ハブ接続失敗: {e}")

    print()

    # P100Mプラグ
    try:
        plug = await client.p100(p100m_ip)
        plug_info = await plug.get_device_info()
        is_on = plug_info.device_on
        nickname = getattr(plug_info, "nickname", "P100M")
        print(f"✅ P100Mプラグ接続成功: {nickname} (電源: {'ON' if is_on else 'OFF'})")
    except Exception as e:
        print(f"❌ P100Mプラグ接続失敗: {e}")

    print()
    print("テスト完了")

asyncio.run(test())

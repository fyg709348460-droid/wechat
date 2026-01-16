import os
import re
import uvicorn
import asyncio
import base64
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from openai import OpenAI
import edge_tts

# ================= 配置区 =================
# 建议在 Zeabur 的 Variables 里设置 API_KEY，不要写死在代码里
API_KEY = os.getenv("API_KEY", "sk-xxxxxxxxxxxxxxxx") 
BASE_URL = "https://api.siliconflow.cn/v1"
MODEL_NAME = "Qwen/Qwen3-8B" # 注意：SiliconFlow 通常用 Instruct 版本效果更好

# 默认声音参数
DEFAULT_VOICE = "zh-CN-XiaoxiaoNeural"
DEFAULT_RATE = "+25%" 
DEFAULT_PITCH = "+0Hz"

client = OpenAI(api_key=API_KEY, base_url=BASE_URL)
app = FastAPI()

@app.get("/")
def read_root():
    return {"status": "Zeabur Running"}

# ... (中间的 generate_emotional_audio 函数保持不变) ...
async def generate_emotional_audio(text, emotion_tag):
    # 直接复制您原来的逻辑
    if not text.strip(): return None
    rate = DEFAULT_RATE; pitch = DEFAULT_PITCH
    if "angry" in emotion_tag: rate = "+40%"; pitch = "+5Hz"
    elif "sad" in emotion_tag: rate = "+0%"; pitch = "-5Hz"
    elif "happy" in emotion_tag: rate = "+30%"; pitch = "+2Hz"
    try:
        safe_text = text + "。"
        communicate = edge_tts.Communicate(text=safe_text, voice=DEFAULT_VOICE, rate=rate, pitch=pitch)
        audio_data = b""
        async for chunk in communicate.stream():
            if chunk["type"] == "audio": audio_data += chunk["data"]
        return base64.b64encode(audio_data).decode('utf-8')
    except Exception as e:
        print(f"TTS Error: {e}")
        return None

# ... (中间的 websocket_endpoint 函数保持不变) ...
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    # 直接复制您原来的逻辑，不需要改动
    await websocket.accept()
    # ... 省略中间代码 ...
    # ... 记得把原来的逻辑完整保留 ...

# 🔥🔥🔥 核心修改在这里 🔥🔥🔥
if __name__ == "__main__":
    # Zeabur 会注入 PORT 环境变量，如果没有则默认 8080
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
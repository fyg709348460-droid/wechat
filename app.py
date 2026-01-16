import os
import re
import uvicorn
import asyncio
import base64
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from openai import OpenAI
import edge_tts

# ================= 配置区 =================
API_KEY = os.getenv("API_KEY", "sk-xxxxxxxx") 
BASE_URL = "https://api.siliconflow.cn/v1"
MODEL_NAME = "Qwen/Qwen3-8B"

client = OpenAI(api_key=API_KEY, base_url=BASE_URL)
app = FastAPI()

@app.get("/")
def read_root(): return {"status": "Zeabur WSS Running"}

# 辅助：情感 TTS 生成
async def generate_emotional_audio(text, emotion_tag):
    if not text.strip(): return None
    rate = "+25%"; pitch = "+0Hz"
    if "angry" in emotion_tag: rate = "+40%"; pitch = "+5Hz"
    elif "sad" in emotion_tag: rate = "+0%"; pitch = "-5Hz"
    elif "happy" in emotion_tag: rate = "+30%"; pitch = "+2Hz"
    try:
        communicate = edge_tts.Communicate(text=text + "。", voice="zh-CN-XiaoxiaoNeural", rate=rate, pitch=pitch)
        audio_data = b""
        async for chunk in communicate.stream():
            if chunk["type"] == "audio": audio_data += chunk["data"]
        return base64.b64encode(audio_data).decode('utf-8')
    except: return None

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    print("📱 前端 WSS 已连接")
    try:
        while True:
            user_text = await websocket.receive_text()
            print(f"👂 收到: {user_text}")
            
            # 1. 思考 (流式)
            system_prompt = "你是一个高情商助手。回复简短(40字内)。开头用 <happy>/<angry> 标记情绪。"
            response = client.chat.completions.create(
                model=MODEL_NAME,
                messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_text}],
                temperature=0.7,
                stream=True # 👈 关键：开启流式
            )

            buffer = ""; current_emotion = "neutral"; is_first = True

            for chunk in response:
                if chunk.choices[0].delta.content:
                    char = chunk.choices[0].delta.content
                    buffer += char
                    
                    # 提取情绪
                    if is_first and "<" in buffer and ">" in buffer:
                        match = re.search(r'<(.*?)>', buffer)
                        if match: current_emotion = match.group(1)
                        buffer = re.sub(r'<.*?>', '', buffer)

                    # 断句逻辑 (遇到标点就发，追求速度)
                    if re.search(r'[，。！？、；\n]', char) or (is_first and len(buffer) > 5):
                        clean_text = re.sub(r'<.*?>', '', buffer).strip()
                        if clean_text:
                            # 1. 发文字
                            await websocket.send_json({"type": "text", "content": clean_text})
                            # 2. 发音频
                            audio = await generate_emotional_audio(clean_text, current_emotion)
                            if audio: await websocket.send_json({"type": "audio_base64", "data": audio})
                        
                        buffer = ""; is_first = False

            # 处理尾巴
            clean_text = re.sub(r'<.*?>', '', buffer).strip()
            if clean_text:
                await websocket.send_json({"type": "text", "content": clean_text})
                audio = await generate_emotional_audio(clean_text, current_emotion)
                if audio: await websocket.send_json({"type": "audio_base64", "data": audio})

    except WebSocketDisconnect:
        print("🔌 断开连接")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)

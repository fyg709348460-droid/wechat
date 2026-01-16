import os
import re
import uvicorn
import asyncio
import base64
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from openai import OpenAI
import edge_tts

# ================= 配置区 =================
# 建议在 Zeabur 环境变量中配置 API_KEY
API_KEY = os.getenv("API_KEY", "sk-xxxxxxxxxxxxxxxx") 
BASE_URL = "https://api.siliconflow.cn/v1"
# 推荐使用 Instruct 版本，指令遵循能力更强
MODEL_NAME = "Qwen/Qwen2.5-7B-Instruct"

client = OpenAI(api_key=API_KEY, base_url=BASE_URL)
app = FastAPI()

@app.get("/")
def read_root():
    return {"status": "Zeabur WSS Fixed"}

# 辅助：情感 TTS 生成 (🔥🔥🔥 核心修复在这里 🔥🔥🔥)
async def generate_emotional_audio(text, emotion_tag):
    if not text.strip(): return None
    
    # 1. 强制清洗：无论传入什么，先删掉所有的 <xxx> 标签
    # 这样 TTS 就绝对不会把标签读出来了
    clean_text = re.sub(r'<.*?>', '', text).strip()
    
    if not clean_text: return None

    # 2. 情感参数设置
    rate = "+25%"; pitch = "+0Hz"
    if "angry" in emotion_tag: rate = "+40%"; pitch = "+5Hz"
    elif "sad" in emotion_tag: rate = "+0%"; pitch = "-5Hz"
    elif "happy" in emotion_tag: rate = "+30%"; pitch = "+2Hz"
    
    try:
        # 3. 补句号防止吞音
        communicate = edge_tts.Communicate(text=clean_text + "。", voice="zh-CN-XiaoxiaoNeural", rate=rate, pitch=pitch)
        audio_data = b""
        async for chunk in communicate.stream():
            if chunk["type"] == "audio": audio_data += chunk["data"]
        return base64.b64encode(audio_data).decode('utf-8')
    except Exception as e:
        print(f"TTS Error: {e}")
        return None

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
                stream=True 
            )

            buffer = ""; current_emotion = "neutral"; is_first = True

            for chunk in response:
                if chunk.choices[0].delta.content:
                    char = chunk.choices[0].delta.content
                    buffer += char
                    
                    # 2. 提取情绪 (只在开头提取)
                    if is_first and "<" in buffer and ">" in buffer:
                        match = re.search(r'<(.*?)>', buffer)
                        if match: 
                            current_emotion = match.group(1)
                        # 无论有没有匹配到，只要有尖括号就删掉 buffer 里的标签，防止发给前端
                        buffer = re.sub(r'<.*?>', '', buffer)

                    # 3. 断句逻辑
                    if re.search(r'[，。！？、；\n]', char) or (is_first and len(buffer) > 5):
                        # 发送前再洗一次，双重保险
                        final_text = re.sub(r'<.*?>', '', buffer).strip()
                        
                        if final_text:
                            # 发文字
                            await websocket.send_json({"type": "text", "content": final_text})
                            # 发音频
                            audio = await generate_emotional_audio(final_text, current_emotion)
                            if audio: await websocket.send_json({"type": "audio_base64", "data": audio})
                        
                        buffer = ""; is_first = False

            # 处理尾巴
            final_text = re.sub(r'<.*?>', '', buffer).strip()
            if final_text:
                await websocket.send_json({"type": "text", "content": final_text})
                audio = await generate_emotional_audio(final_text, current_emotion)
                if audio: await websocket.send_json({"type": "audio_base64", "data": audio})

    except WebSocketDisconnect:
        print("🔌 断开连接")

if __name__ == "__main__":
    # 适配 Zeabur 的端口环境变量
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)

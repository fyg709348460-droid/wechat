import os
import re
import uvicorn
import asyncio
import base64
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from openai import OpenAI
import edge_tts

# ================= 配置区 =================
# 自动读取环境变量，如果没设置默认为空字符串
API_KEY = os.getenv("API_KEY", "").strip()
BASE_URL = "https://api.siliconflow.cn/v1"
MODEL_NAME = "Qwen/Qwen2.5-7B-Instruct" # 推荐使用 Instruct 版本

# 延迟初始化客户端（防止构建时因缺 Key 报错）
client = None

def get_client():
    global client
    if client is None:
        if not API_KEY:
            # 尝试再次读取（应对某些云平台的延迟注入）
            key = os.getenv("API_KEY", "").strip()
            if not key:
                raise ValueError("❌ 错误: API_KEY 未设置！请在云平台环境变量中配置。")
            client = OpenAI(api_key=key, base_url=BASE_URL)
        else:
            client = OpenAI(api_key=API_KEY, base_url=BASE_URL)
    return client

app = FastAPI()

@app.get("/")
def read_root():
    """通用健康检查接口"""
    return {
        "status": "Running", 
        "platform": "Universal (HF/Zeabur)",
        "api_key_set": bool(API_KEY)
    }

# 辅助：情感 TTS 生成 (带强制清洗)
async def generate_emotional_audio(text, emotion_tag):
    # 1. 第一道防线：强制清洗标签
    clean_text = re.sub(r'<.*?>', '', text).strip()
    if not clean_text: return None
    
    rate = "+25%"
    pitch = "+0Hz"
    
    if "angry" in emotion_tag:
        rate = "+40%"; pitch = "+5Hz"
    elif "sad" in emotion_tag:
        rate = "+0%"; pitch = "-5Hz"
    elif "happy" in emotion_tag:
        rate = "+30%"; pitch = "+2Hz"
    
    try:
        # 补句号防止吞音
        communicate = edge_tts.Communicate(text=clean_text + "。", voice="zh-CN-XiaoxiaoNeural", rate=rate, pitch=pitch)
        audio_data = b""
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_data += chunk["data"]
        return base64.b64encode(audio_data).decode('utf-8')
    except Exception as e:
        print(f"TTS Error: {e}")
        return None

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    print("📱 前端已连接")
    
    try:
        # 连接建立时检查客户端
        client_instance = get_client()
    except Exception as e:
        await websocket.send_json({"type": "error", "content": str(e)})
        await websocket.close()
        return

    try:
        while True:
            user_text = await websocket.receive_text()
            print(f"👂 收到: {user_text}")
            
            try:
                # 提示词：要求短回复 + 情感标签
                system_prompt = "你是一个高情商助手。回复简短(40字内)。开头用 <happy>/<angry> 标记情绪。"
                response = client_instance.chat.completions.create(
                    model=MODEL_NAME,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_text}
                    ],
                    temperature=0.7,
                    stream=True
                )

                buffer = ""
                current_emotion = "neutral"
                is_first = True

                for chunk in response:
                    if chunk.choices[0].delta.content:
                        char = chunk.choices[0].delta.content
                        buffer += char
                        
                        # 情感提取 (只在开头)
                        if is_first and "<" in buffer and ">" in buffer:
                            match = re.search(r'<(.*?)>', buffer)
                            if match: current_emotion = match.group(1)
                            buffer = re.sub(r'<.*?>', '', buffer) # 删掉标签

                        # 断句发送逻辑
                        if re.search(r'[，。！？、；\n]', char) or (is_first and len(buffer) > 5):
                            # 第二道防线：再次清洗
                            text_segment = re.sub(r'<.*?>', '', buffer).strip()
                            
                            if text_segment:
                                # 发文字
                                await websocket.send_json({"type": "text", "content": text_segment})
                                # 发音频
                                audio = await generate_emotional_audio(text_segment, current_emotion)
                                if audio:
                                    await websocket.send_json({"type": "audio_base64", "data": audio})
                            
                            buffer = ""; is_first = False

                # 尾巴处理
                text_segment = re.sub(r'<.*?>', '', buffer).strip()
                if text_segment:
                    await websocket.send_json({"type": "text", "content": text_segment})
                    audio = await generate_emotional_audio(text_segment, current_emotion)
                    if audio: await websocket.send_json({"type": "audio_base64", "data": audio})

            except Exception as e:
                print(f"处理错误: {e}")
                await websocket.send_json({"type": "error", "content": "AI 思考超时"})

    except WebSocketDisconnect:
        print("🔌 断开连接")

# 🔥🔥🔥 核心：通用启动逻辑 🔥🔥🔥
if __name__ == "__main__":
    # 1. 尝试读取环境变量 PORT (Zeabur/Render 会自动注入这个变量)
    # 2. 如果没读到，默认使用 7860 (Hugging Face 的强制端口)
    port = int(os.environ.get("PORT", 7860))
    print(f"🚀 Server starting on port: {port}")
    uvicorn.run(app, host="0.0.0.0", port=port)

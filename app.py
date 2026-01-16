import os
import re
import uvicorn
import asyncio
import base64
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from openai import OpenAI
import edge_tts

# ================= 配置区 =================
API_KEY = os.getenv("API_KEY", "").strip()
BASE_URL = "https://api.siliconflow.cn/v1"
MODEL_NAME = "Qwen/Qwen3-8B"

# 延迟初始化客户端
client = None

def get_client():
    """延迟初始化 OpenAI 客户端，避免启动时错误"""
    global client
    if client is None:
        if not API_KEY:
            raise ValueError("API_KEY 环境变量未设置或为空")
        try:
            client = OpenAI(api_key=API_KEY, base_url=BASE_URL)
        except Exception as e:
            raise RuntimeError(f"初始化 OpenAI 客户端失败: {str(e)}")
    return client

app = FastAPI()

@app.get("/")
def read_root():
    """健康检查端点"""
    return {
        "status": "Zeabur WSS Running",
        "api_configured": bool(API_KEY),
        "message": "WebSocket endpoint: /ws"
    }

@app.get("/health")
def health_check():
    """健康检查"""
    return {"status": "ok"}

# 辅助：情感 TTS 生成
async def generate_emotional_audio(text, emotion_tag):
    """生成情感语音"""
    if not text.strip():
        return None
    
    rate = "+25%"
    pitch = "+0Hz"
    
    if "angry" in emotion_tag:
        rate = "+40%"
        pitch = "+5Hz"
    elif "sad" in emotion_tag:
        rate = "+0%"
        pitch = "-5Hz"
    elif "happy" in emotion_tag:
        rate = "+30%"
        pitch = "+2Hz"
    
    try:
        communicate = edge_tts.Communicate(
            text=text + "。",
            voice="zh-CN-XiaoxiaoNeural",
            rate=rate,
            pitch=pitch
        )
        audio_data = b""
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_data += chunk["data"]
        return base64.b64encode(audio_data).decode('utf-8')
    except Exception as e:
        print(f"⚠️ TTS 生成失败: {str(e)}")
        return None

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket 端点"""
    await websocket.accept()
    print("📱 前端 WSS 已连接")
    
    try:
        # 检查 API_KEY
        if not API_KEY:
            await websocket.send_json({
                "type": "error",
                "content": "API_KEY 未配置，请在环境变量中设置"
            })
            await websocket.close()
            return
        
        client_instance = get_client()
        
        while True:
            user_text = await websocket.receive_text()
            print(f"👂 收到: {user_text}")
            
            try:
                # 1. 思考 (流式)
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
                        
                        # 提取情绪
                        if is_first and "<" in buffer and ">" in buffer:
                            match = re.search(r'<(.*?)>', buffer)
                            if match:
                                current_emotion = match.group(1)
                            buffer = re.sub(r'<.*?>', '', buffer)

                        # 断句逻辑
                        if re.search(r'[，。！？、；\n]', char) or (is_first and len(buffer) > 5):
                            clean_text = re.sub(r'<.*?>', '', buffer).strip()
                            if clean_text:
                                # 1. 发文字
                                await websocket.send_json({
                                    "type": "text",
                                    "content": clean_text
                                })
                                # 2. 发音频
                                audio = await generate_emotional_audio(clean_text, current_emotion)
                                if audio:
                                    await websocket.send_json({
                                        "type": "audio_base64",
                                        "data": audio
                                    })
                            
                            buffer = ""
                            is_first = False

                # 处理尾巴
                clean_text = re.sub(r'<.*?>', '', buffer).strip()
                if clean_text:
                    await websocket.send_json({
                        "type": "text",
                        "content": clean_text
                    })
                    audio = await generate_emotional_audio(clean_text, current_emotion)
                    if audio:
                        await websocket.send_json({
                            "type": "audio_base64",
                            "data": audio
                        })
                        
            except Exception as e:
                print(f"❌ 处理请求失败: {str(e)}")
                await websocket.send_json({
                    "type": "error",
                    "content": f"处理失败: {str(e)}"
                })
                
    except WebSocketDisconnect:
        print("🔌 断开连接")
    except Exception as e:
        print(f"❌ WebSocket 错误: {str(e)}")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    print(f"🚀 启动服务器，监听端口 {port}")
    print(f"📝 API_KEY 配置: {'✅ 已配置' if API_KEY else '❌ 未配置'}")
    uvicorn.run(app, host="0.0.0.0", port=port)

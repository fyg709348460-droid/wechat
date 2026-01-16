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
MODEL_NAME = "Qwen/Qwen2.5-7B-Instruct" 

# 延迟初始化客户端
client = None

def get_client():
    global client
    if client is None:
        if not API_KEY:
            # 再次尝试读取
            key = os.getenv("API_KEY", "").strip()
            if not key:
                # 本地测试如果没有 key，不会报错，只会连不上
                print("⚠️ 警告: 环境变量 API_KEY 未设置")
            else:
                client = OpenAI(api_key=key, base_url=BASE_URL)
        else:
            client = OpenAI(api_key=API_KEY, base_url=BASE_URL)
    return client

app = FastAPI()

@app.get("/")
def read_root():
    return {"status": "Universal App Running", "version": "Clean-Fix-v2"}

# 🔥🔥🔥 暴力清洗函数 🔥🔥🔥
def aggressive_clean(text):
    if not text: return ""
    
    # 1. 先做标准正则清洗 (删掉 <happy>, <sad> 等标准格式)
    text = re.sub(r'<.*?>', '', text)
    text = re.sub(r'\[.*?\]', '', text) # 防止出现 [happy]
    text = re.sub(r'\(.*?\)', '', text) # 防止出现 (happy)

    # 2. 针对您遇到的 "neutral>" 做定点爆破
    # 只要看到这些词的残留，统统删掉
    dirty_words = [
        "neutral>", "<neutral", "neutral", 
        "happy>", "<happy", 
        "angry>", "<angry",
        "sad>", "<sad"
    ]
    for word in dirty_words:
        text = text.replace(word, "")
        
    # 3. 再次去头去尾的空格
    return text.strip()

# 辅助：情感 TTS 生成
async def generate_emotional_audio(text, emotion_tag):
    # 🌟 调用暴力清洗
    clean_text = aggressive_clean(text)
    
    if not clean_text: return None
    
    rate = "+25%"
    pitch = "+0Hz"
    
    # 简单的关键词匹配，即使标签乱了也能大概率猜对
    if "angry" in emotion_tag:
        rate = "+40%"; pitch = "+5Hz"
    elif "sad" in emotion_tag:
        rate = "+0%"; pitch = "-5Hz"
    elif "happy" in emotion_tag:
        rate = "+30%"; pitch = "+2Hz"
    
    try:
        # 补句号
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
        client_instance = get_client()
    except:
        await websocket.close()
        return

    try:
        while True:
            user_text = await websocket.receive_text()
            print(f"👂 收到: {user_text}")
            
            try:
                # 🔥🔥🔥 Prompt 核心修改 🔥🔥🔥
                # 明确指示：如果是 neutral，就不要输出标签！这样从源头解决问题。
                system_prompt = """
                你是一个高情商助手。回复简短(40字内)。
                情感标记规则：
                1. 只有在【非常开心】时才用 <happy>。
                2. 只有在【生气】时才用 <angry>。
                3. 平淡或正常语气【不要】使用任何标签，也不要输出 <neutral>。
                """
                
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
                        
                        # 尝试提取情绪 (保留逻辑以防万一 AI 还是输出了)
                        if is_first and "<" in buffer and ">" in buffer:
                            match = re.search(r'<(.*?)>', buffer)
                            if match: current_emotion = match.group(1)
                            # 只要检测到尖括号，就视为标签清除掉
                            buffer = re.sub(r'<.*?>', '', buffer)

                        # 断句
                        if re.search(r'[，。！？、；\n]', char) or (is_first and len(buffer) > 5):
                            # 发送前调用暴力清洗
                            text_segment = aggressive_clean(buffer)
                            
                            if text_segment:
                                await websocket.send_json({"type": "text", "content": text_segment})
                                audio = await generate_emotional_audio(text_segment, current_emotion)
                                if audio: await websocket.send_json({"type": "audio_base64", "data": audio})
                            
                            buffer = ""; is_first = False

                # 尾巴处理
                text_segment = aggressive_clean(buffer)
                if text_segment:
                    await websocket.send_json({"type": "text", "content": text_segment})
                    audio = await generate_emotional_audio(text_segment, current_emotion)
                    if audio: await websocket.send_json({"type": "audio_base64", "data": audio})

            except Exception as e:
                print(f"AI Error: {e}")

    except WebSocketDisconnect:
        print("🔌 断开连接")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 7860))
    uvicorn.run(app, host="0.0.0.0", port=port)

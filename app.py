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
            key = os.getenv("API_KEY", "").strip()
            if not key:
                print("⚠️ 警告: 环境变量 API_KEY 未设置")
            else:
                client = OpenAI(api_key=key, base_url=BASE_URL)
        else:
            client = OpenAI(api_key=API_KEY, base_url=BASE_URL)
    return client

app = FastAPI()

@app.get("/")
def read_root():
    return {"status": "Clean Version Running"}

# 🔥🔥🔥 超级清洗函数 (核心修复) 🔥🔥🔥
def super_clean(text):
    if not text: return ""
    
    # 1. 正常的正则清洗 (匹配成对的尖括号)
    text = re.sub(r'<.*?>', '', text)
    
    # 2. 暴力清洗残留的关键词 (防止 neutral> 这种漏网之鱼)
    dirty_list = [
        "neutral", "happy", "angry", "sad", # 标签里的单词
        ">", "<",                           # 单独的尖括号
        "[", "]", "(", ")"                  # 其他可能出现的括号
    ]
    
    for dirty in dirty_list:
        text = text.replace(dirty, "")
        
    return text.strip()

# 辅助：情感 TTS 生成
async def generate_emotional_audio(text, emotion_tag):
    # 再次清洗，确保 TTS 不会读出符号
    clean_text = super_clean(text)
    if not clean_text: return None
    
    rate = "+25%"; pitch = "+0Hz"
    if "angry" in emotion_tag: rate = "+40%"; pitch = "+5Hz"
    elif "sad" in emotion_tag: rate = "+0%"; pitch = "-5Hz"
    elif "happy" in emotion_tag: rate = "+30%"; pitch = "+2Hz"
    
    try:
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
                # Prompt: 严厉禁止输出无关符号
                system_prompt = """
                你是一个对话助手。回复口语化(40字内)。
                规则：
                1. 只有【开心/生气】时才在开头写 <happy>/<angry>。
                2. 平淡语气【绝对不要】带任何标签。
                3. 禁止输出 >、<、# 等符号。
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
                        
                        # 情感提取
                        if is_first and "<" in buffer and ">" in buffer:
                            match = re.search(r'<(.*?)>', buffer)
                            if match: current_emotion = match.group(1)
                            # 提取完立刻把标签删掉
                            buffer = re.sub(r'<.*?>', '', buffer)

                        # 断句逻辑
                        if re.search(r'[，。！？、；\n]', char) or (is_first and len(buffer) > 5):
                            # 🔥 发送前调用超级清洗
                            text_segment = super_clean(buffer)
                            
                            if text_segment:
                                await websocket.send_json({"type": "text", "content": text_segment})
                                audio = await generate_emotional_audio(text_segment, current_emotion)
                                if audio: await websocket.send_json({"type": "audio_base64", "data": audio})
                            
                            buffer = ""; is_first = False

                # 尾巴处理
                text_segment = super_clean(buffer)
                if text_segment:
                    await websocket.send_json({"type": "text", "content": text_segment})
                    audio = await generate_emotional_audio(text_segment, current_emotion)
                    if audio: await websocket.send_json({"type": "audio_base64", "data": audio})

            except Exception as e:
                print(f"Error: {e}")

    except WebSocketDisconnect:
        print("🔌 断开")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 7860))
    uvicorn.run(app, host="0.0.0.0", port=port)

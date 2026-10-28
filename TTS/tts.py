import ChatTTS
import soundfile as sf

chat = ChatTTS.Chat()
chat.load(compile=False)

def tts(text, out="out.wav"):
    wavs = chat.infer([text])
    sf.write(out, wavs[0], 24000)
    print(f"saved {out}")
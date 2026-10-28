import ChatTTS
import torch
import soundfile as sf

chat = ChatTTS.Chat()
chat.load(compile=False)

text = ["Привет, чат! Это уже стабильный голос."]

# создаём один голос и сохраняем
spk = torch.randn(1, 768)
torch.save(spk, "my_voice.pt")

wavs = chat.infer(text)

sf.write("final.wav", wavs[0], 24000)
print("saved final.wav")
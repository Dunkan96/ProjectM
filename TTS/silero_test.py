import torch
import soundfile as sf

model, _ = torch.hub.load(
    repo_or_dir="snakers4/silero-models",
    model="silero_tts",
    language="ru",
    speaker="v5_ru"   # иногда звучит иначе
)

audio = model.apply_tts(
    text="ПРИВЕЕЕТ ЧАААТ!!! Как у вас делааа сегодня??",
    speaker="kseniya",  # женский голос
    sample_rate=48000
)

sf.write("silero.wav", audio, 48000)

print("saved silero.wav")
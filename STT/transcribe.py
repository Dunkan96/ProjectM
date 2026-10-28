from faster_whisper import WhisperModel

model = WhisperModel(
    "base",
    device="cpu",
    compute_type="int8"
)

segments, info = model.transcribe(
    "audio.aac",
    language="ru",
    vad_filter=True
)

with open("result.txt", "w", encoding="utf-8") as f:
    for segment in segments:
        f.write(segment.text.strip() + " ")

print("Готово! Смотри result.txt")
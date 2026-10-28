# stt_ptt.py
import threading
import numpy as np
import sounddevice as sd
import keyboard
from faster_whisper import WhisperModel
from config import STT_MODEL_SIZE, STT_COMPUTE_TYPE, STT_LANGUAGE, STT_DEVICE_INDEX, STT_SAMPLE_RATE, STT_PTT_KEY

class STT_PTT:
    def __init__(self, callback, signals=None):
        self.callback = callback
        self.signals = signals
        self.is_recording = False
        self.audio_frames = []
        self.stream = None
        self.model = WhisperModel(STT_MODEL_SIZE, device="cpu", compute_type=STT_COMPUTE_TYPE)

    def start(self):
        keyboard.on_press_key(STT_PTT_KEY, self._on_press, suppress=False)
        keyboard.on_release_key(STT_PTT_KEY, self._on_release, suppress=False)

    def _on_press(self, event):
        if not self.is_recording:
            if self.signals:
                self.signals.human_speaking = True
            self._start_recording()

    def _on_release(self, event):
        if self.is_recording:
            self._stop_recording()
            if self.signals:
                self.signals.human_speaking = False

    def _start_recording(self):
        self.is_recording = True
        self.audio_frames = []
        self.stream = sd.InputStream(
            device=STT_DEVICE_INDEX,
            samplerate=STT_SAMPLE_RATE,
            channels=1,
            dtype='int16',
            callback=self._audio_callback
        )
        self.stream.start()
        print("[STT] Запись началась...")

    def _audio_callback(self, indata, frames, time, status):
        if self.is_recording:
            self.audio_frames.append(indata.copy())

    def _stop_recording(self):
        self.is_recording = False
        if self.stream:
            self.stream.stop()
            self.stream.close()
            self.stream = None
        print("[STT] Запись остановлена, распознаю...")
        frames_copy = self.audio_frames.copy()
        if frames_copy:
            threading.Thread(target=self._transcribe, args=(frames_copy,), daemon=True).start()
        else:
            print("[STT] Нет аудиоданных")

    def _transcribe(self, frames):
        try:
            audio_data = np.concatenate(frames, axis=0)
            audio_data = audio_data.flatten().astype(np.float32) / 32768.0
            segments, _ = self.model.transcribe(audio_data, language=STT_LANGUAGE)
            text = " ".join(seg.text for seg in segments).strip()
            if text:
                print(f"[STT] Распознано: {text}")
                self.callback(text)
            else:
                print("[STT] Ничего не распознано")
        except Exception as e:
            print(f"[STT] Ошибка транскрипции: {e}")

    def stop(self):
        keyboard.unhook_all()
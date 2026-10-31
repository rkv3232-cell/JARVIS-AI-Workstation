import io
import time
import wave
import queue
import asyncio
import threading
from pathlib import Path
from typing import Optional, Callable
import numpy as np

try:
    import winsound
except ImportError:
    winsound = None

try:
    import sounddevice as sd
    import soundfile as sf
except ImportError:
    sd = None
    sf = None

try:
    import openwakeword
    from openwakeword.model import Model as OWWModel
except ImportError:
    openwakeword = None
    OWWModel = None

from .config import settings

def play_wake_chime():
    """Plays an instant pleasant ascending 2-tone chime upon detecting 'Hey Jarvis'."""
    if winsound:
        try:
            winsound.Beep(988, 70)   # B5 note
            winsound.Beep(1318, 90)  # E6 note
        except Exception:
            pass

def play_ack_chime():
    """Plays a subtle confirmation chime when command has been received."""
    if winsound:
        try:
            winsound.Beep(1318, 50)
            winsound.Beep(1568, 60)
        except Exception:
            pass

def play_audio_file_native(file_path: Path):
    """
    Plays an MP3 or WAV audio file directly through the default Windows speakers
    using soundfile + sounddevice without needing an open browser window.
    """
    if not sd or not sf or not file_path.exists():
        return False
    try:
        data, fs = sf.read(str(file_path), dtype="float32")
        sd.play(data, fs)
        sd.wait()
        return True
    except Exception as e:
        print(f"[LocalWakeListener] Audio playback notice: {e}")
        return False

class LocalWakeWordListener:
    """
    Autonomous background wake-word listener for Windows OS.
    Runs continuously on the default microphone stream without requiring an active browser.
    Detects 'Hey Jarvis' locally using openwakeword ONNX model (<1% CPU).
    Captures voice command, transcribes via Groq Whisper (<300ms), processes intent,
    and speaks back natively through PC speakers.
    """
    def __init__(self, broadcast_callback: Optional[Callable] = None, loop: Optional[asyncio.AbstractEventLoop] = None):
        self._lock = threading.Lock()
        self.broadcast_callback = broadcast_callback
        self.loop = loop
        self.is_running = False
        self.thread: Optional[threading.Thread] = None
        self.stream: Optional[Any] = None
        self.model: Optional[OWWModel] = None
        
        # Audio stream settings
        self.sample_rate = 16000
        self.chunk_size = 1280  # 80ms chunks (standard for openwakeword)
        self.wake_threshold = 0.45
        self.silence_energy_threshold = 280.0
        self.max_command_seconds = 7.5
        self.silence_timeout_seconds = 1.3

        # State flags
        self.is_capturing_command = False
        self.is_processing = False
        self.audio_queue = queue.Queue(maxsize=150)

    def load_model(self) -> bool:
        """Loads the pre-trained 'hey_jarvis' neural wake-word model via ONNX runtime."""
        if not OWWModel:
            print("[LocalWakeListener] openwakeword is not installed.")
            return False
        try:
            self.model = OWWModel(wakeword_models=["hey_jarvis"], inference_framework="onnx")
            print("[LocalWakeListener] Loaded ONNX wake-word model: 'hey_jarvis'")
            return True
        except Exception as e:
            print(f"[LocalWakeListener] Failed to load openwakeword model: {e}")
            return False

    def start(self, loop: Optional[asyncio.AbstractEventLoop] = None):
        """Starts the background listening thread safely, preventing duplicates."""
        with self._lock:
            if loop:
                self.loop = loop
            elif not self.loop:
                try:
                    self.loop = asyncio.get_running_loop()
                except RuntimeError:
                    pass

            if self.is_running:
                return

            if not self.model:
                if not self.load_model():
                    return

            self.is_running = True
            self.thread = threading.Thread(target=self._run_listener_loop, daemon=True, name="JarvisWakeListener")
            self.thread.start()
            print("[LocalWakeListener] Autonomous PC Background Listener is ACTIVE (Listening for 'Hey Jarvis').")

    def stop(self):
        """
        Stops the background listening thread and immediately closes the active microphone stream.
        Drains all queued audio chunks to ensure no audio is retained.
        """
        with self._lock:
            self.is_running = False

            # Explicitly stop and close the sounddevice stream handle
            if self.stream is not None:
                try:
                    self.stream.stop()
                    self.stream.close()
                except Exception as e:
                    print(f"[LocalWakeListener] Notice closing stream: {e}")
                finally:
                    self.stream = None

            # Drain queue immediately
            while not self.audio_queue.empty():
                try:
                    self.audio_queue.get_nowait()
                except Exception:
                    break

            # Join listener thread
            if self.thread and self.thread.is_alive():
                self.thread.join(timeout=1.5)
                self.thread = None

            print("[LocalWakeListener] Background Listener stopped. Microphone stream closed.")

    def is_stream_open(self) -> bool:
        """Returns True if the microphone stream is currently held open."""
        return self.is_running and self.stream is not None

    def _broadcast(self, event: str, payload: dict):
        """Safely pushes events to connected dashboard WebSocket clients if callback is set."""
        if self.broadcast_callback and self.loop and self.loop.is_running():
            try:
                asyncio.run_coroutine_threadsafe(self.broadcast_callback(event, payload), self.loop)
            except Exception as e:
                print(f"[LocalWakeListener] WS Broadcast error: {e}")

    def _run_listener_loop(self):
        """Main audio processing loop running in background thread using PortAudio callback."""
        if not sd:
            print("[LocalWakeListener] sounddevice is missing. Cannot open microphone stream.")
            self.is_running = False
            return

        def _audio_callback(indata, frames, time_info, status):
            if self.is_running:
                try:
                    self.audio_queue.put_nowait(indata.copy())
                except queue.Full:
                    try:
                        self.audio_queue.get_nowait()
                        self.audio_queue.put_nowait(indata.copy())
                    except Exception:
                        pass

        try:
            stream = sd.InputStream(
                samplerate=self.sample_rate,
                channels=1,
                dtype="int16",
                blocksize=self.chunk_size,
                callback=_audio_callback
            )
            self.stream = stream
            stream.start()

            while self.is_running:
                try:
                    chunk = self.audio_queue.get(timeout=0.2)
                except queue.Empty:
                    continue

                flat_chunk = chunk.flatten()

                if self.is_capturing_command or self.is_processing:
                    time.sleep(0.01)
                    continue

                # 1. Run local prediction on current audio chunk
                if self.model:
                    prediction = self.model.predict(flat_chunk)
                    score = prediction.get("hey_jarvis", 0.0)

                    if score >= self.wake_threshold:
                        print(f"\n[LocalWakeListener] ✦ WAKE-WORD DETECTED! ('Hey Jarvis', score: {score:.2f})")
                        self._handle_wake_event()

        except Exception as e:
            print(f"[LocalWakeListener] Audio stream exception: {e}")
        finally:
            if self.stream is not None:
                try:
                    self.stream.stop()
                    self.stream.close()
                except Exception:
                    pass
                self.stream = None
            # Drain queue
            while not self.audio_queue.empty():
                try:
                    self.audio_queue.get_nowait()
                except Exception:
                    break
            self.is_running = False

    def _handle_wake_event(self):
        """Invoked when 'Hey Jarvis' is detected."""
        # 1. Instant Audio & Visual Feedback
        play_wake_chime()
        self._broadcast("local_wake_triggered", {"status": "listening", "timestamp": time.time()})

        # 2. Reset wake model buffer to prevent double triggers
        self.model.reset()

        # 3. Capture user's spoken command from callback queue
        self.is_capturing_command = True
        command_wav_bytes = self._record_user_command()
        self.is_capturing_command = False

        if not command_wav_bytes:
            print("[LocalWakeListener] No speech detected after wake word.")
            return

        # 4. Process the command in an asynchronous worker thread
        self.is_processing = True
        threading.Thread(target=self._process_command_worker, args=(command_wav_bytes,), daemon=True).start()

    def _record_user_command(self) -> Optional[bytes]:
        """
        Records the user's voice command until silence is detected via Voice Activity Detection (VAD).
        """
        play_ack_chime()
        collected_chunks = []
        has_spoken = False
        silence_start: Optional[float] = None
        start_time = time.time()

        while (time.time() - start_time) < self.max_command_seconds:
            try:
                chunk = self.audio_queue.get(timeout=0.2)
            except queue.Empty:
                continue

            flat = chunk.flatten()
            collected_chunks.append(flat)

            # Compute RMS audio energy
            energy = np.sqrt(np.mean(flat.astype(np.float64) ** 2))

            if energy > self.silence_energy_threshold:
                has_spoken = True
                silence_start = None
            else:
                if has_spoken:
                    if silence_start is None:
                        silence_start = time.time()
                    elif (time.time() - silence_start) >= self.silence_timeout_seconds:
                        # User stopped speaking
                        break
                else:
                    # Give user 2.5 seconds to start speaking after wake chime
                    if (time.time() - start_time) > 2.5:
                        break

        if not has_spoken or len(collected_chunks) < 5:
            return None

        # Build 16kHz mono WAV bytes in memory
        audio_array = np.concatenate(collected_chunks)
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(self.sample_rate)
            wf.writeframes(audio_array.tobytes())
        return buf.getvalue()

    def _process_command_worker(self, wav_bytes: bytes):
        """Transcribes, executes intent, generates speech and plays back natively."""
        try:
            # Create a localized event loop for async services
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self._execute_async_pipeline(wav_bytes))
            loop.close()
        except Exception as e:
            print(f"[LocalWakeListener] Command execution error: {e}")
        finally:
            self.is_processing = False
            if self.model:
                self.model.reset()

    async def _execute_async_pipeline(self, wav_bytes: bytes):
        from .voice_service import transcribe_audio_bytes, generate_speech_file
        from .ai_brain import process_user_intent

        t0 = time.time()
        # 1. Transcribe speech using Groq Whisper Turbo (<300ms)
        transcript = await transcribe_audio_bytes(wav_bytes, filename="local_mic.wav")
        transcript = transcript.strip()

        if not transcript:
            print("[LocalWakeListener] STT returned empty transcript.")
            return

        print(f"[LocalWakeListener] 🎙️ User: \"{transcript}\" (STT in {(time.time()-t0)*1000:.0f}ms)")
        self._broadcast("user_message_received", {"text": transcript, "source": "local_wake_word"})

        # 2. Process Intent via AI Brain
        result = await process_user_intent(transcript)
        reply_text = result.get("text", "")
        dynamic_widget = result.get("dynamic_widget")

        print(f"[LocalWakeListener] ✦ Jarvis: \"{reply_text}\"")

        # 3. Generate Speech Audio File
        audio_rel_url = await generate_speech_file(reply_text)
        audio_full_path = None
        if audio_rel_url:
            from .voice_service import AUDIO_CACHE_DIR
            filename = Path(audio_rel_url).name
            audio_full_path = AUDIO_CACHE_DIR / filename

        # 4. Broadcast to dashboard UI (so browser updates live if open)
        self._broadcast("chat_response", {
            "text": reply_text,
            "audio_url": audio_rel_url,
            "action_executed": result.get("action_executed"),
            "intent": result.get("intent", "general"),
            "dynamic_widget": dynamic_widget
        })

        # 5. Play Native Audio on Windows Speakers
        if audio_full_path and audio_full_path.exists():
            play_audio_file_native(audio_full_path)


# Global singleton instance
_GLOBAL_LISTENER: Optional[LocalWakeWordListener] = None

def get_wake_listener() -> LocalWakeWordListener:
    global _GLOBAL_LISTENER
    if _GLOBAL_LISTENER is None:
        _GLOBAL_LISTENER = LocalWakeWordListener()
    return _GLOBAL_LISTENER

def start_local_wake_listener(broadcast_callback: Optional[Callable] = None, loop: Optional[asyncio.AbstractEventLoop] = None):
    listener = get_wake_listener()
    if broadcast_callback:
        listener.broadcast_callback = broadcast_callback
    if loop is None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            pass
    listener.start(loop=loop)

def stop_local_wake_listener():
    global _GLOBAL_LISTENER
    if _GLOBAL_LISTENER:
        _GLOBAL_LISTENER.stop()
        _GLOBAL_LISTENER = None

def is_wake_listener_running() -> bool:
    global _GLOBAL_LISTENER
    return _GLOBAL_LISTENER is not None and _GLOBAL_LISTENER.is_stream_open()

if __name__ == "__main__":
    print("=================================================================")
    print("      JARVIS LOCAL WAKE-WORD STANDALONE LISTENER (PC ENGINE)     ")
    print("=================================================================")
    print("Say 'Hey Jarvis' to activate your assistant anytime.")
    print("Press Ctrl+C to terminate.")
    
    listener = get_wake_listener()
    listener.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        listener.stop()
        print("\nListener terminated.")

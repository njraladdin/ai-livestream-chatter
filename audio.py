import pyaudiowpatch as pyaudio
import numpy as np
import wave
import os
from datetime import datetime
from scipy import signal

class SystemAudioCapture:
    def __init__(self, format=pyaudio.paInt16, channels=1, 
                 sample_rate=16000, chunk_size=1024):
        """Initialize system audio capture matching live.py settings"""
        self.format = format
        self.channels = channels
        self.sample_rate = sample_rate
        self.chunk_size = chunk_size
        
        self.py_audio = pyaudio.PyAudio()
        self.stream = None
        self.chunks = []  # Store chunks temporarily
        self.chunk_count = 0
        
        # Create test directory if it doesn't exist
        os.makedirs("test", exist_ok=True)

    def start_stream(self):
        """Start the audio stream using WASAPI loopback for system audio"""
        host_api_info = self.py_audio.get_host_api_info_by_type(pyaudio.paWASAPI)
        default_speakers = self.py_audio.get_device_info_by_index(host_api_info["defaultOutputDevice"])

        if not default_speakers.get("isLoopbackDevice", False):
            for loopback in self.py_audio.get_loopback_device_info_generator():
                if default_speakers["name"] in loopback["name"]:
                    default_speakers = loopback
                    break
            
        # Use the device's default sample rate
        device_sample_rate = int(default_speakers.get("defaultSampleRate", 44100))
        print(f"Using device sample rate: {device_sample_rate}")
        
        self.stream = self.py_audio.open(
            format=self.format,
            channels=2,  # WASAPI usually requires stereo
            rate=device_sample_rate,  # Use device's sample rate
            frames_per_buffer=self.chunk_size,
            input=True,
            input_device_index=default_speakers["index"],
            stream_callback=None
        )
        
        # Store the actual sample rate for resampling if needed
        self.actual_sample_rate = device_sample_rate

    def read_chunk(self, exception_on_overflow=False):
        """Read a chunk of audio data and save every 5 seconds"""
        if not self.stream:
            raise RuntimeError("Stream not started")
            
        data = self.stream.read(self.chunk_size, exception_on_overflow=exception_on_overflow)
        
        # Convert to numpy array for processing
        audio_data = np.frombuffer(data, dtype=np.int16)
        
        # Convert stereo to mono if needed
        if self.stream._channels == 2 and self.channels == 1:
            audio_data = np.mean(audio_data.reshape(-1, 2), axis=1, dtype=np.int16)
        
        # Resample if needed (from actual_sample_rate to self.sample_rate)
        if hasattr(self, 'actual_sample_rate') and self.actual_sample_rate != self.sample_rate:
            audio_data = signal.resample(audio_data, 
                                       int(len(audio_data) * self.sample_rate / self.actual_sample_rate))
            audio_data = audio_data.astype(np.int16)
        
        data = audio_data.tobytes()
        self.chunks.append(data)
        self.chunk_count += 1
        
        # Calculate how many chunks make up 5 seconds:
        # (sample_rate * seconds) = total samples needed
        # total samples / chunk_size = number of chunks needed
        chunks_per_save = int((self.sample_rate * 5) / self.chunk_size)
        #print(f"Chunk {self.chunk_count}/{chunks_per_save}")  # Debug print
        
        if self.chunk_count >= chunks_per_save:
            self._save_chunks()
            self.chunks = []
            self.chunk_count = 0
            
        return data

    def _save_chunks(self):
        """Save accumulated chunks to a WAV file"""
        if not self.chunks:
            return
            
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"test/audio_{timestamp}.wav"
        
        # with wave.open(filename, 'wb') as wf:
        #     wf.setnchannels(self.channels)
        #     wf.setsampwidth(self.py_audio.get_sample_size(self.format))
        #     wf.setframerate(self.sample_rate)
        #     wf.writeframes(b''.join(self.chunks))
            
        #print(f"Saved audio chunk to {filename}")

    def stop_stream(self):
        """Stop and clean up the audio stream"""
        if self.stream:
            self.stream.stop_stream()
            self.stream.close()
            self.stream = None
        self.py_audio.terminate()
        
        # Save any remaining chunks
        if self.chunks:
            self._save_chunks()

# Example usage matching live.py settings
if __name__ == "__main__":
    audio = SystemAudioCapture(
        format=pyaudio.paInt16,      # FORMAT from live.py
        channels=1,                   # CHANNELS from live.py
        sample_rate=16000,           # SEND_SAMPLE_RATE from live.py
        chunk_size=1024              # CHUNK_SIZE from live.py
    )
    
    try:
        audio.start_stream()
        print("Recording chunks for 5 seconds...")
        
        # Record for 5 seconds
        for _ in range(int(16000 * 5 / 1024)):  # (sample_rate * seconds / chunk_size)
            data = audio.read_chunk()
            # Data can now be used as needed
            
    finally:
        audio.stop_stream()

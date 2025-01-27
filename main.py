# Standard library imports
import asyncio
import base64
import io
import json
import os
import re
import sys
import time
import traceback
from datetime import datetime
from functools import partial

# Third-party imports
import mss
import PIL.Image
import pyaudio
import pyautogui
from dotenv import load_dotenv
from google import genai
from PIL import Image, ImageGrab, ImageDraw

# Local imports
from audio import SystemAudioCapture


# Audio configuration
FORMAT = pyaudio.paInt16
CHANNELS = 1
SEND_SAMPLE_RATE = 16000
RECEIVE_SAMPLE_RATE = 24000
CHUNK_SIZE = 1024


# Load environment variables and initialize Google API
load_dotenv()
GOOGLE_API_KEY = os.getenv('GOOGLE_API_KEY')
if not GOOGLE_API_KEY:
    raise ValueError("GOOGLE_API_KEY not found in .env file")

# Initialize the client
client = genai.Client(
    api_key=GOOGLE_API_KEY,
    http_options={'api_version': 'v1alpha'}
)

# Load prompts from files
def load_prompt(filename):
    prompt_path = os.path.join('prompts', filename)
    with open(prompt_path, 'r', encoding='utf-8') as f:
        return f.read().strip()


# Load prompts
MESSAGE_STYLE = load_prompt('message_style_prompt.txt')
GOAL_PROMPT = load_prompt('goal_prompt.txt')
SYSTEM_PROMPT = MESSAGE_STYLE + "\n" + GOAL_PROMPT + "\n" + load_prompt('system_prompt.txt')
# Initialize PyAudio
pya = pyaudio.PyAudio()


class KickWebsiteChecker:
    def __init__(self):
        self.setup_safety()

    def setup_safety(self):
        pyautogui.FAILSAFE = True
        pyautogui.PAUSE = 1.0

    def locate_with_scaling(self, template_path, base_confidence=0.8):
        """Locate image with different scale attempts"""
        # Common browser zoom levels and UI scales
        scales = [1.0, 0.9, 0.85, 0.8, 0.75, 0.67, 0.5,
                  1.1, 1.15, 1.25, 1.33, 1.5, 1.75, 2.0, 2.5, 3.0]
        
        for scale in scales:
            try:
                # Load and scale the template image
                template = Image.open(template_path)

                # Scale the template
                new_size = (int(template.size[0] * scale), int(template.size[1] * scale))
                template = template.resize(new_size, Image.LANCZOS)

                # Use the PIL Image object directly with PyAutoGUI
                result = pyautogui.locateOnScreen(template, confidence=base_confidence)

                if result:
                    print(f"Found match at browser scale: {scale*100}%")
                    return result

            except Exception as e:
                continue

        print(f"No match found at any common browser scale")
        return None

    def is_chat_locked(self):
        """Check if chat is locked (requires follow/banned/etc)"""
        try:
            locked = self.locate_with_scaling('kick_ui/kick_chat_locked.png')
            if locked:
                print("""
⚠ Chat is locked:
• You may need to follow the streamer
• You might be banned/timed out
• Account might need verification
• Stream might be in followers-only mode""")
                return True
            return False
        except Exception:
            return False

    def check_chat_available(self):
        """Check if chat input is available"""
        try:
            # First check if chat is locked
            if self.is_chat_locked():
                return False

            # Then check for chat input
            chat_input = self.locate_with_scaling(
                'kick_ui/kick_chat_input.png')
            if chat_input:
                print("✓ Found stream chat!")
                return True
            else:
                print("""
⚠ Stream chat not found:
• Open a live stream
• Make chat visible on right
• Follow streamer if required
• Verify account if needed""")
                return False
        except Exception as img_error:
            print("""
⚠ Can't detect chat:
• Open a live stream
• Make chat visible
• Follow/verify if required""")
            return False

    def type_in_chat(self, message):
        """Type a message in the chat input"""
        try:
            # Find chat input box with scaling support
            chat_input = self.locate_with_scaling(
                'kick_ui/kick_chat_input.png')
            if not chat_input:
                print("❌ Can't find chat input box")
                return False

            # Click near the top-left corner of the chat input box
            click_x = chat_input.left + 10
            click_y = chat_input.top + 10
            pyautogui.click(click_x, click_y)
            time.sleep(0.5)  # Wait for click to register

            # Type the message
            # Add small delay between keystrokes
            pyautogui.write(message, interval=0.05)
            pyautogui.press('enter')
            print(f"✓ Sent message: {message}")
            pyautogui.press('esc')
            return True

        except Exception as e:
            print(f"❌ Failed to send message: {str(e)}")
            return False

    def ensure_kick_ready(self):
        """Main method to ensure Kick is ready for streaming"""
        print("\n=== Checking Kick Setup ===")

        while not self.check_chat_available():
            print("Waiting for chat...")
            time.sleep(2)

        print("\n✓ Ready to go!")
        return True


class AIStreamChatter:
    def __init__(self):
        self.audio_in_queue = None
        self.out_queue = None
        self.session = None
        self.audio_capture = None
        self.kick_checker = KickWebsiteChecker()
        self.last_message_time = 0  # Track last message timestamp

    def _get_screen(self):
        # Create debug_input directory if it doesn't exist
        os.makedirs("debug_input", exist_ok=True)

        sct = mss.mss()
        monitor = sct.monitors[0]
        
        i = sct.grab(monitor)

        mime_type = "image/jpeg"
        image_bytes = mss.tools.to_png(i.rgb, i.size)
        img = PIL.Image.open(io.BytesIO(image_bytes))

        # Save the image to debug_input folder with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        img.save(f"debug_input/screen_{timestamp}.jpg")

        # Continue with the normal process
        image_io = io.BytesIO()
        img.save(image_io, format="jpeg")
        image_io.seek(0)

        image_bytes = image_io.read()
        return {"mime_type": mime_type, "data": base64.b64encode(image_bytes).decode()}

    async def get_screen(self):
        while True:
            frame = await asyncio.to_thread(self._get_screen)
            if frame is None:
                break
            await self.out_queue.put(frame)  # Use single queue
            await asyncio.sleep(5.0)
            print("Screen sent")

    async def listen_audio(self):
        """Capture system audio using SystemAudioCapture"""
        self.audio_capture = SystemAudioCapture(
            format=FORMAT,
            channels=CHANNELS,
            sample_rate=SEND_SAMPLE_RATE,
            chunk_size=CHUNK_SIZE
        )

        try:
            self.audio_capture.start_stream()
            while True:
                data = await asyncio.to_thread(
                    self.audio_capture.read_chunk,
                    exception_on_overflow=False
                )
                # Use single queue
                await self.out_queue.put({"data": data, "mime_type": "audio/pcm"})
        finally:
            self.audio_capture.stop_stream()

    async def send_realtime(self):
        """Simple send loop like in live.py"""
        while True:
            msg = await self.out_queue.get()
            await self.session.send(input=msg)  # No end_of_turn needed

    async def receive_audio(self):
        """Background task to read responses from Gemini"""
        print("Starting receive task...")
        current_response = []

        while True:
            try:
                async for response in self.session.receive():
                    if text := response.text:
                        current_response.append(text)
                    # Check if this is the end of the turn
                    if response.server_content and response.server_content.turn_complete:
                        if current_response:  # Only process if we have accumulated text
                            full_response = "".join(current_response)

                            # Extract JSON from markdown code block if present
                            json_match = re.search(
                                r'```(?:json)?\s*({.*?})\s*```', full_response, re.DOTALL)
                            if json_match:
                                json_str = json_match.group(1)
                            else:
                                json_str = full_response

                            try:
                                # Parse the JSON response
                                json_response = json.loads(json_str.strip())
                                if 'message' in json_response and 'relevancy' in json_response:
                                    # Only process highly relevant messages (>80)
                                    if json_response['relevancy'] >= 80:
                                        current_time = time.time()
                                        # Only send if 30 seconds have passed since last message
                                        if current_time - self.last_message_time >= 20:
                                            print(
                                                f"Sending message: {json_response}")
                                            if await self.send_to_chat(json_response['message']):
                                                self.last_message_time = current_time
                                                print(
                                                    f"Chat message sent: {json_response}")
                                            else:
                                                print(
                                                    "Failed to send message to chat")
                                        else:
                                            print(
                                                f"Skipped message (cooldown): {json_response}")
                                    else:
                                        print(
                                            f"Skipped low relevancy message: {json_response}")
                                else:
                                    print(
                                        f"Warning: Response missing required fields: {json_str}")
                            except json.JSONDecodeError:
                                print(
                                    f"Warning: Invalid JSON response: {json_str}")
                            current_response = []  # Reset for next turn
            except Exception as e:
                print(f"Error in receive_audio: {e}")
                await asyncio.sleep(0.1)

    async def send_to_chat(self, message):
        """Send message to chat with async wrapper"""
        try:
            # Use to_thread since type_in_chat is synchronous
            result = await asyncio.to_thread(self.kick_checker.type_in_chat, message)
            return result
        except Exception as e:
            print(f"Error sending to chat: {e}")
            return False

    async def run(self):
        try:
            # First ensure Kick is ready
            await asyncio.to_thread(self.kick_checker.ensure_kick_ready)
            # Model configuration

            async with (
                client.aio.live.connect(model="models/gemini-2.0-flash-exp", config={
                    "generation_config": {
                        "response_modalities": ["TEXT"]
                    }
                }) as session,
                asyncio.TaskGroup() as tg,
            ):
                self.session = session

                # Send system prompt first after connection
                await self.session.send(input=SYSTEM_PROMPT, end_of_turn=True)

                # Clear initial response
                async for response in session.receive():
                    continue

                self.audio_in_queue = asyncio.Queue()
                self.out_queue = asyncio.Queue(maxsize=5)

                tg.create_task(self.send_realtime())
                tg.create_task(self.listen_audio())
                tg.create_task(self.get_screen())
                tg.create_task(self.receive_audio())

                while True:
                    await asyncio.sleep(1)

        except asyncio.CancelledError:
            if self.audio_capture:
                self.audio_capture.stop_stream()
            pass
        except ExceptionGroup as EG:
            if self.audio_capture:
                self.audio_capture.stop_stream()
            traceback.print_exception(EG)


if __name__ == "__main__":
    main = AIStreamChatter()
    asyncio.run(main.run())

# AI Livestream Chatter

A Realtime AI bot that watches Kick.com livestreams and chats naturally in the stream's chat by understanding what's happening on screen and what's being said.

## What it Does

- Watches the stream video and listens to audio in real-time
- Uses Google's Gemini AI to understand what's happening in the stream
- Generates relevant chat messages based on the stream content
- Automatically types messages in Kick.com's chat interface


## Setup

1. Clone the repository
2. Install requirements:
   ```bash
   pip install -r requirements.txt
   ```
3. Create a `.env` file with your Google API key:
   ```
   GOOGLE_API_KEY=your_key_here
   ```
4. Ensure the `kick_ui` folder contains necessary UI element screenshots
5. Create a `prompts` folder with required prompt files:
   - `message_style_prompt.txt`
   - `goal_prompt.txt`
   - `system_prompt.txt`

## Usage

1. Open a Kick.com livestream in your browser
2. Ensure the chat is visible on the right side
3. Run the script:
   ```bash
   python main.py
   ```
4. The bot will automatically verify chat access and begin monitoring the stream. 

## Notes

- Keep the stream window visible and chat accessible
- The bot requires chat permissions (follow streamer if needed)
- Debug screenshots are saved to `debug_input` folder
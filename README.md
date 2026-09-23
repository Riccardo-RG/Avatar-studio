# Avatar Studio

Avatar Studio is a personal macOS app for planning and producing short videos with virtual characters. It brings together scripts, voice, subtitles, saved projects, video generation or import, vertical editing, and social media export packages. It runs locally for one person; it is not a SaaS service.

## What you can do

- Manage characters and projects while keeping scripts, source materials, and revisions together.
- Draft scripts from an idea or a content plan and create Italian speech locally.
- Build local scenes with 3D avatars, illustrations, or narrated portraits, then add subtitles and edit the video.
- Follow the **Prepare → Generate → Import → Finish** workflow: create an avatar video on the HeyGen website, then complete it in Avatar Studio.
- Export vertical MP4 videos, covers, subtitles, and media packages for YouTube, TikTok, and Instagram.
- Organize campaigns and content, and use the local tools for directing and live streams.

**Important limitation:** local modes create stylized characters or narrated portraits. They do not realistically animate a human face. For that workflow, you can generate the video on the HeyGen website. An optional API integration is also available and is separate from a HeyGen website subscription.

## Requirements

- macOS 13.5 or later;
- Python 3.11, 3.12, or 3.13 for macOS;
- Google Chrome.

The setup installs dependencies inside the project folder and downloads the speech and language models. It also installs Node.js and the local script engine for your Mac's architecture. An Internet connection is required during setup.

## Start the app

Clone the repository, open `Prepara Mac.command`, and wait for setup to finish. Then open `Avvia Avatar Studio.command`. The app opens in your browser and keeps running while its Terminal window stays open. To stop it, press Ctrl+C in that window.

After setup, you can also launch it from Terminal:

```sh
.venv/bin/python app.py
```

The server listens on `127.0.0.1:8765`, so it is available on your Mac only. Do not expose this port to the public Internet.

## Workflow for a realistic avatar video

1. In **Projects**, choose a character with an image and prepare the script, voice, and subtitles.
2. Download the prepared materials and open HeyGen from the project.
3. Generate and download the video from the HeyGen website.
4. Import the MP4 into the same project, check the crop, format, and subtitles, then export the finished video.

HeyGen requires an account and a website subscription or API credits. The API integration is optional; a website subscription does not automatically include API access.

## Services and data

Local speech synthesis and the local script engine do not require a cloud account. OpenAI, the HeyGen API, web search, and social platform integrations are optional and require your own credentials. Using an external service may send the data required for that feature to its provider; review content before sending it.

Local settings, tokens, projects, recordings, and generated videos are excluded from Git. Do not put API keys in source code or files you plan to publish. Configure credentials only in your local environment. Generated files and downloaded models stay in the project folder.

## Development

The backend uses Python's standard HTTP library; the interface uses JavaScript and CSS. Python dependencies are listed in `requirements-mac.txt`. The Node.js runtime is declared in `package.json` and installed locally by the setup script.

To run the test suite:

```sh
.venv/bin/python -m unittest discover -p 'test_*.py' -v
```

## License

This repository does not currently declare an overall license. Dependencies and downloaded models may have their own terms; check their notices before redistributing the app or its materials.

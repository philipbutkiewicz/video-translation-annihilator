# video-translation-annihilator
A simple Python script to remove any translation data (ie. dubbed audio, subtitles) from video media. Because I want to watch Japanese content in Japanese without having to turn off subtitles and without having to switch the audio language.

## Setup
```bash
pip install -r requirements.txt
python video-translation-annihilator.py --help
```

## Usage
Generally you should refer to the help command, but here is an example how to remove all audio and subtitle streams from a file except for Japanese and "Unknown" ones:
```bash
python video-translation-annihilator.py --input-path <input_path> --languages jap,jpn --script-path process-media-files.sh
chmod +x process-media-files.sh
./process-media-files.sh
```

Yes - the script doesn't actually do anything but generate a bash script. You can verify every step the generated script makes before executing on your video library.

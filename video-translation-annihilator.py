# video-translation-annihilator Copyright (C) 2020 Philip Butkiewicz <https://github.com/philipbutkiewicz>
# This program comes with ABSOLUTELY NO WARRANTY.
# This is free software, and you are welcome to redistribute it
# under certain conditions.

from argparse import ArgumentParser, BooleanOptionalAction
from pydantic import BaseModel, StringConstraints
from typing import Annotated, Optional, List, Dict, Any
from pathlib import Path
from tqdm import tqdm
from logging import info, error, INFO, StreamHandler, FileHandler
from logging import basicConfig as log_config
import subprocess
import os
import json
import pickle


class MediaFileInfo(BaseModel):
    container: Optional[Annotated[str, StringConstraints(pattern=r'mkv|mp4|avi|unknown')]] = ''
    audio_streams: Optional[List[Dict]] = []
    video_streams: Optional[List[Dict]] = []
    subtitle_streams: Optional[List[Dict]] = []

    @staticmethod
    def from_path(path: str) -> 'MediaFileInfo':
        if '.' not in path:
            raise ValueError(f'Cannot detect a container in path "{path}"')
        
        if not os.path.exists(path):
            raise FileNotFoundError(f'Cannot find media in path "{path}"')

        container = path.split('.')[-1].lower()
        if container not in ['mkv', 'mp4', 'avi']:
            return MediaFileInfo(container='unknown')
        
        audio_streams, video_streams, subtitle_streams = MediaFileInfo._read_ffmpeg_info(path)
        return MediaFileInfo(
            container=container,
            audio_streams=audio_streams,
            video_streams=video_streams,
            subtitle_streams=subtitle_streams
        )

    @staticmethod
    def _read_ffmpeg_info(path: str) -> tuple[List[Dict], List[Dict], List[Dict]]:
        def __stream_info(stream: str = 'v') -> List[Dict]:
            return json.loads(
                subprocess.check_output(
                    ['ffprobe', '-show_streams', '-select_streams', stream, '-v', 'quiet', '-of', 'json', path]
                )
            )['streams']

        return __stream_info(stream='a'), __stream_info(stream='v'), __stream_info(stream='s')


class MediaFile(BaseModel):
    path: str
    info: MediaFileInfo

    @staticmethod
    def from_path(path: str) -> 'MediaFile':
        return MediaFile(
            path=path,
            info=MediaFileInfo.from_path(path)
        )


def init() -> Dict[str, Any]:
    ap = ArgumentParser()
    ap.add_argument('-i', '--input-path', type=str, required=False, help='Input path.')
    ap.add_argument('-s', '--script-path', type=str, required=False, default='process-media-files.sh', help='Script output path.')
    ap.add_argument('-l', '--languages', type=str, required=True, help='Keep audio and subtitles only with selected languages (ie. jap,jpn,eng) or unknown. Comma separated.')
    ap.add_argument('-c', '--cached', action=BooleanOptionalAction, required=False, help='Resume from a cached file scan.')
    ap.add_argument('-v', '--verbose', action=BooleanOptionalAction, required=False, help='Output extra information to console.')

    args = vars(ap.parse_args())

    handlers=[
        FileHandler('app.log', encoding='utf-8'),
    ]

    if args.get('verbose'):
        handlers.append(StreamHandler())

    log_config(
        level=INFO,
        format='(%(asctime)s) %(message)s',
        datefmt='%m/%d/%Y %I:%M:%S %p',
        handlers=handlers
    )

    return args


def find_media_files(path: str, cached: bool = False) -> List[MediaFile]:
    media_files = []
    if os.path.exists('media.pickle') and cached:
        info('Starting from a cached file scan in "media.pickle"')
        with open('media.pickle', 'rb') as cf:
            media_files = pickle.load(cf)
    else:
        info(f'Searching for compatible files in "{path}"')
        input_files = []
        for ext in ['mkv', 'mp4', 'avi']:
            input_files.extend(list(Path(path).rglob(f'*.{ext}')))

        info(f'Reading stream info in {len(input_files)} file(s)')
        for file in tqdm(input_files, desc='read stream info'):
            try:
                media_files.append(MediaFile.from_path(str(file)))
            except Exception as e:
                error(e)

        info('Storing a cached file scan in "media.pickle"')
        with open('media.pickle', 'wb') as cf:
            pickle.dump(media_files, cf)
    
    return media_files


def process_media_files(media_files: List[MediaFile], languages: List[str]) -> str:
    def _map_streams(media_file: MediaFile, stream: str = 'audio') -> list[int]:
        _streams = []
        for _stream in media_file.info.audio_streams if stream == 'audio' else media_file.info.subtitle_streams:
            _stream_language = _stream['tags']['language'] if 'tags' in _stream and 'language' in _stream['tags'] else 'und'
            if not _stream_language == 'und' and _stream_language not in languages:
                info(f'{media_file.path} - delete {stream} stream: {_stream["index"]}:{_stream["codec_name"]}:{_stream_language}')
                _streams.append(_stream['index'])
        
        return _streams

    def _gen_cmdline(media_file: MediaFile, audio_stream_ids: List[int], subtitle_stream_ids: List[int]) -> List[str]:
        cmd = ['ffmpeg', '-i', media_file.path, '-map', '0', '-map']
        for audio_stream_id in audio_stream_ids:
            cmd.append(f'-0:a:{audio_stream_id}')
        for subtitle_stream_id in subtitle_stream_ids:
            cmd.append(f'-0:s:{subtitle_stream_id}')
        cmd += ['-c', 'copy', media_file.path.replace(media_file.info.container, f'cleaned.{media_file.info.container}')]

        return cmd

    script = '#!/bin/bash\n\n'
    for media_file in tqdm(media_files, desc='processing'):
        audio_stream_ids = _map_streams(
            media_file=media_file,
            stream='audio'
        )

        subtitle_stream_ids = _map_streams(
            media_file=media_file,
            stream='subtitle'
        )

        cmdline = _gen_cmdline(
            media_file=media_file,
            audio_stream_ids=audio_stream_ids,
            subtitle_stream_ids=subtitle_stream_ids
        )

        script += f'echo "Processing {media_file.path}..."\n'
        script += ' '.join([f'"{arg}"' if ' ' in arg else arg for arg in cmdline])
        script += '\n\n'

    return script


args = init()
if not args.get('input_path') and not args.get('cached'):
    error('You must provide --input-path or use --cached')
    exit(1)

media_files = find_media_files(
    path=args.get('input_path'),
    cached=args.get('cached')
)

info('Processing media')
script = process_media_files(
    media_files=media_files,
    languages=args.get('languages').split(',')
)

if os.path.exists(args.get('script_path')):
    os.remove(args.get('script_path'))

with open(args.get('script_path'), 'w', encoding='utf-8') as sf:
    sf.write(script)

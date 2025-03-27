# Discord Spotify Bot

Play Spotify music in Discord voice channels

## Features

- Play, pause, and skip Spotify tracks
- Display currently playing song
- Search and queue songs
- Share playlists
- Control volume

## Requirements
- Python 3.9 or later
- FFmpeg installed
- Spotify Developer account
- Discord bot token

## Installation

1. Clone the repository
2. Install dependencies: `npm install`
3. Set up environment variables (see Configuration section)
4. Run the bot: `npm start`

## Configuration

Create a `.env` file in the root directory with the following:
- DISCORD_TOKEN=your_discord_bot_token
- SPOTIFY_CLIENT_ID=your_spotify_client_id
- SPOTIFY_CLIENT_SECRET=your_spotify_client_secret

## Usage

- $login       - Connect your Spotify account
- $playlists   - List your Spotify playlists
- $play_track X Y - Play track Y from playlist X
- $nowplaying  - Show currently playing track
- $join        - Join your voice channel
- $leave       - Leave voice channel

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.


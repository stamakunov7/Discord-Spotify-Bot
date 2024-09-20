# Discord Spotify Bot

A Discord bot that integrates with Spotify, allowing users to control and share music within Discord servers.

## Features

- Play, pause, and skip Spotify tracks
- Display currently playing song
- Search and queue songs
- Share playlists
- Control volume

## Installation

1. Clone the repository
2. Install dependencies: `npm install`
3. Set up environment variables (see Configuration section)
4. Run the bot: `npm start`

## Configuration

Create a `.env` file in the root directory with the following:
DISCORD_TOKEN=your_discord_bot_token
SPOTIFY_CLIENT_ID=your_spotify_client_id
SPOTIFY_CLIENT_SECRET=your_spotify_client_secret

## Usage

- `/play <song name>`: Play a song
- `/pause`: Pause the current song
- `/resume`: Resume playback
- `/skip`: Skip to the next song
- `/nowplaying`: Display the current song
- `/queue <song name>`: Add a song to the queue

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.


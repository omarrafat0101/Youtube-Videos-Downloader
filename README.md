# YouTube Video/Playlist Downloader

A modern, user-friendly desktop application for downloading YouTube videos and playlists with quality selection and download management features.

```
YouTube video downloader with a modern dark-themed GUI. Download single videos or entire playlists, 
choose quality, track progress, and play videos directly from the app.
```

![Python](https://img.shields.io/badge/python-3.7+-blue.svg)

## ✨ Features

- 📹 Download single videos or entire playlists
- 🎬 Multiple quality options (360p, 480p, 720p, 1080p, Best)
- 📊 Real-time download progress tracking
- 🎨 Modern dark-themed interface
- ▶️ Play downloaded videos directly from the app
- 🔄 Automatic retry on failed downloads
- 📂 Custom download location


## 🔧 How It Works

### The Download Process

When you download a video from YouTube, here's what happens behind the scenes:

1. **URL Parsing**: The application extracts the video ID and metadata from the YouTube URL
2. **Format Selection**: Based on your quality preference, it requests the appropriate video format from YouTube's servers
3. **Stream Download**: The video is downloaded in chunks (fragments) to handle large files efficiently
4. **Progress Tracking**: Each downloaded chunk updates the progress bar so you can monitor the download
5. **File Assembly**: All chunks are combined into a single MP4 file saved to your chosen location

### Code Architecture

The application is built with two main classes:

#### `VideoDownloader` Class
- Manages individual video downloads using the `yt-dlp` library
- Handles format selection based on quality settings
- Implements retry logic (up to 5 attempts) for failed downloads
- Provides progress hooks to update the UI in real-time
- Runs downloads in separate threads to keep the interface responsive

**Key Features:**
- Non-blocking downloads using threading
- Automatic retry mechanism with exponential backoff
- Fragment-level error recovery
- Cancel/pause functionality

#### `PlaylistDownloaderApp` Class
- Creates the graphical user interface using Tkinter
- Manages multiple concurrent downloads
- Handles both single videos and playlists
- Provides video playback integration

**Key Components:**
- **URL Fetching**: Uses `yt-dlp` to extract video metadata without downloading
- **UI Threading**: All UI updates happen on the main thread for stability
- **Download Manager**: Tracks all active downloads using a dictionary
- **Scrollable List**: Dynamically displays videos with individual controls

### Technical Details

The downloader uses these key parameters:
- `format`: Selects the best available format matching your quality preference
- `progress_hooks`: Connects download progress to the UI progress bars
- `retry logic`: Automatically retries failed downloads up to 5 times
- `fragment_retries`: Handles individual chunk failures without restarting the entire download

## 🛠️ Technologies Used

- **Tkinter**: Cross-platform GUI framework
- **yt-dlp**: YouTube video extraction and download library
- **Threading**: Enables concurrent downloads without freezing the UI (My favourite)



## 🐛 Known Issues

- Some age-restricted or private videos may not be downloadable
- Very long playlist names might be truncated in the UI (You're welcome to fix this in the UI yourself if you want, I didn't have the time)

## 💡 Future Enhancements

- [ ] Audio-only download option
- [ ] Subtitle download support
- [ ] Download queue management
- [ ] Bandwidth throttling
- [ ] Video format conversion


---

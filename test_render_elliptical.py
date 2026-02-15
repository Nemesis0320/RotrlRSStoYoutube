def render_circular_waveform():
    log("Rendering circular waveform...")
    
    duration = get_audio_duration(TEST_AUDIO_FILE)
    log(f"Audio duration: {duration:.2f} seconds")
    
    # Test metadata
    episode_title = "Test File"
    season_label = "Season 1"
    episode_number = "0"
    ticker_text = f"{season_label} EP {episode_number}: {episode_title}"
    
    def ffmpeg_escape(text):
        return (
            text
            .replace("\\", "\\\\")
            .replace('"', '\\"')
            .replace(":", "\\:")
            .replace(",", "\\,")
        )
    
    safe_episode_title = ffmpeg_escape(episode_title)
    safe_season_ep = ffmpeg_escape(f"{season_label} EP {episode_number}")
    safe_ticker = ffmpeg_escape(ticker_text)
    
    # UPDATED: mode=p2p creates a smooth circular ring waveform
    filter_complex = f"""
        [0:v]scale={VIDEO_SIZE}[bg];
        [1:a]asplit[a_out][a_wave];
        [a_wave]showwaves=s={VIDEO_SIZE}:mode=p2p:rate={VIDEO_FPS}:colors=gold:scale=lin:draw=scale[wave];
        [bg][wave]overlay=0:0[bg_wave];
        [bg_wave]drawtext=fontfile={FONT_FILE}:text='{safe_episode_title}':x=(w-text_w)/2:y=120:fontsize=40:fontcolor=gold:shadowx=2:shadowy=2[bg_titleline];
        [bg_titleline]drawtext=fontfile={FONT_FILE}:text='{safe_season_ep}':x=(w-text_w)/2:y=180:fontsize=32:fontcolor=white:shadowx=2:shadowy=2[bg_ep];
        [bg_ep]drawtext=fontfile={FONT_FILE}:text='{safe_ticker}':x=w-mod(t*120\\,w+text_w):y=h-60:fontsize=26:fontcolor=white:shadowx=2:shadowy=2[final]
    """.replace("\n", " ")
    
    cmd = [
        "ffmpeg", "-y",
        "-loop", "1", "-t", str(duration), "-i", BG_IMAGE,
        "-i", TEST_AUDIO_FILE,
        "-filter_complex", filter_complex,
        "-map", "[final]",
        "-map", "[a_out]",
        "-r", str(VIDEO_FPS),
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-tune", "stillimage",
        "-crf", str(VIDEO_CRF),
        "-c:a", "aac",
        "-b:a", AUDIO_BITRATE,
        OUTPUT_VIDEO
    ]
    
    return run_cmd(cmd, capture=False)

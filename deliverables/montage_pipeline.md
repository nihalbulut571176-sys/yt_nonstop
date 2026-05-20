1. Таймлайн строится из:
`C:\Users\MIKE\Documents\Codex\YT\deliverables\sentence_blocks_from_srt.txt`

2. Готовые кадры берутся из:
`C:\Users\MIKE\Documents\Codex\YT\fastgen_run\images`

3. Аудио:
`C:\Users\MIKE\Documents\Codex\YT\assets\audio\message@elevenLabsVoicerBot.mp3`

4. Построить монтажный таймлайн:
`python C:\Users\MIKE\Documents\Codex\YT\scripts\build_slideshow_timeline.py`

5. Это создаст:
- `C:\Users\MIKE\Documents\Codex\YT\edit\timeline.ffconcat`
- `C:\Users\MIKE\Documents\Codex\YT\edit\timeline.json`

6. Отрендерить финальный ролик:
`powershell -ExecutionPolicy Bypass -File C:\Users\MIKE\Documents\Codex\YT\scripts\render_slideshow_video.ps1`

7. Результат:
`C:\Users\MIKE\Documents\Codex\YT\deliverables\final_video\telegram_darknet_final.mp4`

8. Что учтено:
- кадры идут строго по порядку `001–188`
- длительность каждого кадра берется из SRT-разбивки по предложениям
- последний кадр автоматически дотягивается до конца аудио
- черных экранов между кадрами быть не должно
- экспорт идет в стандартный `yuv420p` для нормальной совместимости
9. Technical note:
- The current fixed edit uses `274` ordered shots, not `188`.
- Any SRT segment longer than `5` seconds must be split into multiple shots before image generation.
- Final montage should always be rebuilt from the updated `timeline.json` and `timeline.ffconcat`.

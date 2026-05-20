1. Add your API key to:
`C:\Users\MIKE\Documents\Codex\YT\.env`

2. Use the key name:
`VEO_NONSTOP_API_KEY`

3. Main animation script:
`C:\Users\MIKE\Documents\Codex\YT\scripts\veononstop_image_to_video.py`

4. The script reads shots from:
`C:\Users\MIKE\Documents\Codex\YT\edit\timeline.json`

5. It sends one `image-to-video` task per shot to:
`https://veononstop.org/api/v1/video/image-to-video`

6. It keeps the project order and saves outputs as:
`001.mp4 ... 274.mp4`

7. Output folder:
`C:\Users\MIKE\Documents\Codex\YT\veononstop_run\videos`

8. Metadata folder:
`C:\Users\MIKE\Documents\Codex\YT\veononstop_run\meta`

9. Resume behavior:
- existing `.mp4` files are skipped
- rerun the script to continue after interruption

10. Failure logs:
`C:\Users\MIKE\Documents\Codex\YT\veononstop_run\failed.jsonl`

11. Success logs:
`C:\Users\MIKE\Documents\Codex\YT\veononstop_run\success.jsonl`

12. Timeout handling:
- `HTTPSConnectionPool(...): Read timed out` is treated as retryable
- this is especially important for long-running or overloaded tasks
- during polling, timeout does not kill the job; the script reconnects and keeps waiting

13. Default motion behavior:
- preserve the original frame composition
- no camera zoom
- no reframing
- no identity drift
- no extra objects or text

14. Request note:
- `image-to-video` should be sent without a `duration` field unless the API docs explicitly support it for that route
- current default is to omit `duration`

15. Example test run:
`python C:\Users\MIKE\Documents\Codex\YT\scripts\veononstop_image_to_video.py --start 1 --end 3`

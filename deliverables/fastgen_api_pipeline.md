1. Заполни API key в:
`C:\Users\MIKE\Documents\Codex\YT\.env`

2. Скопируй шаблон:
`C:\Users\MIKE\Documents\Codex\YT\deliverables\fastgen_ref_paths.template.json`

в файл:
`C:\Users\MIKE\Documents\Codex\YT\deliverables\fastgen_ref_paths.json`

3. В `fastgen_ref_paths.json` укажи реальные абсолютные пути к 6 reference images.

4. Скрипт генерации:
`C:\Users\MIKE\Documents\Codex\YT\scripts\fastgen_openai_v4_generate.py`

5. Что делает скрипт:
- читает `sentence_visual_prompts_generator_ready.md`
- убирает из текста технические префиксы `Use reference image...`
- загружает референсы в storage.fast-gen.ai
- создает image operations на `/api/v4/openai/image/generate`
- для кадров с рефами отправляет `reference_images: ["file:..."]`
- ждет готовности через `/api/v4/operations/{operation_id}`
- сразу сохраняет изображения в правильном порядке как `001.png ... 188.png`

6. Базовый запуск:
`python C:\Users\MIKE\Documents\Codex\YT\scripts\fastgen_openai_v4_generate.py`

7. Результат будет здесь:
`C:\Users\MIKE\Documents\Codex\YT\fastgen_run\images`

8. Метаданные и операции будут здесь:
`C:\Users\MIKE\Documents\Codex\YT\fastgen_run\meta`

9. Кэш референсов будет здесь:
`C:\Users\MIKE\Documents\Codex\YT\fastgen_run\ref_cache.json`

10. Manifest текущего запуска:
`C:\Users\MIKE\Documents\Codex\YT\fastgen_run\run_manifest.json`

11. Возобновление после остановки:
- скрипт пропускает уже существующие `001.png`, `002.png` и так далее
- можно просто запустить его повторно

12. Запуск диапазона для теста:
`python C:\Users\MIKE\Documents\Codex\YT\scripts\fastgen_openai_v4_generate.py --start 1 --end 5`

13. Важная оговорка:
- сейчас скрипт сохраняет первый результат из массива `result[0]`
- если позже захочешь несколько вариантов на кадр, это можно расширить
14. Technical note:
- Fast Gen API can accept multiple reference images in a single request.
- For this project, treat `reference_images` as supporting up to `10` refs per shot when scene consistency requires it.
- Do not assume only one ref per prompt in future runs.

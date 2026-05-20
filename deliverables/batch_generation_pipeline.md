1. Источник промптов:
`C:\Users\MIKE\Documents\Codex\YT\deliverables\sentence_visual_prompts_generator_ready.md`

2. Разбей промпты на группы:
`python C:\Users\MIKE\Documents\Codex\YT\scripts\split_prompts_by_reference.py`

3. После запуска появится папка:
`C:\Users\MIKE\Documents\Codex\YT\deliverables\prompt_batches`

В ней будут:
- `manifest.json` — главный файл порядка кадров
- `SUMMARY.txt` — сколько промптов в каждой группе
- отдельные `.txt` и `.csv` файлы по группам

4. Для генерации используй `.txt` по группам:
- `CHAR_01_Journalist.txt`
- `CHAR_02_CrimeBoss.txt`
- `CHAR_03_TeenageRecruit.txt`
- `CHAR_04_FounderEngineer.txt`
- `CHAR_05_CryptophoneEntrepreneur.txt`
- `CHAR_06_IntelligenceAnalyst.txt`
- `NO_REF.txt`

5. После генерации сложи картинки в папки с теми же именами, например:
- `C:\Users\MIKE\Documents\Codex\YT\generated\CHAR_01_Journalist`
- `C:\Users\MIKE\Documents\Codex\YT\generated\CHAR_02_CrimeBoss`
- `C:\Users\MIKE\Documents\Codex\YT\generated\CHAR_03_TeenageRecruit`
- `C:\Users\MIKE\Documents\Codex\YT\generated\CHAR_04_FounderEngineer`
- `C:\Users\MIKE\Documents\Codex\YT\generated\CHAR_05_CryptophoneEntrepreneur`
- `C:\Users\MIKE\Documents\Codex\YT\generated\CHAR_06_IntelligenceAnalyst`
- `C:\Users\MIKE\Documents\Codex\YT\generated\NO_REF`

6. Важно:
- внутри каждой папки изображения должны лежать в том же порядке, в котором сервис сгенерировал промпты из соответствующего `.txt`
- лучше не переименовывать их вручную
- в одной папке должны лежать только изображения одной группы

7. Когда все готово, собери в одну итоговую папку:
`python C:\Users\MIKE\Documents\Codex\YT\scripts\reassemble_generated_images.py --manifest C:\Users\MIKE\Documents\Codex\YT\deliverables\prompt_batches\manifest.json --generated-root C:\Users\MIKE\Documents\Codex\YT\generated --output C:\Users\MIKE\Documents\Codex\YT\generated_final`

8. Результат:
- в `C:\Users\MIKE\Documents\Codex\YT\generated_final` появятся файлы `001`, `002`, `003` ... `188`
- порядок будет восстановлен по исходному сценарию, а не по папкам

9. Важная оговорка:
- если сервис в какой-то группе пропустит кадр или выдаст лишний кадр, сборщик остановится с ошибкой и покажет, в какой группе не совпало количество
- это хорошо, потому что не даст молча перемешать монтажный порядок

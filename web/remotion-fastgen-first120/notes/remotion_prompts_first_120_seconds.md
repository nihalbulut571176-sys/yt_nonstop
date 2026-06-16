# Remotion Prompts — первые 120 секунд видео

**Проект:** «Иллюзия выбора»  
**Фрагмент:** 00:00–02:00  
**Формат:** 16:9  
**Рекомендуемый FPS:** 30 fps  
**Общий принцип:** не делать просто слайд-шоу из красивых картинок. Каждая сцена должна иметь понятное движение, смысловой акцент, короткий текст на экране и переход в следующую сцену.

---

## MASTER PROMPT ДЛЯ REMOTION

Ты — senior Remotion developer, motion designer и режиссёр документальной графики.

Нужно собрать первые 120 секунд видео по сценам S01–S10. Используй заранее сгенерированные изображения как layered assets: background, midground, foreground, typography overlay, motion graphics overlay. Не добавляй текст внутрь изображений — весь текст должен быть отдельными Remotion-слоями.

Визуальный стиль: investigative documentary, cinematic realism, холодный супермаркетный свет, тёмные индустриальные тени, restrained motion, clean visual hierarchy, subtle data overlays, scanner sweeps, parallax push, x-ray reveal, funnel-flow, documentary captions.

Главная метафора первых 120 секунд: зритель начинает у яркой полки супермаркета, но камера постепенно вскрывает скрытую систему за этой полкой: лаборатории, зерновые терминалы, мясокомбинаты, переговорные комнаты, узкие ворота контроля и исторический контраст с локальной едой.

Требования:
- Composition: 1920x1080, 16:9.
- FPS: 30.
- Продолжительность сегмента: 120 секунд / 3600 frames.
- Все сцены должны быть отдельными компонентами: `SceneS01`, `SceneS02`, ... `SceneS10`.
- Все сцены должны подключаться в одном `Sequence` timeline.
- Используй easing, но избегай рекламной глянцевой динамики.
- Основной тип движения: slow push-in, parallax, scanner sweep, mask reveal, x-ray reveal, match cut, carry-over motion.
- Typography: короткие акценты, не субтитры. Не дублировать всю озвучку.
- Цвет: cold teal / graphite / muted amber highlights.
- Использовать vignette и grain очень умеренно.
- Не использовать реальные бренды, логотипы, знаменитостей, агрессивную конспирологическую эстетику.

---

## GLOBAL COMPONENTS

Рекомендуемые reusable components:

```text
SceneWrapper
ParallaxImage
AnimatedCaption
ScannerSweep
XRayReveal
EvidenceCard
SupplyChainLine
FunnelFlow
StageSpotlight
DocumentaryLabel
VignetteOverlay
FilmGrainOverlay
MatchCutTransition
```

---

## GLOBAL ASSET NAMING

```text
/assets/S01/supermarket_aisle_bg.png
/assets/S01/cart_foreground.png
/assets/S01/scanner_sweep.png

/assets/S02/glass_maze_bg.png
/assets/S02/shopper_silhouette.png
/assets/S02/maze_wall_layer.png

/assets/S03/supply_chain_collage_bg.png
/assets/S03/lab_layer.png
/assets/S03/grain_terminal_layer.png
/assets/S03/meat_processing_layer.png
/assets/S03/negotiation_room_layer.png

/assets/S04/evidence_wall_bg.png
/assets/S04/evidence_cards.png
/assets/S04/thread_lines.png

/assets/S05/funnel_gate_bg.png
/assets/S05/product_particles.png
/assets/S05/commodity_particles.png
/assets/S05/industrial_gate.png

/assets/S06/supermarket_theater_bg.png
/assets/S06/product_actors.png
/assets/S06/stage_spotlight.png

/assets/S07/backstage_corridor_bg.png
/assets/S07/backstage_door.png
/assets/S07/industrial_distance_layers.png

/assets/S08/ancient_food_world_bg.png
/assets/S08/grain_hands.png
/assets/S08/rain_sun_overlay.png

/assets/S09/local_market_bg.png
/assets/S09/farmer_layer.png
/assets/S09/miller_layer.png
/assets/S09/butcher_layer.png
/assets/S09/bread_basket_layer.png

/assets/S10/bread_origin_bg.png
/assets/S10/bread_loaf.png
/assets/S10/origin_line.png
```

---

# SCENE PROMPTS

---

## S01 — 00:00–00:10

**Frame range:** 0–300  
**Start phrase:** «Ты стоишь перед полкой супермаркета.»  
**End phrase:** «Кажется, выбора слишком много.»

### Goal
Создать первое ощущение: зритель находится прямо перед полкой, где слишком много товаров. Кадр должен быть реалистичным, немного перегруженным, но не хаотичным.

### Text overlay
```text
КАЖЕТСЯ, ВЫБОРА СЛИШКОМ МНОГО
```

Текст появляется не сразу, а ближе к концу сцены.

### Remotion prompt
Создай компонент `SceneS01_SupermarketChoice` длительностью 10 секунд. Используй full-screen background supermarket aisle. Добавь foreground shopping cart handle как отдельный слой. Сделай медленный cinematic push-in: background scale 1.0 → 1.08, foreground cart scale 1.0 → 1.03, чтобы появился parallax. На 3-й секунде проведи subtle scanner sweep слева направо по полкам. На 6-й секунде слегка усили визуальную плотность: shelves можно немного затемнить по краям и добавить мягкое ощущение давления через vignette. На 7.5 секунде выведи короткий typography accent. На 9-й секунде затемни края и подготовь match cut в glass maze сцену.

### Animation sequence
```text
0.0–1.5 sec: fade in from black, supermarket light turns on subtly.
1.5–3.0 sec: slow push-in begins, cart handle appears as foreground anchor.
3.0–4.2 sec: scanner sweep crosses shelves left to right.
4.2–6.5 sec: product rows feel denser through parallax and slight vignette.
6.5–8.5 sec: text appears with restrained sharp reveal.
8.5–10.0 sec: text holds, edges darken, prepare match cut.
```

### Components
```text
SceneWrapper
ParallaxImage
ScannerSweep
AnimatedCaption
VignetteOverlay
FilmGrainOverlay
```

### Transition out
Match cut into S02: shelf geometry becomes glass maze geometry.

### Do not
Не делать весёлую рекламную полку. Не использовать яркие бренды. Не выводить всю озвучку субтитрами.

---

## S02 — 00:10–00:18

**Frame range:** 300–540  
**Start phrase:** «Кажется, современный человек впервые в истории свободен решать, что положить в корзину.»  
**End phrase:** «Но это иллюзия.»

### Goal
Показать, что свобода выбора превращается в лабиринт. Сцена должна быть психологической, но не фантастической.

### Text overlay
```text
НО ЭТО ИЛЛЮЗИЯ
```

### Remotion prompt
Создай компонент `SceneS02_ChoiceIllusion` длительностью 8 секунд. Начни с похожей геометрии полок из S01, но через mask reveal постепенно наложи glass maze layer. Маленький shopper silhouette стоит перед несколькими проходами, которые выглядят разными, но визуально ведут в одну глубину. Камера медленно push-in: scale 1.0 → 1.06. На слове «иллюзия» сделай короткий visual impact: glass reflections briefly align, проходы становятся похожими, текст появляется резким reveal. Motion должен быть restrained, не horror.

### Animation sequence
```text
0.0–1.0 sec: continue motion from S01, shelf lines remain visible.
1.0–3.0 sec: glass maze walls appear via opacity + mask reveal.
3.0–5.2 sec: shopper silhouette becomes visible, paths look repetitive.
5.2–6.3 sec: impact on “иллюзия”: reflections snap into alignment.
6.3–8.0 sec: text holds, background slightly darkens for transition.
```

### Components
```text
SceneWrapper
ParallaxImage
XRayReveal
AnimatedCaption
VignetteOverlay
```

### Transition out
Hard-but-clean cut into S03, as if camera breaks through the supermarket wall.

### Do not
Не превращать сцену в sci-fi лабиринт. Не использовать слишком абстрактные neon tunnels.

---

## S03 — 00:18–00:32

**Frame range:** 540–960  
**Start phrase:** «Самое важное решение уже было принято до того, как ты вошёл в магазин.»  
**End phrase:** «Кто на самом деле выбирает нашу еду?»

### Goal
Вскрыть скрытые места принятия решений: лаборатория, зерновой терминал, мясокомбинат, переговорная комната. Показываем не злодеев, а инфраструктуру.

### Text overlay
```text
РЕШЕНИЕ УЖЕ ПРИНЯТО
```

Дополнительный маленький caption:
```text
до входа в магазин
```

### Remotion prompt
Создай компонент `SceneS03_DecisionBeforeStore` длительностью 14 секунд. Используй supermarket shelf foreground как полупрозрачную переднюю плоскость. За ней через x-ray reveal покажи layered supply chain collage: laboratory, grain terminal, meat processing corridor, negotiation room. Соедини их тонкими supply chain lines. Движение камеры: slow push through shelf, затем drift по слоям слева направо. Каждый скрытый узел появляется по очереди на соответствующей фразе. На финальном вопросе «кто на самом деле выбирает нашу еду?» все линии сходятся в один central node без логотипа.

### Animation sequence
```text
0.0–2.0 sec: supermarket foreground remains visible, background is dark.
2.0–4.5 sec: lab layer appears behind shelf through x-ray reveal.
4.5–6.8 sec: grain terminal layer appears, supply chain line connects.
6.8–9.0 sec: meat processing layer appears, line continues.
9.0–11.2 sec: negotiation room appears, no readable documents.
11.2–13.0 sec: all lines converge toward central invisible decision point.
13.0–14.0 sec: question text appears, hold for impact.
```

### Components
```text
SceneWrapper
XRayReveal
SupplyChainLine
ParallaxImage
AnimatedCaption
DocumentaryLabel
```

### Transition out
Lines from hidden nodes become thread lines of the evidence wall in S04.

### Do not
Не показывать конкретные корпорации, логотипы, злодейские лица или конспирологический underground room.

---

## S04 — 00:32–00:45

**Frame range:** 960–1350  
**Start phrase:** «Это расследование не про один злой логотип.»  
**End phrase:** «Всё сложнее. И именно поэтому опаснее.»

### Goal
Сразу убрать карикатуру про “одного злодея” и показать сложность системы. Визуально — investigative wall, но без дешёвой conspiracy эстетики.

### Text overlay
```text
НЕ ОДИН ЛОГОТИП
```

Затем заменить на:
```text
СЛОЖНЕЕ = ОПАСНЕЕ
```

### Remotion prompt
Создай компонент `SceneS04_NotOneLogo` длительностью 13 секунд. Используй dark evidence wall. В начале в центре появляется один blank corporate placeholder, но он быстро распадается на сеть нейтральных evidence cards. Каждая карточка — не бренд, а узел: seeds, grain, processing, retail, advertising. Текст «НЕ ОДИН ЛОГОТИП» появляется в начале, затем на 8-й секунде заменяется на «СЛОЖНЕЕ = ОПАСНЕЕ». Motion: mechanical reveal, thin thread lines, subtle data pulses. Никаких реальных названий и логотипов.

### Animation sequence
```text
0.0–2.0 sec: one central blank card appears under narrow spotlight.
2.0–4.5 sec: central card splits into multiple evidence cards.
4.5–7.5 sec: thread lines connect cards, showing system complexity.
7.5–9.5 sec: first text fades, second text stamps in.
9.5–12.0 sec: data pulses travel across network.
12.0–13.0 sec: camera pushes into one line that becomes the gate path of S05.
```

### Components
```text
SceneWrapper
EvidenceCard
SupplyChainLine
AnimatedCaption
VignetteOverlay
```

### Transition out
Carry-over motion: one evidence line stretches forward and morphs into the narrow gate perspective of S05.

### Do not
Не делать красную ниточную доску как в конспирологическом триллере. Не использовать слова “заговор” на экране.

---

## S05 — 00:45–01:07

**Frame range:** 1350–2010  
**Start phrase:** «На витрине мы видим тысячи брендов, но за витриной есть узкие ворота.»  
**End phrase:** «А у покупателя остаётся только ощущение свободы.»

### Goal
Ключевая сцена первых двух минут. Нужно визуально показать “узкие ворота”, через которые проходит вся система: семена, зерно, корма, мясо, сахар, масла, упаковка, рекламные смыслы.

### Text overlay
```text
УЗКИЕ ВОРОТА
```

Secondary labels, по одному, коротко:
```text
семена
зерно
корма
мясо
сахар
масла
упаковка
смыслы
```

### Remotion prompt
Создай компонент `SceneS05_NarrowGate` длительностью 22 секунды. Используй bright supermarket display as foreground, за ним dark industrial bottleneck gate. В начале зритель видит множество generic packages. Затем камера проходит за витрину, и товары/сырьевые частицы начинают funnel-flow в один узкий industrial gate. Добавь label chips для категорий: seeds, grain, feed, meat, sugar, oils, packaging, advertising meanings. Движение должно быть неизбежным: объекты не хаотично летят, а как поток сжимаются в горловину. На фразе про фермера, магазин и покупателя сделай три коротких visual beats: farmer alternative closes, store maneuver space narrows, buyer freedom becomes only a glowing outline.

### Animation sequence
```text
0.0–3.0 sec: bright shelf foreground, many product packages, slow push-in.
3.0–5.5 sec: shelf becomes transparent, dark gate appears behind it.
5.5–10.0 sec: commodity particles flow toward the gate: seeds, grain, feed, meat, sugar, oils.
10.0–13.5 sec: packaging and advertising-meaning particles join the flow.
13.5–16.5 sec: gate narrows visually, flow compresses.
16.5–18.5 sec: farmer option path closes with a subtle line collapse.
18.5–20.0 sec: store maneuver area shrinks as rectangular frame tightens.
20.0–22.0 sec: buyer freedom remains as a thin glowing outline, then fades.
```

### Components
```text
SceneWrapper
FunnelFlow
ParallaxImage
DocumentaryLabel
AnimatedCaption
SupplyChainLine
VignetteOverlay
```

### Transition out
Industrial gate opens like stage curtains into S06 supermarket theater.

### Do not
Не перегружать сцену десятками иконок. Лучше 8 категорий через аккуратные label chips. Не использовать реальные изображения мяса с gore.

---

## S06 — 01:07–01:18

**Frame range:** 2010–2340  
**Start phrase:** «Запомни эту картинку: супермаркет как театр.»  
**End phrase:** «Бренды — актёры.»

### Goal
Создать запоминаемую визуальную метафору: полки — сцена, бренды — актёры. Сцена должна быть красивой, но с тревожным подтекстом.

### Text overlay
```text
СУПЕРМАРКЕТ КАК ТЕАТР
```

Затем маленькие labels:
```text
полки = сцена
бренды = актёры
```

### Remotion prompt
Создай компонент `SceneS06_SupermarketTheater` длительностью 11 секунд. Начни с dark industrial gate из S05, который открывается как театральный занавес. За ним появляется supermarket aisle transformed into stage. Product packages стоят как актёры под spotlights. Полки работают как stage wings. Используй warm stage light поверх cold supermarket light. Текст появляется documentary-caption style, не как рекламный заголовок. Камера плавно отъезжает, раскрывая сцену целиком.

### Animation sequence
```text
0.0–1.5 sec: gate/curtain opens from center.
1.5–3.5 sec: supermarket stage appears, spotlights turn on.
3.5–5.5 sec: text “СУПЕРМАРКЕТ КАК ТЕАТР” fades in.
5.5–8.0 sec: labels point to shelves and product actors.
8.0–10.0 sec: camera pulls back slightly, audience darkness appears foreground.
10.0–11.0 sec: spotlight beam becomes corridor light for S07.
```

### Components
```text
SceneWrapper
StageSpotlight
ParallaxImage
AnimatedCaption
DocumentaryLabel
VignetteOverlay
```

### Transition out
Spotlight beam stretches into backstage corridor light.

### Do not
Не делать сцену комичной. Продукты не должны иметь лица, руки или мультяшность.

---

## S07 — 01:18–01:32

**Frame range:** 2340–2760  
**Start phrase:** «Но сценарий написан не здесь.»  
**End phrase:** «Имена которых ты даже не знаешь.»

### Goal
Показать, что “сценарий” написан за пределами полки: в местах, куда зритель не попадает. Визуально камера уходит за сцену, затем дальше — к индустриальным узлам.

### Text overlay
```text
СЦЕНАРИЙ НАПИСАН НЕ ЗДЕСЬ
```

Secondary caption:
```text
раньше, глубже, дальше от полки
```

### Remotion prompt
Создай компонент `SceneS07_BackstageSystem` длительностью 14 секунд. Начни с supermarket theater stage from behind. Камера проходит через backstage door. За дверью длинный corridor, в конце которого слоями видны laboratory, factory, grain silos, corporate meeting room. Используй parallax depth: foreground door moves быстрее, distant industrial layers медленнее. На фразе про простой продукт на столе покажи маленький dinner plate/bread object в нижнем foreground, а от него тонкая line уходит назад в industrial distance. На финале затемни неизвестные corporate silhouettes без логотипов.

### Animation sequence
```text
0.0–2.0 sec: camera behind the supermarket stage, backstage door visible.
2.0–4.5 sec: door opens, corridor appears.
4.5–7.5 sec: camera travels through corridor, industrial layers appear in depth.
7.5–10.5 sec: simple food plate appears foreground, line connects it to distant nodes.
10.5–12.5 sec: anonymous decision silhouettes appear as dark shapes, no faces.
12.5–14.0 sec: text holds, corridor fades into warm historical field.
```

### Components
```text
SceneWrapper
ParallaxImage
SupplyChainLine
AnimatedCaption
XRayReveal
VignetteOverlay
```

### Transition out
Dip / morph: dark corridor fades into warm dawn field of S08.

### Do not
Не показывать конкретных руководителей, кабинеты с логотипами, злодейские силуэты. Смысл — структура, не персональная атака.

---

## S08 — 01:32–01:46

**Frame range:** 2760–3180  
**Start phrase:** «Начнём с того, что еда долгое время казалась чем-то слишком древним, чтобы её можно было монополизировать.»  
**End phrase:** «Всё это выглядело как мир, который невозможно полностью упаковать в корпоративную систему.»

### Goal
Смена темпа. После тёмной системы показать древний, земной, почти архетипический мир еды: земля, дождь, солнце, труд, урожай.

### Text overlay
```text
ЕДА КАЗАЛАСЬ СЛИШКОМ ДРЕВНЕЙ
```

Secondary words appearing softly:
```text
земля / дождь / солнце / труд / урожай
```

### Remotion prompt
Создай компонент `SceneS08_AncientFoodWorld` длительностью 14 секунд. Используй warm rural landscape at dawn. Движение должно резко замедлиться по сравнению с S05–S07. Камера делает slow push-in к рукам с зерном и полю. Слова “земля, дождь, солнце, труд, урожай” появляются не как заголовки, а как мягкие documentary labels, синхронно с озвучкой. Добавь subtle rain/sun overlay. Сцена должна ощущаться как историческая память до корпоративной упаковки.

### Animation sequence
```text
0.0–2.0 sec: warm dawn field fades in from dark corridor.
2.0–4.5 sec: hands with grain appear foreground through soft reveal.
4.5–8.0 sec: labels earth/rain/sun/labor/harvest appear one by one.
8.0–11.5 sec: slow push-in, natural particles drift, no hard motion.
11.5–14.0 sec: composition widens slightly to prepare local market transition.
```

### Components
```text
SceneWrapper
ParallaxImage
DocumentaryLabel
AnimatedCaption
FilmGrainOverlay
```

### Transition out
Warm dissolve / match cut from grain in hands to grain/bread at local market.

### Do not
Не делать пасторальную открытку. Кадр должен быть красивым, но документальным, не рекламой фермерского продукта.

---

## S09 — 01:46–01:55

**Frame range:** 3180–3450  
**Start phrase:** «На протяжении веков человек выращивал, обменивал, молол, солил, сушил, продавал.»  
**End phrase:** «Но в них было главное: много независимых участников.»

### Goal
Показать локальный рынок как сеть многих независимых участников. Важно не романтизировать: он хаотичный и несовершенный, но разнообразный.

### Text overlay
```text
МНОГО НЕЗАВИСИМЫХ УЧАСТНИКОВ
```

Small labels:
```text
фермер
мельник
мясник
покупатель
```

### Remotion prompt
Создай компонент `SceneS09_LocalMarketParticipants` длительностью 9 секунд. Используй historical local market background. Размести layered characters: farmer, miller, butcher, bread seller, buyers. Движение — gentle parallax, slight handheld documentary feel, no modern logos. По мере перечисления действий можно коротко подсветить разные участки рынка: grow, exchange, mill, salt, dry, sell. На финале линии между участниками образуют открытую сеть, не funnel.

### Animation sequence
```text
0.0–1.5 sec: local market appears via warm dissolve.
1.5–3.5 sec: camera drift across stalls, subtle parallax.
3.5–6.0 sec: labels highlight farmer, miller, butcher, buyer.
6.0–8.0 sec: open network lines connect many participants.
8.0–9.0 sec: camera settles on bread / market table for S10.
```

### Components
```text
SceneWrapper
ParallaxImage
DocumentaryLabel
SupplyChainLine
AnimatedCaption
```

### Transition out
Match cut from market bread basket to close-up bread loaf in S10.

### Do not
Не делать рынок слишком чистым или сказочным. Нужна умеренная хаотичность, но без грязи и жестокости.

---

## S10 — 01:55–02:00

**Frame range:** 3450–3600  
**Start phrase:** «Фермер мог сохранить часть семян.»  
**End phrase:** «Покупатель видел, откуда приходит хлеб.»

### Goal
Завершить первые 120 секунд спокойным, ясным образом видимого происхождения еды. Это контраст с будущей индустриальной невидимостью.

### Text overlay
```text
ВИДИМОЕ ПРОИСХОЖДЕНИЕ
```

Optional secondary caption:
```text
поле → мельница → рынок → хлеб
```

### Remotion prompt
Создай компонент `SceneS10_VisibleOrigin` длительностью 5 секунд. Используй close-up bread loaf on market table. В background мягко видны field, mill, market as lineage layers. Анимируй thin origin line от поля к мельнице, затем к рынку, затем к хлебу. Камера почти статична, только очень медленный push-in. Текст должен появиться тихо и держаться до конца сегмента. Финальный кадр должен подготовить переход к следующей части: «Но в двадцатом веке еда перестала быть просто урожаем. Она стала потоком.» Поэтому в самом конце origin line начинает слегка растягиваться и превращаться в flow line.

### Animation sequence
```text
0.0–1.0 sec: match cut from bread basket to bread loaf close-up.
1.0–2.5 sec: origin line traces field → mill → market.
2.5–3.8 sec: line reaches bread loaf, text appears softly.
3.8–5.0 sec: hold; line begins to transform into flow line for next section.
```

### Components
```text
SceneWrapper
ParallaxImage
SupplyChainLine
AnimatedCaption
DocumentaryLabel
```

### Transition out
For the next scene after 02:00, transform origin line into industrial flow line.

### Do not
Не перегружать финал инфографикой. Это короткая спокойная фиксация перед переходом к XX веку.

---

# FINAL ASSEMBLY PROMPT

Use this prompt if generating implementation from the full scene list:

```text
Build a Remotion sequence for the first 120 seconds of a 16:9 documentary video. Use 30 fps and create ten scene components: S01 to S10. Each scene should use generated still images as layered assets and animate them with parallax, scanner sweeps, x-ray reveals, funnel-flow, documentary labels, and restrained cinematic camera motion.

The video starts in a supermarket aisle, turns the shelf into a psychological maze, reveals hidden supply-chain decision points, rejects the idea of a single villain, introduces the metaphor of narrow gates behind the shelf, transforms the supermarket into theater, moves backstage into hidden industrial spaces, then shifts into a warm historical food world with local independent participants, ending on a bread loaf whose origin is visible.

Do not create subtitles for the full voiceover. Use only short typography accents. Do not use real brands, logos, celebrity faces, readable documents, or conspiracy-style visuals. All text must be rendered in Remotion, not inside images. The tone should be investigative, cinematic, restrained, and serious.
```

---

# CHECKLIST BEFORE IMPLEMENTATION

- [ ] Confirm final FPS: 30 or 25.
- [ ] Replace approximate scene timings with SRT when available.
- [ ] Keep all image assets unbranded.
- [ ] Add all text in Remotion.
- [ ] Use one visual language across all scenes.
- [ ] Avoid over-animating every layer.
- [ ] Keep S05 as the strongest visual beat in the first 120 seconds.
- [ ] Keep S10 clean and calm to prepare the next section.

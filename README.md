# Програмний проєкт
## Виконала: Анастасія Гопко, ТТП-32.

## Обрані завдання

| ID      | Завдання                                                    | Бали | Де реалізовано |
|---------|-------------------------------------------------------------|-----:|----------------|
| CORE-01 | Формальна специфікація: машинозчитувана граматика (Lark)    | 0.5  | [`src/sipl/grammar/sipl.lark`](src/sipl/grammar/sipl.lark), [розділ «Граматика та лексика»](#граматика-та-лексика), [`examples/`](examples) |
| CORE-02 | Парсер і типізоване AST з `SourceSpan`                      | 1.5  | [`parser.py`](src/sipl/parser.py), [`ast.py`](src/sipl/ast.py), [`parse_tree.py`](src/sipl/parse_tree.py) |
| CORE-03 | Інтерпретатор: стан, присвоювання, `;`, if, while, begin/end, skip | 2.0  | [`interpreter/`](src/sipl/interpreter) |
| CORE-04 | Подієва модель виконання та trace                            | 1.0  | [`interpreter/events.py`](src/sipl/interpreter/events.py) |
| CORE-05 | CLI: parse, check, run, trace (+ JSON-режим)                 | 1.0  | [`cli.py`](src/sipl/cli.py), [розділ «JSON-режим»](#json-режим) |
| VIS-01  | Візуалізація дерева синтаксичного виводу: text, JSON, DOT, SVG | 1.5  | [`visualization/`](src/sipl/visualization) |
| VIS-02  | Візуалізація AST і порівняння «parse tree ↔ AST» (HTML)      | 1.0  | [`visualization/html.py`](src/sipl/visualization/html.py) |
| SEM-01  | Автоматична побудова семантичного терму SIPL-програми      | 2.0  | [`semantics/`](src/sipl/semantics) |
|         | **Разом заявлено**                                          | **10.5** | до оцінки зараховується не більше 10 |

## Встановлення

Потрібен Python 3.10 або новіший.

```bash
git clone https://github.com/hopko-anastasiya/TP_Project.git
cd TP_Project
python -m venv .venv
# Windows:  .venv\Scripts\activate      Linux/macOS:  source .venv/bin/activate
pip install -e ".[dev]"
```

Після цього доступна команда `sipl` (або `python -m sipl`). Єдина залежність для роботи — `lark`.
Для тестів додатково встановлюються `pytest`, `pytest-cov`, `jsonschema`.

## Швидкий старт

```bash
sipl check examples/power.sipl
sipl run   examples/power.sipl -s X=5,Y=2
sipl trace examples/power.sipl -s X=5,Y=2
sipl term  examples/power.sipl --explain
sipl tree  examples/power.sipl -f leaves
sipl visualize examples/power.sipl -o power.html
```

Приклад програми (`examples/power.sipl`):

```
begin
  R := 1;
  while Y > 0 do
  begin
    R := R * X;
    Y := Y - 1
  end
end
```

Результати:

```text
$ sipl run examples/power.sipl -s X=5,Y=2
[X ↦ 5, Y ↦ 0, R ↦ 25]

$ sipl term examples/power.sipl
AS^R(1) · WH(S2(gr, Y⇒, 0), AS^R(S2(mult, R⇒, X⇒)) · AS^Y(S2(sub, Y⇒, 1)))

$ sipl tree examples/power.sipl -f leaves
1 begin 2 R 3 := 4 1 5 ; 6 while 7 Y 8 > 9 0 10 do 11 begin 12 R 13 := 14 R 15 * 16 X 17 ; 18 Y 19 := 20 Y 21 - 22 1 23 end 24 end

$ sipl check examples/invalid/trailing_semicolon.sipl
examples/invalid/trailing_semicolon.sipl:5:1: помилка: неочікувана лексема 'end'; очікувалось: 'begin', 'if', 'skip', 'while', змінна (у SIPL ';' розділяє оператори, тому перед 'end' вона не ставиться)
  end
  ^^^
```

## Граматика та лексика

Машинозчитувана граматика — [`src/sipl/grammar/sipl.lark`](src/sipl/grammar/sipl.lark)
(Lark, аналізатор LALR(1)). Вона реалізує БНФ мови SIPL:

```
P ::= begin S end                                              NP1
S ::= x := a | S1 ; S2 | if b then S1 else S2
    | while b do S | begin S end | skip                       NS1–NS6
a ::= n | x | a1 + a2 | a1 - a2 | a1 * a2 | (a)                 NA1–NA6
b ::= a1 = a2 | a1 > a2 | b1 ∨ b2 | ¬b | (b)                    NB1–NB5
```

У дереві виводу нетермінали підписані: `<програма>` (NP1),
`<оператор>` (NS1–NS6), `<вираз>` (NA1–NA6), `<умова>` (NB1–NB5), `<змінна>`, `<число>`.

Лексика:

| Лексема | Запис |
|---|---|
| ключові слова | `begin end if then else while do skip` — зарезервовані, малими літерами |
| змінна | `[A-Za-z_][A-Za-z0-9_]*`, крім ключових слів (`beginner`, `endX` — допустимі імена) |
| число | `-?[0-9]+`. Мінус належить числу лише там, де очікується операнд: у `Y - 1` це віднімання, у `R := -1` — від'ємне число |
| присвоювання | `:=` |
| операції | `+`, `-` (також `−`, `–`), `*` (також `∗`, `×`), `=`, `>` |
| логічні | `∨` або `or`, `¬` або `not` |
| дужки, розділювач | `(` `)` `;` |
| коментар | `// до кінця рядка` |
| пропуски | пробіли, табуляції й переведення рядка ігноруються |

БНФ мови SIPL неоднозначна (наприклад, `a - b - c`), тому граматика фіксує пріоритети,
від слабшого до сильнішого: `;` (права асоціативність) → тіло `if`/`while` (один оператор,
кілька беруть у `begin … end`) → `∨` (ліва) → `¬` → `=`, `>` (не асоціативні) → `+`, `-` (ліва) → `*` (ліва).

## Команди CLI

| Команда | Що робить | Основні параметри |
|---------|-----------|-------------------|
| `check ФАЙЛ` | перевіряє синтаксис, показує змінні програми | `--json` |
| `parse ФАЙЛ` | будує AST | `-f text\|dot\|svg`, `--spans`, `-o ФАЙЛ`, `--json` |
| `tree ФАЙЛ` | будує дерево синтаксичного виводу | `-f text\|dot\|svg\|leaves`, `--spans`, `-o ФАЙЛ`, `--json` |
| `run ФАЙЛ` | виконує програму, друкує кінцевий стан | `-s X=5,Y=2`, `--max-steps N`, `--json` |
| `trace ФАЙЛ` | виконує програму, друкує всі події | `-s …`, `--max-steps N`, `--json` |
| `term ФАЙЛ` | будує семантичний терм | `--explain`, `--ascii`, `--json` |
| `visualize ФАЙЛ` | генерує інтерактивну HTML-сторінку «текст ↔ parse tree ↔ AST» | `-o ФАЙЛ.html`, `--json` |

Замість файлу можна передати `-`, тоді програма читається зі stdin.

Коди завершення: `0` — успіх, `1` — синтаксична помилка, `2` — неправильні аргументи,
`3` — помилка виконання (наприклад, неініціалізована змінна), `4` — перевищено ліміт кроків,
`5` — помилка читання/запису файлу.

### JSON-режим

З `--json` будь-яка команда друкує один JSON-об'єкт:

```json
{
  "schema_version": 1,
  "tool": "sipl",
  "version": "0.1.0",
  "command": "run",
  "file": "examples/power.sipl",
  "ok": true,
  "result": { "state": { "X": 5, "Y": 0, "R": 25 }, "steps": 8 },
  "diagnostics": []
}
```

- `ok = false` означає помилку: її описує `diagnostics`
  (`{"severity", "code", "message", "span"}`), а `result` дорівнює `null`. Виняток — `trace`:
  `result` містить події до моменту помилки.
- `span` — позиція у тексті: `line`, `column` (з 1), `end_line`, `end_column`, `start`, `end`
  (зміщення в символах).
- `result` за командами: `check` → `variables`; `parse` → `ast`; `tree` → `parse_tree`, `leaves`;
  `run` → `state`, `steps`; `trace` → `events`, `state`, `steps`; `term` → `term`, `term_ascii`,
  `tree` (і `steps` з `--explain`); `visualize` → `output`.
- Події `trace` (`kind`): `program_started`, `before_statement`, `after_statement`,
  `variable_changed`, `condition_evaluated`, `program_finished`.

Формат описано JSON Schema [`docs/schema/cli-output.schema.json`](docs/schema/cli-output.schema.json),
і тести перевіряють за нею вивід кожної команди. Несумісна зміна формату вимагає збільшити
`schema_version`.

## Використання як бібліотеки

```python
from sipl import parse, parse_tree
from sipl.interpreter import Interpreter, run, trace
from sipl.semantics import build_term, explain_term
from sipl.visualization import from_parse_tree, render_dot

program = parse(open("examples/power.sipl", encoding="utf-8").read())
run(program, {"X": 5, "Y": 2})
build_term(program).render()

for event in Interpreter().events(program, {"X": 2, "Y": 1}):
    print(event.to_dict())
```

## Структура проєкту

```
TP_Project/
├── src/sipl/
│   ├── grammar/sipl.lark      # машинозчитувана граматика (CORE-01)
│   ├── parser.py              # текст → дерево виводу → AST, діагностика (CORE-02)
│   ├── parse_tree.py          # конкретний синтаксис: <програма>, <оператор>, …
│   ├── ast.py                 # типізоване AST, SourceSpan
│   ├── printer.py             # AST → текст SIPL
│   ├── errors.py              # помилки та Diagnostic
│   ├── interpreter/           # виконання, стан, події, trace (CORE-03, CORE-04)
│   ├── semantics/             # семантичні терми та пояснення правил (SEM-01)
│   ├── visualization/         # text / DOT / SVG / HTML (VIS-01, VIS-02)
│   └── cli.py                 # командний рядок (CORE-05)
├── examples/                  # 12 коректних програм із вхідними даними та очікуваним результатом
│   └── invalid/               # 15 некоректних програм з очікуваною позицією помилки
├── tests/                     # pytest; golden-файли термів у tests/golden/terms
└── docs/schema/               # JSON Schema виводу CLI
```

## Тести

```bash
pytest                 # усі тести
pytest --cov           # з покриттям (зараз ≈97% коду пакета)
```

Тести перевіряють, що граматика приймає 12 коректних і 13 коротких програм та відхиляє
15 некоректних прикладів і 12 коротких програм. Для кожного некоректного прикладу
перевіряється точна позиція помилки. Також перевіряються структура AST і позиції `SourceSpan`,
пріоритети операцій та round-trip `AST → текст → AST`. Інтерпретатор перевіряється на кінцевих
станах усіх прикладів і на класах вхідних даних (x^y, C(x, y)), на неініціалізованих змінних
і на ліміті кроків. Для подій перевіряються порядок і JSON. Семантичні терми звіряються
з golden-файлами, з термами для x^y та C(x, y), побудованими вручну. Візуалізації перевіряються
на коректність SVG і на зв'язок вузлів із текстом. Для CLI перевіряються всі команди,
коди завершення та валідація JSON за схемою.

Golden-файли термів оновлюються свідомо: `SIPL_UPDATE_GOLDEN=1 pytest tests/test_semantics.py`.

## Формат прикладів

Кожен файл в `examples/` починається з коментарів, які читають тести:

```
// input: X=5, Y=2      ← початковий стан
// expect: R=25         ← очікувані значення в кінцевому стані
```

У `examples/invalid/` рядок `// error: 5:1` задає рядок і колонку очікуваної синтаксичної помилки.

## Обмеження та рішення щодо мови

- Граматика відповідає БНФ мови SIPL. Неоднозначності БНФ розв'язані пріоритетами: `;`
  має найнижчий пріоритет і правоасоціативна, тіло `if`/`while` — один оператор
  (кілька беруть у `begin … end`), `*` сильніше за `+`/`-`, `¬` сильніше за `∨`.
- Розширення лексики, яких немає в БНФ: коментарі `// …`, ASCII-форми `or`/`not` для `∨`/`¬`,
  юнікодні мінус `−`/`–` і множення `∗`/`×`. На AST вони не впливають.
- Ключові слова зарезервовані та записуються малими літерами.
- Значення — необмежені цілі числа Python. Функцій `div`/`mod` у БНФ мови SIPL немає, тож їх немає й тут.
- Читання змінної, якої немає у стані, означає невизначений результат і повідомляється
  як помилка з позицією у тексті. Диз'юнкція обчислює обидва аргументи (як `S2(or, …)`).
- Нескінченні цикли автоматично не розпізнаються, бо це нерозв'язна задача.
  Виконання обривається, якщо перевищено ліміт елементарних кроків (за замовчуванням 100 000).

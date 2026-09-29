# Модели и слои принятия решений

Игра сообщает ситуацию и список действий. `Brain` выбирает идентификатор. `Agent` применяет дополнительные слои и проверяет, что ответ входит в список. Физику и управление камерой адаптер модели не знает.

```text
До старта: уровень → необязательный Planner → короткий план
У препятствия: Context → Layer → Layer → Brain → Decision
После решения: игровой контроллер → прыжок / подкат / щит / выстрел
```

Все контракты находятся в `race/contracts.py`. Контекст неизменяемый; слои могут добавлять сведения, но не заменять доступные действия. При отсутствии заряда из кандидатов исключаются щит и выстрел.

## Минимальный адаптер

```python
from race.contracts import Context, Decision

class MyBrain:
    async def choose(self, context: Context) -> Decision:
        # Здесь ваш SDK или HTTP-запрос. Отдавайте ID, а не текст кнопки.
        selected = await your_model.choose(
            state=context.state,
            choices={c.id: c.text for c in context.candidates},
        )
        return Decision(action=selected, model="my-model")
```

Для подключения напишите модуль `examples/my_plugin.py`:

```python
from race.app import Provider
from race.contracts import Agent

def register(registry, client, settings):
    brain = MyBrain()
    registry["my-model"] = Provider(
        "Моя модель", lambda _token: Agent(brain), requires_token=False,
    )
```

Запуск: `RACE_PLUGIN=examples.my_plugin:register python -m race`. Модель появится в списке соперников. Плагин загружается владельцем сервера из кода; посетитель не может задать произвольный Python-модуль или URL провайдера.

Долгие синхронные вычисления выносите в отдельный поток. Модель загружайте один раз при регистрации, а не перед каждым препятствием. Если она не поддерживает параллельный инференс, используйте очередь с одним исполнителем, как в адаптере Laya. Отмена HTTP-запроса не останавливает уже запущенный Python/CUDA-инференс, поэтому следующая задача должна дождаться его завершения.

## Laya на PyTorch

Готовый пример: `examples/laya_plugin.py`. Он использует `race/brains/laya.py` и не требует токена Jev. Зависимости Laya и веса не входят в базовый контейнер.

Установите официальный [Laya](https://huggingface.co/convaiinnovations/laya) в отдельное окружение согласно его инструкции. Наш адаптер рассчитан на API библиотеки 0.3.5: `laya.load(checkpoint, device=...)`, затем `model.predict(state, questions)`. В проверке этого выпуска реальные веса Laya не запускались.

```bash
pip install laya==0.3.5
LAYA_MODEL_PATH=/path/to/checkpoint \
LAYA_DEVICE=cpu \
RACE_PLUGIN=examples.laya_plugin:register \
python -m race
```

Для NVIDIA можно поставить соответствующий PyTorch и выбрать `LAYA_DEVICE=cuda`. MLX-версия Laya требует Apple Silicon и другого адаптера; обычный Linux-контейнер её не запускает. Проверяйте язык и назначение конкретного checkpoint: `laya-typed-decisions` и multilingual — разные модели.

В Docker потребуется производный образ с Laya/PyTorch, том с весами и, для CUDA, доступ контейнера к GPU. В этом проекте базовый образ остаётся небольшим и ориентирован на облачный Jev. Плата за локальный API в отчёте равна нулю; расходы на оборудование и электричество не оцениваются.

## LLM для плана + Jev для реакции

Рабочий пример подключения — `examples/layered_plugin.py`. Планировщик `HttpPlanner` обращается к локальному серверу с OpenAI-совместимым `/v1/chat/completions`. Он вызывается **один раз до старта**; игра ждёт готовности человека уже после получения плана.

```bash
PLANNER_URL=http://127.0.0.1:11434/v1/chat/completions \
PLANNER_MODEL=your-installed-model \
RACE_PLUGIN=examples.layered_plugin:register \
python -m race
```

Выберите «LLM + Jev» в интерфейсе. Название LLM должно совпадать с моделью, уже установленной на вашем локальном сервере. В Docker Desktop для LLM на хосте обычно используется `host.docker.internal`; на Linux добавьте `host-gateway` или разместите LLM в той же Docker-сети.

План живёт в памяти вкладки и включается в последующие запросы. `PlanLayer` добавляет его к наблюдению, Jev выбирает действие. Планировщик не получает API-токен Jev. Его URL задаётся только владельцем сервера.

Дополнительный слой, например, может дописать правило экономии заряда:

```python
from dataclasses import replace

class EnergyAdvice:
    async def apply(self, context):
        return replace(context, state=context.state +
                       " Prefer a free action when it is equally safe.")

agent = Agent(brain, layers=(PlanLayer(), EnergyAdvice()), planner=planner)
```

Новый сетевой LLM-запрос внутри каждого слоя увеличит задержку реакции. Для медленных задач используйте `Planner`; для дешёвых преобразований текущего наблюдения — `Layer`. Если нужен меняющийся долгосрочный план, возвращайте его явно в браузер и передавайте следующим запросом: сервер не ведёт память матча.

Примеры Laya и LLM интегрируют реальные интерфейсы, но требуют ваших весов/запущенного LLM. Они не подменяют модель эвристикой и не дают заранее рассчитанных ответов.

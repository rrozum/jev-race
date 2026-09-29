extends Node

## One authoritative track, two independent cameras, equal obstacle timing.
## The Python server creates the track and chooses Jev's actions. This scene
## handles physics, input, visuals, and the final race result.

const PLAYER_SCENE = preload("res://player/player.tscn")
const BACKGROUND_SCENE = preload("res://level/background/parallax_background.tscn")
const TRACK_RENDERER = preload("res://track_renderer.gd")
const RUNNER_SCRIPT = preload("res://race_runner.gd")
const ACTIONS = ["jump", "slide", "shield", "shoot"]
const ACTION_NAMES = ["ПРЫЖОК", "ПОДКАТ", "ЩИТ", "ВЫСТРЕЛ"]
var ACTOR_NAMES = {"human": "ВЫ", "jev": "JEV"}

var configured := false
var ready_to_start := false
var track: Dictionary = {}
var racers: Dictionary = {}
var viewports: Array[SubViewport] = []
var viewport_containers: Array[SubViewportContainer] = []
var view_layout: GridContainer
var view_mode := "side"
var world: Node2D
var status_labels: Dictionary = {}
var status_panels: Dictionary = {}
var cue_label: Label
var cue_panel: PanelContainer
var message_label: Label
var buttons: Array[Button] = []
var complete := false
var race_started := false
var auto_human := false
var elapsed := 0.0
var jev_requests := 0
var view_callback
var configure_callback
var decision_callback
var begin_callback


func _ready() -> void:
	_build_views()
	_build_ui()
	_update_view_layout()
	Music.stream = load("res://music.ogg")
	Music.stop()
	message_label.text = "Загружаем трассу…"
	if OS.has_feature("web"):
		view_callback = JavaScriptBridge.create_callback(_on_browser_view_change)
		configure_callback = JavaScriptBridge.create_callback(_on_configure)
		decision_callback = JavaScriptBridge.create_callback(_on_decision)
		begin_callback = JavaScriptBridge.create_callback(func(_args): _begin_race())
		var window = JavaScriptBridge.get_interface("window")
		window.raceSetView = view_callback
		window.raceConfigure = configure_callback
		window.raceDecision = decision_callback
		window.raceBegin = begin_callback
		_notify({"type": "engine-ready"})


func _notify(data: Dictionary) -> void:
	if OS.has_feature("web"):
		var window = JavaScriptBridge.get_interface("window")
		var payload = JavaScriptBridge.get_interface("JSON").parse(JSON.stringify(data))
		window.parent.postMessage(payload, str(window.location.origin))


func _on_configure(args: Array) -> void:
	if configured or args.is_empty():
		return
	var data = JSON.parse_string(str(args[0]))
	if not data is Dictionary or not data.get("track") is Dictionary:
		return
	track = data["track"]
	view_mode = "stack" if data.get("view") == "stack" else "side"
	auto_human = bool(data.get("auto_human", false))
	ACTOR_NAMES["human"] = str(data.get("human_name", "ВЫ"))
	ACTOR_NAMES["jev"] = str(data.get("bot_name", "Jev"))
	for button in buttons:
		button.visible = not auto_human
	TRACK_RENDERER.new().build(world, track)
	for actor in racers:
		racers[actor]["node"].camera.limit_right = int(track["finish_x"]) + 300
	configured = true
	ready_to_start = true
	_update_view_layout()
	_update_ui()
	message_label.text = "Нажмите любую клавишу, если готовы"
	_notify({"type": "race-ready"})


func _begin_race() -> void:
	if not ready_to_start or race_started:
		return
	ready_to_start = false
	for actor in racers:
		racers[actor]["node"].set("running", true)
	race_started = true
	Music.play()
	message_label.text = "Бег начался!" if auto_human else "Бег начался. Реагируйте на препятствия!"
	_notify({"type": "race-started"})


func _build_views() -> void:
	view_layout = GridContainer.new()
	view_layout.columns = 2
	view_layout.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	view_layout.add_theme_constant_override("h_separation", 2)
	view_layout.add_theme_constant_override("v_separation", 2)
	add_child(view_layout)
	for i in 2:
		var container := SubViewportContainer.new()
		container.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		container.size_flags_vertical = Control.SIZE_EXPAND_FILL
		container.stretch = true
		view_layout.add_child(container)
		viewport_containers.append(container)
		var viewport := SubViewport.new()
		viewport.size = Vector2i(400, 480)
		viewport.canvas_item_default_texture_filter = Viewport.DEFAULT_CANVAS_ITEM_TEXTURE_FILTER_NEAREST
		viewport.canvas_cull_mask = 3 if i == 0 else 5
		viewport.render_target_update_mode = SubViewport.UPDATE_ALWAYS
		container.add_child(viewport)
		viewports.append(viewport)
		viewport.add_child(BACKGROUND_SCENE.instantiate())
	world = Node2D.new()
	viewports[0].add_child(world)
	viewports[1].world_2d = viewports[0].world_2d
	for actor in ["human", "jev"]:
		var runner: Player = PLAYER_SCENE.instantiate()
		runner.set_script(RUNNER_SCRIPT)
		runner.position = Vector2(100, 631)
		runner.z_index = 5
		runner.modulate = Color(0.65, 1.1, 2.0) if actor == "human" else Color(2.0, 0.82, 0.68)
		runner.visibility_layer = 2 if actor == "human" else 4
		world.add_child(runner)
		var index := 0 if actor == "human" else 1
		runner.camera.custom_viewport = viewports[index]
		runner.camera.limit_left = 0
		runner.camera.limit_right = 20000
		runner.camera.limit_top = 0
		runner.camera.limit_bottom = 700
		runner.camera.make_current()
		racers[actor] = {"node": runner, "next": 0, "chosen": "", "pending_action": "", "applied": false,
			"requested": false, "request_attempts": 0, "energy": 3, "penalties": 0, "done": false, "elapsed": 0.0,
			"outcomes": []}


func _update_view_layout() -> void:
	view_layout.columns = 1 if view_mode == "stack" else 2
	racers["human"]["node"].camera.make_current()
	racers["jev"]["node"].camera.make_current()
	status_panels["jev"].position = Vector2(8, 248) if view_mode == "stack" else Vector2(408, 8)
	cue_panel.position = Vector2(408, 8) if view_mode == "stack" else Vector2(8, 89)


func _on_browser_view_change(args: Array) -> void:
	if args.is_empty() or str(args[0]) not in ["side", "stack"]:
		return
	view_mode = str(args[0])
	_update_view_layout()


func _build_ui() -> void:
	var layer := CanvasLayer.new()
	layer.layer = 10
	add_child(layer)
	var overlay := Control.new()
	overlay.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	layer.add_child(overlay)
	for actor in ["human", "jev"]:
		var index := 0 if actor == "human" else 1
		var panel := PanelContainer.new()
		panel.position = Vector2(index * 400 + 8, 8)
		panel.size = Vector2(384, 72)
		panel.add_theme_stylebox_override("panel", _panel_style(Color(0.07, 0.12, 0.22, 0.9)))
		overlay.add_child(panel)
		var label := Label.new()
		label.add_theme_font_size_override("font_size", 16)
		label.add_theme_color_override("font_color", Color.WHITE)
		panel.add_child(label)
		status_labels[actor] = label
		status_panels[actor] = panel
	cue_panel = PanelContainer.new()
	cue_panel.position = Vector2(8, 89)
	cue_panel.size = Vector2(384, 65)
	cue_panel.add_theme_stylebox_override("panel", _panel_style(Color(0.1, 0.14, 0.23, 0.84)))
	overlay.add_child(cue_panel)
	cue_label = Label.new()
	cue_label.add_theme_font_size_override("font_size", 16)
	cue_label.add_theme_color_override("font_color", Color(1, 0.96, 0.8))
	cue_panel.add_child(cue_label)
	var message_panel := PanelContainer.new()
	message_panel.position = Vector2(8, 393)
	message_panel.size = Vector2(784, 34)
	message_panel.add_theme_stylebox_override("panel", _panel_style(Color(0.08, 0.12, 0.2, 0.88)))
	overlay.add_child(message_panel)
	message_label = Label.new()
	message_label.add_theme_font_size_override("font_size", 15)
	message_label.add_theme_color_override("font_color", Color.WHITE)
	message_panel.add_child(message_label)
	for i in ACTIONS.size():
		var button := Button.new()
		button.text = "%s  %s" % [["W / 1", "S / 2", "Q / 3", "Пробел / 4"][i], ACTION_NAMES[i]]
		button.position = Vector2(8 + i * 198, 435)
		button.size = Vector2(190, 38)
		button.add_theme_font_size_override("font_size", 13)
		button.pressed.connect(_choose_human.bind(ACTIONS[i]))
		overlay.add_child(button)
		buttons.append(button)
	_update_ui()


func _panel_style(color: Color) -> StyleBoxFlat:
	var box := StyleBoxFlat.new()
	box.bg_color = color
	box.corner_radius_top_left = 8
	box.corner_radius_top_right = 8
	box.corner_radius_bottom_left = 8
	box.corner_radius_bottom_right = 8
	box.content_margin_left = 10
	box.content_margin_top = 7
	return box


func _input(event: InputEvent) -> void:
	if ready_to_start and ((event is InputEventKey and event.pressed) or (event is InputEventMouseButton and event.pressed)):
		_begin_race()
		get_viewport().set_input_as_handled()
		return
	if event is InputEventKey and event.pressed and not event.echo:
		var key: int = event.physical_keycode if event.physical_keycode != 0 else event.keycode
		match key:
			KEY_W, KEY_1: _choose_human("jump")
			KEY_S, KEY_2: _choose_human("slide")
			KEY_Q, KEY_3: _choose_human("shield")
			KEY_SPACE, KEY_4: _choose_human("shoot")
	elif event is InputEventMouseButton and event.pressed and event.button_index == MOUSE_BUTTON_LEFT:
		if event.position.y < 390.0:
			_choose_human("shoot")


func _choose_human(action: String) -> void:
	if not configured or not race_started or complete or auto_human:
		return
	var state: Dictionary = racers["human"]
	if state["done"] or state["applied"]:
		return
	if state["next"] >= track["events"].size():
		return
	var event: Dictionary = track["events"][state["next"]]
	var distance: float = float(event["x"]) - state["node"].position.x
	if distance > 350.0:
		message_label.text = "Ещё рано. Дождитесь окна реакции перед препятствием."
		return
	if distance <= 0.0:
		message_label.text = "Поздно для действия. Готовьтесь к следующему препятствию."
		return
	if action in ["shield", "shoot"] and state["energy"] <= 0:
		message_label.text = "Нет заряда. Выберите прыжок или подкат."
		return
	_apply_action("human", action)
	message_label.text = "Вы: %s!" % ACTION_NAMES[ACTIONS.find(action)]
	_update_ui()


func _apply_action(actor: String, action: String) -> void:
	var state: Dictionary = racers[actor]
	if state["applied"] or action not in ACTIONS:
		return
	state["chosen"] = action
	state["applied"] = true
	state["node"].call("perform", action)
	if action in ["shield", "shoot"]:
		state["energy"] -= 1


func _physics_process(delta: float) -> void:
	if not configured or not race_started or complete:
		return
	elapsed += delta
	for actor in ["human", "jev"]:
		var state: Dictionary = racers[actor]
		if state["done"]:
			continue
		var runner: Player = state["node"]
		if state["next"] >= track["events"].size():
			if runner.position.x >= float(track["finish_x"]):
				state["done"] = true
				state["elapsed"] = elapsed
				runner.set("running", false)
			continue
		var event: Dictionary = track["events"][state["next"]]
		var distance := float(event["x"]) - runner.position.x
		var automatic: bool = actor == "jev" or auto_human
		if automatic and distance < 620.0 and not state["requested"]:
			state["requested"] = true
			_request_model(actor, int(event["id"]), int(state["energy"]))
		if automatic and distance <= 120.0 and distance > 0.0 and state["pending_action"] != "":
			_apply_action(actor, str(state["pending_action"]))
			state["pending_action"] = ""
		if distance <= (-85.0 if event["type"] == "gap" else 0.0):
			_resolve(actor, state, event)
			state["next"] += 1
			state["chosen"] = ""
			state["pending_action"] = ""
			state["applied"] = false
			state["requested"] = false
			state["request_attempts"] = 0
			if state["next"] % 3 == 0:
				state["energy"] = mini(3, state["energy"] + 1)
	if racers["human"]["done"] and racers["jev"]["done"]:
		_complete_match()
	_update_ui()


func _resolve(actor: String, state: Dictionary, event: Dictionary) -> void:
	var action := str(state["chosen"])
	var safe: bool = action == event["best"] or action == event["alternative"]
	if action == "jump":
		safe = safe and state["node"].position.y < (650.0 if event["type"] == "gap" else 616.0)
	elif action == "slide":
		safe = safe and state["node"].slide_time > 0.0
	elif action == "shield":
		safe = safe and state["node"].shield_time > 0.0
	if not safe:
		state["penalties"] += 1
		state["node"].slow_time = 0.7
		if event["type"] == "gap":
			state["node"].position = Vector2(float(event["x"]) + 105.0, 631)
			state["node"].velocity.y = 0
		message_label.text = "%s: столкновение, +%s с" % [ACTOR_NAMES[actor], str(track["penalty_seconds"])]
	else:
		message_label.text = "%s прошёл препятствие: %s" % [ACTOR_NAMES[actor], event["title"]]
	state["outcomes"].append({"event_id": int(event["id"]), "action": action if action != "" else "none",
		"safe": safe})


func _request_model(actor: String, event_id: int, energy: int) -> void:
	jev_requests += 1
	_notify({"type": "model-request", "actor": actor, "event_id": event_id, "energy": energy})


func _on_decision(args: Array) -> void:
	if args.is_empty() or complete:
		return
	var response = JSON.parse_string(str(args[0]))
	if not response is Dictionary:
		return
	jev_requests = maxi(0, jev_requests - 1)
	var event_id := int(response.get("event_id", -1))
	var actor := str(response.get("actor", "jev"))
	if actor != "jev" and (actor != "human" or not auto_human):
		return
	var state: Dictionary = racers[actor]
	if response.get("status") == "ok" and event_id >= 0 and event_id < track["events"].size() and state["next"] == event_id and not state["applied"]:
		if state["node"].position.x < float(track["events"][event_id]["x"]):
			state["pending_action"] = str(response["action"])


func _complete_match() -> void:
	complete = true
	Music.stop()
	var results := {}
	for actor in ["human", "jev"]:
		var runner: Player = racers[actor]["node"]
		runner.set("running", false)
		runner.velocity = Vector2.ZERO
		runner.set_physics_process(false)
		results[actor] = {"elapsed": racers[actor]["elapsed"],
			"penalties": racers[actor]["penalties"], "outcomes": racers[actor]["outcomes"]}
	message_label.text = "Финиш!"
	_update_ui()
	_notify({"type": "race-finished", "results": results})
	get_tree().paused = true


func _update_ui() -> void:
	var event_count: int = track["events"].size() if not track.is_empty() else 0
	for actor in ["human", "jev"]:
		var state: Dictionary = racers[actor]
		var label: Label = status_labels[actor]
		label.text = "%s  ·  %.1f с  ·  штрафы %d\nЭнергия %d/3  ·  %s" % [
			ACTOR_NAMES[actor], float(state["elapsed"]) if state["done"] else elapsed,
			int(state["penalties"]), int(state["energy"]),
			"препятствие %d/%d" % [mini(event_count, int(state["next"]) + 1), event_count] if event_count > 0 else "загружаем трассу"]
	if not track.is_empty() and racers["human"]["next"] < track["events"].size():
		var event: Dictionary = track["events"][racers["human"]["next"]]
		var distance: float = float(event["x"]) - racers["human"]["node"].position.x
		var prompt := "ПРЕПЯТСТВИЕ БЛИЗКО!" if distance <= 180.0 and distance > 0.0 else "Приближается: %.1f с" % maxf(0.0, distance / 300.0)
		if racers["human"]["applied"]:
			prompt = "Действие выполнено: %s" % ACTION_NAMES[ACTIONS.find(str(racers["human"]["chosen"]))]
		cue_label.text = "ВПЕРЕДИ: %s\n%s" % [event["title"], prompt]
	else:
		cue_label.text = "ТРАССА ЗАГРУЖАЕТСЯ" if not configured else "ФИНИШ"
	var can_act := false
	if not track.is_empty() and racers["human"]["next"] < track["events"].size():
		var upcoming: Dictionary = track["events"][racers["human"]["next"]]
		var remaining: float = float(upcoming["x"]) - racers["human"]["node"].position.x
		can_act = remaining <= 350.0 and remaining > 0.0
	for button in buttons:
		button.disabled = not configured or not race_started or complete or racers["human"]["applied"] or not can_act

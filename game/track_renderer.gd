extends RefCounted

## Terrain and decoration from the official Godot demo.
const TILESET = preload("res://level/tileset.tres")
var world: Node2D
var track: Dictionary

func build(parent: Node2D, data: Dictionary) -> void:
	world = parent
	track = data
	var ground := TileMapLayer.new()
	ground.tile_set = TILESET
	ground.z_index = 0
	world.add_child(ground)
	var finish_x := int(track["finish_x"])
	var last_tile := ceili(float(finish_x + 450) / 64.0)
	for tile_x in range(-2, last_tile):
		var gap := false
		for event in track["events"]:
			if event["type"] == "gap" and absf(tile_x * 64.0 + 32.0 - float(event["x"])) < 64.0:
				gap = true
		if gap:
			continue
		for row in range(10, 14):
			ground.set_cell(Vector2i(tile_x, row), 10 if row == 10 else 6, Vector2i.ZERO)
	for tile_x in range(4, last_tile, 5):
		var flower := Sprite2D.new()
		flower.texture = load("res://level/props/grass_1.webp")
		flower.position = Vector2(tile_x * 64.0, 630)
		flower.z_index = 2
		world.add_child(flower)
	for tile_x in range(7, last_tile, 9):
		var scenic_x := tile_x * 64.0
		var near_gap := false
		for event in track["events"]:
			if event["type"] == "gap" and absf(scenic_x - float(event["x"])) < 160.0:
				near_gap = true
		if near_gap:
			continue
		var tree := Sprite2D.new()
		tree.texture = load("res://level/props/tree_1.webp") if tile_x % 2 else load("res://level/props/tree_2.webp")
		tree.position = Vector2(scenic_x, 571)
		tree.z_index = -2
		world.add_child(tree)
		var bush := Sprite2D.new()
		bush.texture = load("res://level/props/bush_1.webp")
		bush.position = Vector2(scenic_x + 94.0, 610)
		bush.z_index = 1
		world.add_child(bush)
	for event in track["events"]:
		_draw_hazard(event)
	var finish := Label.new()
	finish.text = "ФИНИШ"
	finish.position = Vector2(finish_x - 42, 535)
	finish.add_theme_font_size_override("font_size", 24)
	finish.add_theme_color_override("font_color", Color.WHITE)
	world.add_child(finish)
	var pole := Polygon2D.new()
	pole.polygon = PackedVector2Array([Vector2(0, 0), Vector2(8, 0), Vector2(8, 110), Vector2(0, 110)])
	pole.color = Color(0.99, 0.85, 0.36)
	pole.position = Vector2(finish_x, 530)
	world.add_child(pole)


func _draw_hazard(event: Dictionary) -> void:
	var x := float(event["x"])
	var kind := str(event["type"])
	var shape := Polygon2D.new()
	shape.position = Vector2(x, 0)
	shape.z_index = 3
	match kind:
		"spikes":
			shape.polygon = PackedVector2Array([Vector2(-32, 640), Vector2(-20, 599), Vector2(-8, 640), Vector2(4, 599), Vector2(17, 640), Vector2(28, 599), Vector2(40, 640)])
			shape.color = Color(0.92, 0.35, 0.35)
		"beam":
			shape.polygon = PackedVector2Array([Vector2(-48, 560), Vector2(48, 560), Vector2(48, 596), Vector2(-48, 596)])
			shape.color = Color(0.36, 0.24, 0.27)
		"drone":
			shape.polygon = PackedVector2Array([Vector2(-35, 580), Vector2(0, 560), Vector2(35, 580), Vector2(0, 600)])
			shape.color = Color(0.75, 0.32, 0.73)
		"laser":
			shape.polygon = PackedVector2Array([Vector2(-48, 565), Vector2(48, 565), Vector2(48, 573), Vector2(-48, 573)])
			shape.color = Color(1.0, 0.2, 0.45)
		"beetle":
			shape.polygon = PackedVector2Array([Vector2(-27, 637), Vector2(-20, 604), Vector2(0, 593), Vector2(22, 604), Vector2(29, 637)])
			shape.color = Color(0.48, 0.28, 0.66)
		"gap":
			shape.polygon = PackedVector2Array([Vector2(-70, 640), Vector2(70, 640), Vector2(70, 648), Vector2(-70, 648)])
			shape.color = Color(0.95, 0.35, 0.34, 0.7)
	world.add_child(shape)
	var sign := Label.new()
	sign.text = str(event["title"])
	sign.add_theme_font_size_override("font_size", 13)
	sign.add_theme_color_override("font_color", Color(0.27, 0.15, 0.2))
	sign.position = Vector2(x - 48, 521)
	sign.z_index = 3
	world.add_child(sign)

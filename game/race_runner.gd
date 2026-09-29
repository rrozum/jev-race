extends Player

## The official demo's robot and physics, with a race controller in place of WASD.
var running := false
var slow_time := 0.0
var slide_time := 0.0
var shield_time := 0.0


func _physics_process(delta: float) -> void:
	if is_on_floor():
		_double_jump_charged = true
	slow_time = maxf(0.0, slow_time - delta)
	slide_time = maxf(0.0, slide_time - delta)
	shield_time = maxf(0.0, shield_time - delta)
	velocity.y = minf(TERMINAL_VELOCITY, velocity.y + get_gravity().y * delta)
	var target_speed := WALK_SPEED if running else 0.0
	if slow_time > 0.0:
		target_speed *= 0.45
	velocity.x = move_toward(velocity.x, target_speed, ACCELERATION_SPEED * delta)
	sprite.scale.x = 1.0
	sprite.scale.y = 0.55 if slide_time > 0.0 else 1.0
	floor_stop_on_slope = not platform_detector.is_colliding()
	move_and_slide()
	var animation := "crouch" if slide_time > 0.0 else get_new_animation()
	if animation != animation_player.current_animation:
		animation_player.play(animation)
	queue_redraw()


func perform(action: String) -> void:
	match action:
		"jump":
			try_jump()
		"slide":
			slide_time = 1.5
		"shield":
			shield_time = 1.5
		"shoot":
			gun.shoot(1.0)


func _draw() -> void:
	if shield_time > 0.0:
		draw_arc(Vector2(0, -14), 37, 0.0, TAU, 32, Color(0.37, 0.86, 1.0, 0.9), 4.0)

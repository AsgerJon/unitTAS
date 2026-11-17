package io.github.asgerjon.unittas.agent.probe;

import io.github.asgerjon.unittas.agent.game.Entity;

/** The probe's own subclass of a game class: its override renamed with the game's method. */
public final class Ticker extends Entity {

	@Override
	public void tick() {
		x += 100;
	}
}

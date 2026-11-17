package io.github.asgerjon.unittas.agent.game;

/** A subclass that overrides, implements an interface, and holds a nested enum. */
public class Player extends Entity implements Named {

	public enum Hand {
		MAIN, OFF
	}

	public final Hand hand = Hand.MAIN;

	@Override
	public String name() {
		return "steve";
	}

	@Override
	public void tick() {
		super.tick();
		x += 10;
	}
}

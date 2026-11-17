package io.github.asgerjon.unittas.agent.sample;

/** A subclass whose override calls the wrapped method by super, as the game's subclasses do. */
public class SubSample extends Sample {

	@Override
	public void tick() {
		SEEN.add("sub");
		super.tick();
	}
}

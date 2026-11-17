package io.github.asgerjon.unittas.agent.game;

/** A game's own functional interface: a lambda for it names its method, renamed too. */
@FunctionalInterface
public interface Listener {

	void heard(Entity entity);
}

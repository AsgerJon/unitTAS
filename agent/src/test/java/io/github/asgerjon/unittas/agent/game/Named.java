package io.github.asgerjon.unittas.agent.game;

/** An interface with a default method, which the player takes. */
public interface Named {

	String name();

	default String greeting() {
		return "hello " + name();
	}
}
